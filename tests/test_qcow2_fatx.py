from __future__ import annotations

import hashlib
import os
import struct
import tempfile
import unittest
import zlib
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from xemu_lab.backup import (
    GameBackup,
    deserialize_backup,
    save_backup,
    serialize_backup,
)
from xemu_lab.catalog import HDDCatalog
from xemu_lab.compare import compare_paths
from xemu_lab.fatx import (
    FATXVolume,
    XboxRegion,
)
from xemu_lab.remap import (
    build_remap_plan,
    decide_restore_path,
)
from xemu_lab.qcow2 import (
    QCOW2BlockDevice,
    QCOW2FormatError,
    QCOW2WritableBlockDevice,
    QCOW2WriteError,
    QCOW2_MAGIC,
    QCOW_OFLAG_COMPRESSED,
    QCOW_OFLAG_COPIED,
    QCOW_OFLAG_ZERO,
)
from xemu_lab.restore import RestoreError, restore_backup_to_path
from xemu_lab.safety import (
    SafetyError,
    assert_not_golden,
    assert_path_writable,
    atomic_copy_qcow2,
)


BLACK_B1 = Path(r"D:\xemu\bk\xbox_hddB1.qcow2")
BLACK_B2 = Path(r"D:\xemu\bk\xbox_hddB2.qcow2")
HALO_H1 = Path(r"D:\xemu\bk\xbox_hddh1.qcow2")
HALO_H2 = Path(r"D:\xemu\bk\xbox_hddh2.qcow2")


class MemoryBlockDevice:
    def __init__(self, data: bytes):
        self.data = bytearray(data)

    @property
    def size(self) -> int:
        return len(self.data)

    def read_at(self, offset: int, size: int) -> bytes:
        if offset < 0 or size < 0 or offset + size > len(self.data):
            raise ValueError("lettura fuori range")
        return bytes(self.data[offset : offset + size])

    def write_at(self, offset: int, data: bytes, *, allocate: bool = False) -> None:
        payload = bytes(data)
        if offset < 0 or offset + len(payload) > len(self.data):
            raise ValueError("scrittura fuori range")
        self.data[offset : offset + len(payload)] = payload


class QCOW2ReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "synthetic.qcow2"
        self.path.write_bytes(_make_synthetic_qcow2())

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_reads_l1_size_from_header_offset_36(self) -> None:
        with QCOW2BlockDevice(self.path) as device:
            self.assertEqual(device.header.l1_size, 1)
            self.assertEqual(device.header.l1_table_offset, 0x2000)
            self.assertEqual(device.cluster_size, 0x1000)

    def test_maps_allocated_unallocated_and_zero_clusters(self) -> None:
        with QCOW2BlockDevice(self.path) as device:
            self.assertEqual(device.map_offset(0), 0x4000)
            self.assertIsNone(device.map_offset(0x1000))
            self.assertIsNone(device.map_offset(0x2000))
            self.assertEqual(device.map_offset(0x3000), 0x5000)
            self.assertEqual(device.read_at(0x1000, 16), bytes(16))
            self.assertEqual(device.read_at(0x2000, 16), bytes(16))
            self.assertEqual(device.read_at(0x3000, 16), b"D" * 16)

    def test_read_crosses_qcow2_cluster_boundary(self) -> None:
        with QCOW2BlockDevice(self.path) as device:
            expected_tail = bytes(range(256))[-6:]
            self.assertEqual(
                device.read_at(0x1000 - 6, 12),
                expected_tail + bytes(6),
            )

    def test_rejects_out_of_bounds_reads(self) -> None:
        with QCOW2BlockDevice(self.path) as device:
            with self.assertRaises(ValueError):
                device.read_at(-1, 1)
            with self.assertRaises(ValueError):
                device.read_at(device.size, 1)
            with self.assertRaises(ValueError):
                device.read_cluster(device.cluster_count)

    def test_has_no_write_api_and_does_not_change_file(self) -> None:
        before = hashlib.sha256(self.path.read_bytes()).digest()
        with QCOW2BlockDevice(self.path) as device:
            self.assertFalse(hasattr(device, "write_at"))
            self.assertEqual(device.read_at(0, 64), bytes(range(64)))
        after = hashlib.sha256(self.path.read_bytes()).digest()
        self.assertEqual(before, after)

    def test_rejects_invalid_magic(self) -> None:
        invalid = Path(self.temp_dir.name) / "invalid.qcow2"
        invalid.write_bytes(bytes(0x1000))
        with self.assertRaises(QCOW2FormatError):
            with QCOW2BlockDevice(invalid):
                pass

    def test_rejects_zero_descriptor_bit_in_qcow2_v2(self) -> None:
        version2 = bytearray(_make_synthetic_qcow2())
        struct.pack_into(">I", version2, 4, 2)
        path = Path(self.temp_dir.name) / "version2.qcow2"
        path.write_bytes(version2)
        with QCOW2BlockDevice(path) as device:
            with self.assertRaises(QCOW2FormatError):
                device.read_at(0x2000, 1)


class QCOW2WriterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "writable.qcow2"
        self.path.write_bytes(_make_synthetic_qcow2())

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_overwrite_allocated_cluster(self) -> None:
        with QCOW2WritableBlockDevice(self.path) as device:
            device.write_at(0, b"HELLO")
            device.flush()
            self.assertEqual(device.read_at(0, 5), b"HELLO")
            self.assertEqual(device.read_at(5, 1), bytes([5]))

    def test_rejects_unallocated_and_zero_clusters(self) -> None:
        with QCOW2WritableBlockDevice(self.path) as device:
            with self.assertRaises(QCOW2WriteError):
                device.write_at(0x1000, b"X")
            with self.assertRaises(QCOW2WriteError):
                device.write_at(0x2000, b"Y")

    def test_write_does_not_change_unrelated_host_clusters(self) -> None:
        before = self.path.read_bytes()
        with QCOW2WritableBlockDevice(self.path) as device:
            device.write_at(0x3000, b"ZZZZ")
            device.flush()
        after = bytearray(self.path.read_bytes())
        # Host cluster at 0x4000 (guest 0) unchanged; guest 0x3000 -> host 0x5000.
        self.assertEqual(before[0x4000:0x5000], after[0x4000:0x5000])
        self.assertEqual(after[0x5000:0x5004], b"ZZZZ")
        self.assertEqual(before[:0x4000], after[:0x4000])


class BackupRestoreUnitTests(unittest.TestCase):
    def test_serialize_roundtrip_and_restore_on_synthetic_qcow2(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        image = Path(temp.name) / "target.qcow2"
        image.write_bytes(_make_synthetic_qcow2())

        backup = GameBackup(
            title_id="4c410015",
            partition="E",
            source_path=image,
            source_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
            created_at=datetime.now(timezone.utc),
            fat_entry_size=2,
            fatx_cluster_size=0x4000,
            directory_entries=[(0x10, b"E" * 64)],
            fat_runs=[],
            data_chunks=[(9, 0x100, b"PAYLOAD!!")],
        )

        payload = serialize_backup(backup)
        restored = deserialize_backup(payload)
        self.assertEqual(restored.title_id, "4c410015")
        self.assertEqual(restored.data_chunks[0][2], b"PAYLOAD!!")

        bin_path, json_path = save_backup(backup, output_dir=temp.name)
        self.assertTrue(bin_path.is_file())
        self.assertTrue(json_path.is_file())

        report = restore_backup_to_path(restored, image, verify=True)
        self.assertTrue(report.verified)
        with QCOW2BlockDevice(image) as device:
            self.assertEqual(device.read_at(0x100, 9), b"PAYLOAD!!")
            self.assertEqual(device.read_at(0x10, 64), b"E" * 64)


class QCOW2AllocateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "alloc.qcow2"
        self.path.write_bytes(_make_synthetic_qcow2_with_refcounts())

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_allocate_unallocated_and_write(self) -> None:
        with QCOW2WritableBlockDevice(self.path) as device:
            with self.assertRaises(QCOW2WriteError):
                device.write_at(0x1000, b"NEW1")
            device.write_at(0x1000, b"NEW1", allocate=True)
            self.assertEqual(device.read_at(0x1000, 4), b"NEW1")
            self.assertGreaterEqual(device.clusters_allocated, 1)
            self.assertFalse(device.header.is_dirty)

    def test_allocate_zero_cluster(self) -> None:
        with QCOW2WritableBlockDevice(self.path) as device:
            self.assertTrue(device.map_cluster(2).reads_as_zero)
            device.write_at(0x2000, b"ZERO", allocate=True)
            mapping = device.map_cluster(2)
            self.assertTrue(mapping.allocated)
            self.assertFalse(mapping.reads_as_zero)
            self.assertEqual(device.read_at(0x2000, 4), b"ZERO")

    def test_reallocate_compressed_cluster(self) -> None:
        with QCOW2WritableBlockDevice(self.path) as device:
            self.assertTrue(device.is_compressed_cluster(4))
            device.write_at(0x4000, b"UNC!", allocate=True)
            self.assertFalse(device.is_compressed_cluster(4))
            self.assertEqual(device.read_at(0x4000, 4), b"UNC!")
            # Prefisso sovrascritto; il resto resta il contenuto decompresso.
            self.assertEqual(device.read_at(0x4004, 4), b"CCCC")

    def test_allocate_creates_missing_l2(self) -> None:
        # Guest 512 richiede L1[1], inizialmente 0.
        guest_offset = 512 * 0x1000
        with QCOW2WritableBlockDevice(self.path) as device:
            self.assertEqual(device.raw_l2_entry(512), 0)
            device.write_at(guest_offset, b"L2OK", allocate=True)
            self.assertEqual(device.read_at(guest_offset, 4), b"L2OK")
            self.assertNotEqual(device._l1_table[1], 0)

    def test_allocate_false_still_rejects_unallocated(self) -> None:
        with QCOW2WritableBlockDevice(self.path) as device:
            with self.assertRaises(QCOW2WriteError):
                device.write_at(0x1000, b"X", allocate=False)

    def test_restore_with_allow_allocate_on_sparse_target(self) -> None:
        # Envelope QCOW2 interi: evita di azzerare i byte non chirurgici.
        with QCOW2WritableBlockDevice(self.path) as device:
            env1 = bytearray(device.read_cluster_content(1))
            env2 = bytearray(device.read_cluster_content(2))
            env4 = bytearray(device.read_cluster_content(4))
        env1[0:64] = b"D" * 64
        env2[0:4] = b"FATZ"
        env4[0:4] = b"COMP"
        envelopes = [(1, bytes(env1)), (2, bytes(env2)), (4, bytes(env4))]

        backup = GameBackup(
            title_id="4c410015",
            partition="E",
            source_path=self.path,
            source_sha256=hashlib.sha256(self.path.read_bytes()).hexdigest(),
            created_at=datetime.now(timezone.utc),
            fat_entry_size=2,
            fatx_cluster_size=0x4000,
            directory_entries=[(0x1000, b"D" * 64)],
            fat_runs=[],
            data_chunks=[
                (1, 0x2000, b"FATZ"),
                (2, 0x4000, b"COMP"),
            ],
            qcow2_envelopes=envelopes,
            qcow2_cluster_size=0x1000,
            format_version=7,
        )
        with self.assertRaises(Exception):
            restore_backup_to_path(backup, self.path, verify=True, allow_allocate=False)

        report = restore_backup_to_path(
            backup,
            self.path,
            verify=False,
            allow_allocate=True,
        )
        self.assertTrue(report.allocate_used)
        self.assertGreater(report.clusters_allocated, 0)
        self.assertEqual(report.envelopes_written, 3)
        with QCOW2BlockDevice(self.path) as device:
            self.assertEqual(device.read_at(0x1000, 64), b"D" * 64)
            self.assertEqual(device.read_at(0x2000, 4), b"FATZ")
            self.assertEqual(device.read_at(0x4000, 4), b"COMP")

    def test_v7_skips_envelopes_on_already_allocated_clusters(self) -> None:
        """Su cluster già overwrite-safe gli envelope non si applicano (parity v6)."""

        with QCOW2WritableBlockDevice(self.path) as device:
            env0 = device.read_cluster_content(0)
        # Payload diverso dall'immagine: se l'envelope venisse scritto, cambierebbe.
        foreign = bytes([0x5A]) * 0x1000
        backup = GameBackup(
            title_id="4c410015",
            partition="E",
            source_path=self.path,
            source_sha256="",
            created_at=datetime.now(timezone.utc),
            fat_entry_size=2,
            fatx_cluster_size=0x4000,
            directory_entries=[(0x0, b"E" * 64)],
            fat_runs=[],
            data_chunks=[],
            qcow2_envelopes=[(0, foreign)],
            qcow2_cluster_size=0x1000,
            format_version=7,
        )
        report = restore_backup_to_path(
            backup,
            self.path,
            verify=False,
            allow_allocate=True,
        )
        self.assertEqual(report.envelopes_written, 0)
        with QCOW2BlockDevice(self.path) as device:
            # Solo i 64 byte chirurgici, non l'envelope straniero.
            self.assertEqual(device.read_at(0, 64), b"E" * 64)
            self.assertEqual(device.read_at(64, 16), env0[64:80])

    def test_v6_allocate_partial_unalloc_is_rejected(self) -> None:
        backup = GameBackup(
            title_id="4c410015",
            partition="E",
            source_path=self.path,
            source_sha256="",
            created_at=datetime.now(timezone.utc),
            fat_entry_size=2,
            fatx_cluster_size=0x4000,
            directory_entries=[(0x1000, b"D" * 64)],
            fat_runs=[],
            data_chunks=[],
            format_version=6,
        )
        from xemu_lab.restore import RestoreError

        with self.assertRaises(RestoreError) as ctx:
            restore_backup_to_path(
                backup,
                self.path,
                verify=False,
                allow_allocate=True,
            )
        self.assertIn("envelope", str(ctx.exception).lower())

    def test_serialize_v7_roundtrip_includes_envelopes(self) -> None:
        backup = GameBackup(
            title_id="4c410015",
            partition="E",
            source_path=self.path,
            source_sha256="ab" * 32,
            created_at=datetime.now(timezone.utc),
            fat_entry_size=2,
            fatx_cluster_size=0x4000,
            directory_entries=[(0x10, b"E" * 64)],
            fat_runs=[],
            data_chunks=[(9, 0x100, b"PAYLOAD!!")],
            qcow2_envelopes=[(0, b"Q" * 0x1000)],
            qcow2_cluster_size=0x1000,
            format_version=7,
        )
        restored = deserialize_backup(serialize_backup(backup))
        self.assertEqual(restored.format_version, 7)
        self.assertEqual(len(restored.qcow2_envelopes), 1)
        self.assertEqual(restored.qcow2_envelopes[0][1], b"Q" * 0x1000)


class SafetyTests(unittest.TestCase):
    def test_refuses_copy_into_golden_folder(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        folder = Path(temp.name) / "bk"
        folder.mkdir()
        source = folder / "golden.qcow2"
        source.write_bytes(_make_synthetic_qcow2())
        with self.assertRaises(SafetyError):
            assert_not_golden(source, folder)
        dest = folder / "copy.qcow2"
        with self.assertRaises(SafetyError):
            atomic_copy_qcow2(source, dest, folder)

    def test_atomic_copy_verifies_hash(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        folder = Path(temp.name) / "bk"
        folder.mkdir()
        source = Path(temp.name) / "src.qcow2"
        dest = Path(temp.name) / "dst.qcow2"
        source.write_bytes(_make_synthetic_qcow2())
        with mock.patch("xemu_lab.safety.find_xemu_processes", return_value=[]):
            report = atomic_copy_qcow2(source, dest, folder)
        self.assertTrue(dest.is_file())
        self.assertEqual(report.sha256, hashlib.sha256(source.read_bytes()).hexdigest())

    def test_assert_path_writable_ok(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "live.qcow2"
        path.write_bytes(_make_synthetic_qcow2())
        assert_path_writable(path)

    def test_restore_rolls_back_on_unsafe_allocate(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "live.qcow2"
        path.write_bytes(_make_synthetic_qcow2())
        with QCOW2BlockDevice(path) as device:
            before = device.read_at(0, 64)

        bad = GameBackup(
            title_id="4c410015",
            partition="E",
            source_path=path,
            source_sha256="",
            created_at=datetime.now(timezone.utc),
            fat_entry_size=2,
            fatx_cluster_size=0x4000,
            directory_entries=[(0x1000, b"D" * 64)],
            fat_runs=[],
            data_chunks=[],
            format_version=6,
        )
        with self.assertRaises(RestoreError) as ctx:
            restore_backup_to_path(
                bad,
                path,
                verify=False,
                allow_allocate=True,
            )
        self.assertIn("envelope", str(ctx.exception).lower())
        with QCOW2WritableBlockDevice(path) as device:
            self.assertFalse(device.header.is_dirty)
            self.assertEqual(device.read_at(0, 64), before)
            # Immagine ancora apribile in scrittura dopo undo.
            device.write_at(0, before[:16])

    def test_host_checkpoint_undoes_allocate(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "live.qcow2"
        path.write_bytes(_make_synthetic_qcow2())
        host_before = path.stat().st_size

        with QCOW2WritableBlockDevice(path) as device:
            checkpoint = device.capture_host_checkpoint()
            device.write_at(0x1000, b"NEWDATA!!", allocate=True)
            self.assertGreater(device.host_bytes_grown, 0)
            device.restore_host_checkpoint(checkpoint)
            self.assertFalse(device.header.is_dirty)
            self.assertEqual(device.read_at(0x1000, 8), bytes(8))

        self.assertEqual(path.stat().st_size, host_before)


class FATXParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.partition = XboxRegion(
            "T",
            0,
            0x20000,
            "Fixture FATX",
        )
        self.device = MemoryBlockDevice(_make_synthetic_fatx())
        self.volume = FATXVolume(self.device, self.partition)

    def test_derives_fat_and_file_area_from_header(self) -> None:
        self.assertEqual(self.volume.header.cluster_size, 0x4000)
        self.assertTrue(self.volume.header.is_fat16)
        self.assertEqual(self.volume.header.fat_size, 0x1000)
        self.assertEqual(self.volume.header.file_area_offset, 0x2000)

    def test_walks_udata_tree_and_reads_file(self) -> None:
        games = self.volume.list_games()
        self.assertEqual(
            [(game.area, game.title_id) for game in games],
            [("UDATA", "45410083")],
        )
        entry = self.volume.resolve_path(
            r"T:\UDATA\45410083\SaveMeta.xbx"
        )
        self.assertEqual(entry.directory_cluster, 3)
        self.assertEqual(self.volume.read_file(entry), b"test")

    def test_classifies_real_fatx_cluster_numbers(self) -> None:
        cluster_3_offset = self.volume.cluster_offset(3)
        location = self.volume.classify_offset(cluster_3_offset + 7)
        self.assertEqual(location.area, "data")
        self.assertEqual(location.cluster, 3)
        self.assertEqual(location.offset_in_cluster, 7)

    def test_zero_directory_marker_stops_stale_entries(self) -> None:
        data = bytearray(_make_synthetic_fatx())
        file_area = 0x2000
        data[file_area + 0x40] = 0x00
        stale = _make_dirent("DEADBEEF", 0x10, 2, 0)
        data[file_area + 0x80 : file_area + 0xC0] = stale
        volume = FATXVolume(MemoryBlockDevice(bytes(data)), self.partition)
        root_names = [
            entry.name
            for entry in volume.iter_directory(
                volume.header.root_dir_first_cluster
            )
        ]
        self.assertEqual(root_names, ["UDATA"])


@unittest.skipUnless(
    BLACK_B1.exists() and BLACK_B2.exists(),
    "Fixture Black B1/B2 non presenti",
)
class BlackForensicIntegrationTests(unittest.TestCase):
    def test_guest_mapping_fatx_and_exact_64_byte_delta(self) -> None:
        before = {path: _sha256_file(path) for path in (BLACK_B1, BLACK_B2)}

        for path in (BLACK_B1, BLACK_B2):
            with QCOW2BlockDevice(path) as device:
                self.assertEqual(device.header.version, 3)
                self.assertEqual(device.size, 8 * 1024**3)
                self.assertEqual(device.cluster_size, 64 * 1024)
                self.assertEqual(device.map_offset(0xABE80000), 0x1A0000)
                volume = FATXVolume.open_partition(device, "E")
                save_meta = volume.find_named_entries("SaveMeta.xbx")
                self.assertIn(
                    9,
                    {item.entry.directory_cluster for item in save_meta},
                )

        summary = compare_paths(BLACK_B1, BLACK_B2)
        self.assertEqual(summary.total_different_bytes, 64)
        self.assertEqual(summary.region_totals().get("CONFIG"), 1)
        self.assertEqual(
            summary.cluster_totals("E"),
            {5: 2, 9: 2, 11: 59},
        )

        after = {path: _sha256_file(path) for path in (BLACK_B1, BLACK_B2)}
        self.assertEqual(before, after)


@unittest.skipUnless(
    os.environ.get("XEMU_LAB_RUN_SLOW") == "1"
    and HALO_H1.exists()
    and HALO_H2.exists(),
    "Impostare XEMU_LAB_RUN_SLOW=1 per il confronto H1/H2",
)
class HaloForensicIntegrationTests(unittest.TestCase):
    def test_guest_aware_partition_totals(self) -> None:
        summary = compare_paths(HALO_H1, HALO_H2, sample_limit=0)
        regions = summary.region_totals()
        self.assertEqual(summary.total_different_bytes, 428_287_103)
        self.assertEqual(regions.get("Y"), 427_278_322)
        self.assertEqual(regions.get("E"), 1_008_759)
        self.assertEqual(summary.other_than("Y", "E"), 22)


class CatalogTests(unittest.TestCase):
    @unittest.skipUnless(
        Path(r"D:\GitHub\xemu_tools\hdd_backups.json").exists(),
        "Catalogo locale non presente",
    )
    def test_unknown_t_images_are_not_given_a_meaning(self) -> None:
        entries = HDDCatalog().entries(include_unregistered=True)
        unknown = {
            entry.actual_path.name.casefold(): entry
            for entry in entries
            if not entry.registered
        }
        for filename in ("xbox_hddt1.qcow2", "xbox_hddt2.qcow2"):
            if filename in unknown:
                self.assertEqual(unknown[filename].games, ())
                self.assertIn("significato non dedotto", unknown[filename].description)


class FatxAllocAndRemapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.partition = XboxRegion("T", 0, 0x20000, "Fixture FATX")
        self.device = MemoryBlockDevice(_make_synthetic_fatx())
        self.volume = FATXVolume(self.device, self.partition)

    def test_find_free_clusters_skips_used(self) -> None:
        free = self.volume.find_free_clusters(2)
        for cluster in free:
            self.assertTrue(self.volume.is_cluster_free(cluster))
        # 1-4 sono usati nella fixture.
        self.assertTrue(min(free) >= 5)

    def test_find_directory_slot_on_end_marker(self) -> None:
        udata = self.volume.find_child(
            self.volume.header.root_dir_first_cluster, "UDATA"
        )
        assert udata is not None
        # UDATA ha solo 45410083 poi END.
        offset, dir_cluster = self.volume.find_directory_slot(udata.first_cluster)
        self.assertEqual(dir_cluster, udata.first_cluster)
        self.assertEqual(self.device.read_at(offset, 1), b"\xff")

    def test_decide_same_guest_when_clusters_free(self) -> None:
        backup = _make_toy_backup(first_cluster=5)
        decision = decide_restore_path(backup, self.volume)
        self.assertTrue(decision.use_same_guest)

    def test_decide_remap_when_clusters_occupied_by_other(self) -> None:
        # Cluster 2/3/4 sono della fixture esistente (altro titolo).
        backup = _make_toy_backup(first_cluster=2)
        decision = decide_restore_path(backup, self.volume)
        self.assertFalse(decision.use_same_guest)
        self.assertTrue(decision.colliding_clusters)

    def test_remap_installs_title_without_clobbering_existing(self) -> None:
        backup = _make_toy_backup(first_cluster=2)
        # Occupati: remap deve usare cluster >= 5.
        plan = build_remap_plan(backup, self.volume)
        self.assertEqual(plan.mode, "remap")
        self.assertNotIn(2, plan.cluster_map.values())
        for old, new in plan.cluster_map.items():
            self.assertTrue(self.volume.is_cluster_free(new))

        for guest_offset, payload in plan.pending:
            self.device.write_at(guest_offset, payload)

        # Ricarica volume sul device mutato.
        volume = FATXVolume(self.device, self.partition)
        games = {(g.area, g.title_id) for g in volume.list_games()}
        self.assertIn(("UDATA", "45410083"), games)
        self.assertIn(("UDATA", "4c410015"), games)

        new_game = volume.find_child(
            volume.find_child(
                volume.header.root_dir_first_cluster, "UDATA"
            ).first_cluster,
            "4c410015",
        )
        assert new_game is not None
        self.assertEqual(new_game.first_cluster, plan.game_first_cluster)
        entries = [e.name for e in volume.iter_directory(new_game.first_cluster)]
        self.assertEqual(entries, ["SaveMeta.xbx"])
        meta = volume.find_child(new_game.first_cluster, "SaveMeta.xbx")
        assert meta is not None
        self.assertEqual(volume.read_file(meta), b"hello")

        # Il titolo originale resta leggibile.
        old = volume.find_child(
            volume.find_child(
                volume.header.root_dir_first_cluster, "UDATA"
            ).first_cluster,
            "45410083",
        )
        assert old is not None
        save = volume.find_child(old.first_cluster, "SaveMeta.xbx")
        assert save is not None
        self.assertEqual(volume.read_file(save), b"test")


def _make_toy_backup(*, first_cluster: int) -> GameBackup:
    """Backup minimo: cartella Title + un file SaveMeta su due cluster."""

    title = "4c410015"
    dir_cluster = first_cluster
    file_cluster = first_cluster + 1
    cluster_size = 0x4000
    file_area = 0x2000

    # Dirent Title come se fosse in UDATA (fuori dai data chunk).
    title_dirent = _make_dirent(title, 0x10, dir_cluster, 0)
    title_udata_offset = 0x100  # fuori dai data cluster

    save_dirent = _make_dirent("SaveMeta.xbx", 0x20, file_cluster, 5)
    dir_payload = bytearray(cluster_size)
    dir_payload[0:64] = save_dirent
    dir_payload[64] = 0xFF

    file_payload = bytearray(cluster_size)
    file_payload[0:5] = b"hello"

    fat_blob = (0xFFFF).to_bytes(2, "little") + (0xFFFF).to_bytes(2, "little")
    fat_offset = 0x1000 + dir_cluster * 2

    return GameBackup(
        title_id=title,
        partition="E",
        source_path=Path("toy"),
        source_sha256="",
        created_at=datetime.now(timezone.utc),
        fat_entry_size=2,
        fatx_cluster_size=cluster_size,
        directory_entries=[
            (title_udata_offset, title_dirent),
            (file_area + (dir_cluster - 1) * cluster_size, save_dirent),
        ],
        fat_runs=[(dir_cluster, fat_offset, fat_blob)],
        data_chunks=[
            (
                dir_cluster,
                file_area + (dir_cluster - 1) * cluster_size,
                bytes(dir_payload),
            ),
            (
                file_cluster,
                file_area + (file_cluster - 1) * cluster_size,
                bytes(file_payload),
            ),
        ],
        format_version=7,
    )


def _make_synthetic_qcow2() -> bytes:
    cluster_bits = 12
    cluster_size = 1 << cluster_bits
    image = bytearray(cluster_size * 6)
    virtual_size = cluster_size * 8
    l1_offset = cluster_size * 2
    l2_offset = cluster_size * 3

    struct.pack_into(">I", image, 0, QCOW2_MAGIC)
    struct.pack_into(">I", image, 4, 3)
    struct.pack_into(">Q", image, 8, 0)
    struct.pack_into(">I", image, 16, 0)
    struct.pack_into(">I", image, 20, cluster_bits)
    struct.pack_into(">Q", image, 24, virtual_size)
    struct.pack_into(">I", image, 32, 0)
    struct.pack_into(">I", image, 36, 1)
    struct.pack_into(">Q", image, 40, l1_offset)
    struct.pack_into(">Q", image, 48, cluster_size)
    struct.pack_into(">I", image, 56, 1)
    struct.pack_into(">I", image, 60, 0)
    struct.pack_into(">Q", image, 64, 0)
    struct.pack_into(">Q", image, 72, 0)
    struct.pack_into(">Q", image, 80, 0)
    struct.pack_into(">Q", image, 88, 0)
    struct.pack_into(">I", image, 96, 4)
    struct.pack_into(">I", image, 100, 104)

    struct.pack_into(">Q", image, l1_offset, QCOW_OFLAG_COPIED | l2_offset)
    struct.pack_into(
        ">Q",
        image,
        l2_offset,
        QCOW_OFLAG_COPIED | cluster_size * 4,
    )
    struct.pack_into(">Q", image, l2_offset + 8, 0)
    struct.pack_into(">Q", image, l2_offset + 16, QCOW_OFLAG_ZERO)
    struct.pack_into(
        ">Q",
        image,
        l2_offset + 24,
        QCOW_OFLAG_COPIED | cluster_size * 5,
    )

    image[cluster_size * 4 : cluster_size * 5] = bytes(range(256)) * 16
    image[cluster_size * 5 : cluster_size * 6] = b"D" * cluster_size
    return bytes(image)


def _make_synthetic_qcow2_with_refcounts() -> bytes:
    """Fixture con refcount coerenti, unalloc/zero/compresso e L1 sparso."""

    cluster_bits = 12
    cluster_size = 1 << cluster_bits
    # Host layout:
    # 0 header, 1 refcount table, 2 refcount block, 3 L1, 4 L2,
    # 5 data guest0, 6 compressed payload guest4
    host_clusters = 7
    image = bytearray(cluster_size * host_clusters)
    # Guest 0..512 coperti da due entry L1 (512 entry/L2).
    virtual_size = cluster_size * 513
    refcount_table_offset = cluster_size * 1
    refcount_block_offset = cluster_size * 2
    l1_offset = cluster_size * 3
    l2_offset = cluster_size * 4
    data0_offset = cluster_size * 5
    compressed_host = cluster_size * 6

    struct.pack_into(">I", image, 0, QCOW2_MAGIC)
    struct.pack_into(">I", image, 4, 3)
    struct.pack_into(">Q", image, 8, 0)
    struct.pack_into(">I", image, 16, 0)
    struct.pack_into(">I", image, 20, cluster_bits)
    struct.pack_into(">Q", image, 24, virtual_size)
    struct.pack_into(">I", image, 32, 0)
    struct.pack_into(">I", image, 36, 2)  # l1_size
    struct.pack_into(">Q", image, 40, l1_offset)
    struct.pack_into(">Q", image, 48, refcount_table_offset)
    struct.pack_into(">I", image, 56, 1)  # refcount_table_clusters
    struct.pack_into(">I", image, 60, 0)
    struct.pack_into(">Q", image, 64, 0)
    struct.pack_into(">Q", image, 72, 0)
    struct.pack_into(">Q", image, 80, 0)
    struct.pack_into(">Q", image, 88, 0)
    struct.pack_into(">I", image, 96, 4)  # refcount_order -> 16-bit
    struct.pack_into(">I", image, 100, 104)

    struct.pack_into(">Q", image, refcount_table_offset, refcount_block_offset)
    for host_index in range(host_clusters):
        struct.pack_into(
            ">H",
            image,
            refcount_block_offset + host_index * 2,
            1,
        )

    struct.pack_into(">Q", image, l1_offset, QCOW_OFLAG_COPIED | l2_offset)
    # L1[1] = 0 → allocate dovrà creare la L2 per guest 512.

    # Guest 0: allocato
    struct.pack_into(
        ">Q",
        image,
        l2_offset,
        QCOW_OFLAG_COPIED | data0_offset,
    )
    # Guest 1: unallocated
    struct.pack_into(">Q", image, l2_offset + 8, 0)
    # Guest 2: zero
    struct.pack_into(">Q", image, l2_offset + 16, QCOW_OFLAG_ZERO)
    # Guest 3: allocato (riusa data0 per semplicità di lettura)
    struct.pack_into(
        ">Q",
        image,
        l2_offset + 24,
        QCOW_OFLAG_COPIED | data0_offset,
    )

    plain = b"C" * cluster_size
    compressor = zlib.compressobj(level=9, wbits=-12)
    compressed = compressor.compress(plain) + compressor.flush()
    image[compressed_host : compressed_host + len(compressed)] = compressed
    size_bits = cluster_bits - 8
    csize_shift = 62 - size_bits
    sectors = (len(compressed) + 511) // 512
    additional_sectors = max(0, sectors - 1)
    compressed_entry = (
        QCOW_OFLAG_COMPRESSED
        | (additional_sectors << csize_shift)
        | compressed_host
    )
    # Guest 4: compresso
    struct.pack_into(">Q", image, l2_offset + 32, compressed_entry)

    image[data0_offset : data0_offset + cluster_size] = bytes(range(256)) * 16
    return bytes(image)


def _make_synthetic_fatx() -> bytes:
    data = bytearray(0x20000)
    struct.pack_into("<4sIII", data, 0, b"FATX", 0x12345678, 0x20, 1)

    fat_offset = 0x1000
    struct.pack_into("<H", data, fat_offset, 0xFFF8)
    for cluster in (1, 2, 3, 4):
        struct.pack_into("<H", data, fat_offset + cluster * 2, 0xFFFF)

    file_area = 0x2000
    _put_directory(
        data,
        file_area,
        [_make_dirent("UDATA", 0x10, 2, 0)],
    )
    _put_directory(
        data,
        file_area + 0x4000,
        [_make_dirent("45410083", 0x10, 3, 0)],
    )
    _put_directory(
        data,
        file_area + 0x8000,
        [_make_dirent("SaveMeta.xbx", 0x20, 4, 4)],
    )
    data[file_area + 0xC000 : file_area + 0xC004] = b"test"
    return bytes(data)


def _make_dirent(
    name: str,
    attributes: int,
    first_cluster: int,
    file_size: int,
) -> bytes:
    encoded = name.encode("latin-1")
    entry = bytearray(0x40)
    entry[0] = len(encoded)
    entry[1] = attributes
    entry[2 : 2 + len(encoded)] = encoded
    struct.pack_into("<II", entry, 44, first_cluster, file_size)
    return bytes(entry)


def _put_directory(data: bytearray, offset: int, entries: list[bytes]) -> None:
    for index, entry in enumerate(entries):
        start = offset + index * 0x40
        data[start : start + 0x40] = entry
    data[offset + len(entries) * 0x40] = 0xFF


def _sha256_file(path: Path) -> bytes:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                return digest.digest()
            digest.update(chunk)


if __name__ == "__main__":
    unittest.main()
