"""Lettore QCOW2 strettamente read-only.

Il resto del progetto deve ragionare esclusivamente in offset del disco guest.
Questo modulo è l'unico punto che traduce tali offset in posizioni del
contenitore QCOW2.
"""

from __future__ import annotations

import os
import struct
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator, Optional, Protocol, Tuple, Union


PathLike = Union[str, os.PathLike]

QCOW2_MAGIC = 0x514649FB
QCOW2_MIN_CLUSTER_BITS = 9
QCOW2_MAX_CLUSTER_BITS = 21
QCOW2_MAX_L1_BYTES = 32 * 1024 * 1024
QCOW2_MAX_CACHED_L2_TABLES = 32

QCOW_OFLAG_COPIED = 1 << 63
QCOW_OFLAG_COMPRESSED = 1 << 62
QCOW_OFLAG_ZERO = 1
QCOW_OFFSET_MASK = 0x00FFFFFFFFFFFE00

QCOW2_INCOMPAT_DIRTY = 1 << 0
QCOW2_INCOMPAT_CORRUPT = 1 << 1
QCOW2_INCOMPAT_EXTERNAL_DATA = 1 << 2
QCOW2_INCOMPAT_COMPRESSION_TYPE = 1 << 3
QCOW2_INCOMPAT_EXTENDED_L2 = 1 << 4
QCOW2_KNOWN_INCOMPAT = (
    QCOW2_INCOMPAT_DIRTY
    | QCOW2_INCOMPAT_CORRUPT
    | QCOW2_INCOMPAT_EXTERNAL_DATA
    | QCOW2_INCOMPAT_COMPRESSION_TYPE
    | QCOW2_INCOMPAT_EXTENDED_L2
)


class QCOW2Error(Exception):
    """Errore base del block device QCOW2."""


class QCOW2FormatError(QCOW2Error):
    """Il contenitore non rispetta il formato QCOW2 atteso."""


class UnsupportedQCOW2Feature(QCOW2Error):
    """Il contenitore usa una funzione non supportata in sicurezza."""


class BlockDevice(Protocol):
    """Interfaccia minima usata dai parser guest-aware."""

    @property
    def size(self) -> int:
        """Dimensione del disco guest in byte."""

    def read_at(self, offset: int, size: int) -> bytes:
        """Legge byte a un offset del disco guest."""


@dataclass(frozen=True)
class QCOW2Header:
    version: int
    backing_file_offset: int
    backing_file_size: int
    cluster_bits: int
    cluster_size: int
    virtual_size: int
    crypt_method: int
    l1_size: int
    l1_table_offset: int
    refcount_table_offset: int
    refcount_table_clusters: int
    snapshot_count: int
    snapshots_offset: int
    incompatible_features: int
    compatible_features: int
    autoclear_features: int
    refcount_order: int
    header_length: int
    compression_type: int

    @property
    def is_dirty(self) -> bool:
        return bool(self.incompatible_features & QCOW2_INCOMPAT_DIRTY)


@dataclass(frozen=True)
class ClusterMapping:
    """Traduzione di un cluster guest standard."""

    guest_cluster: int
    guest_offset: int
    host_offset: Optional[int]
    allocated: bool
    reads_as_zero: bool


class QCOW2BlockDevice:
    """Block device QCOW2 senza alcuna API di scrittura."""

    def __init__(self, path: PathLike):
        self.path = Path(path)
        self._file: Optional[BinaryIO] = None
        self._host_size = 0
        self._header: Optional[QCOW2Header] = None
        self._l1_table: Tuple[int, ...] = ()
        self._l2_cache: "OrderedDict[int, Tuple[int, ...]]" = OrderedDict()

    def __enter__(self) -> "QCOW2BlockDevice":
        return self.open()

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def open(self) -> "QCOW2BlockDevice":
        if self._file is not None:
            return self

        try:
            self._file = self.path.open("rb")
            self._host_size = os.fstat(self._file.fileno()).st_size
            self._header = self._read_header()
            self._l1_table = self._read_l1_table()
            self._validate_l1_coverage()
        except Exception:
            self.close()
            raise
        return self

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
        self._file = None
        self._host_size = 0
        self._header = None
        self._l1_table = ()
        self._l2_cache.clear()

    @property
    def header(self) -> QCOW2Header:
        self._require_open()
        assert self._header is not None
        return self._header

    @property
    def size(self) -> int:
        return self.header.virtual_size

    @property
    def cluster_size(self) -> int:
        return self.header.cluster_size

    @property
    def cluster_count(self) -> int:
        return (self.size + self.cluster_size - 1) // self.cluster_size

    @property
    def host_size(self) -> int:
        self._require_open()
        return self._host_size

    def read_at(self, offset: int, size: int) -> bytes:
        """Legge un intervallo guest, attraversando correttamente L1/L2."""

        self._validate_guest_range(offset, size)
        if size == 0:
            return b""

        result = bytearray(size)
        result_offset = 0
        while result_offset < size:
            guest_offset = offset + result_offset
            guest_cluster = guest_offset // self.cluster_size
            in_cluster = guest_offset % self.cluster_size
            chunk_size = min(size - result_offset, self.cluster_size - in_cluster)
            mapping = self.map_cluster(guest_cluster)

            if mapping.allocated and not mapping.reads_as_zero:
                assert mapping.host_offset is not None
                chunk = self._read_exact_host(
                    mapping.host_offset + in_cluster,
                    chunk_size,
                )
                result[result_offset : result_offset + chunk_size] = chunk

            result_offset += chunk_size

        return bytes(result)

    def read_cluster(self, guest_cluster: int) -> bytes:
        if not isinstance(guest_cluster, int) or guest_cluster < 0:
            raise ValueError("Il numero del cluster guest deve essere >= 0")
        if guest_cluster >= self.cluster_count:
            raise ValueError("Cluster guest oltre la dimensione virtuale")

        guest_offset = guest_cluster * self.cluster_size
        return self.read_at(
            guest_offset,
            min(self.cluster_size, self.size - guest_offset),
        )

    def map_cluster(self, guest_cluster: int) -> ClusterMapping:
        """Restituisce il mapping del cluster guest, senza leggere i dati."""

        if not isinstance(guest_cluster, int) or guest_cluster < 0:
            raise ValueError("Il numero del cluster guest deve essere >= 0")
        guest_offset = guest_cluster * self.cluster_size
        l2_entry = self.raw_l2_entry(guest_cluster)

        if l2_entry == 0:
            return ClusterMapping(
                guest_cluster,
                guest_offset,
                None,
                allocated=False,
                reads_as_zero=True,
            )
        if l2_entry & QCOW_OFLAG_COMPRESSED:
            raise UnsupportedQCOW2Feature(
                f"Cluster guest {guest_cluster} compresso: lettura non supportata"
            )
        if self.header.version == 2 and l2_entry & QCOW_OFLAG_ZERO:
            raise QCOW2FormatError(
                f"Bit ZERO non valido in QCOW2 v2 al cluster {guest_cluster}"
            )

        l2_reserved = l2_entry & ~(
            QCOW_OFLAG_COPIED | QCOW_OFLAG_ZERO | QCOW_OFFSET_MASK
        )
        if l2_reserved:
            raise QCOW2FormatError(
                f"Entry L2 per cluster {guest_cluster} con bit riservati: "
                f"0x{l2_reserved:x}"
            )

        reads_as_zero = bool(l2_entry & QCOW_OFLAG_ZERO)
        host_offset = l2_entry & QCOW_OFFSET_MASK
        if host_offset == 0:
            return ClusterMapping(
                guest_cluster,
                guest_offset,
                None,
                allocated=False,
                reads_as_zero=True,
            )

        self._validate_host_cluster_offset(host_offset, "cluster dati")
        return ClusterMapping(
            guest_cluster,
            guest_offset,
            host_offset,
            allocated=True,
            reads_as_zero=reads_as_zero,
        )

    def raw_l2_entry(self, guest_cluster: int) -> int:
        """Restituisce il descriptor L2 per diagnostica read-only."""

        self._require_open()
        if not isinstance(guest_cluster, int) or guest_cluster < 0:
            raise ValueError("Il numero del cluster guest deve essere >= 0")
        if guest_cluster >= self.cluster_count:
            raise ValueError("Cluster guest oltre la dimensione virtuale")

        entries_per_l2 = self.cluster_size // 8
        l1_index, l2_index = divmod(guest_cluster, entries_per_l2)
        if l1_index >= len(self._l1_table):
            raise QCOW2FormatError("La tabella L1 non copre il disco guest")

        l1_entry = self._l1_table[l1_index]
        if l1_entry == 0:
            return 0

        l1_reserved = l1_entry & ~(QCOW_OFLAG_COPIED | QCOW_OFFSET_MASK)
        if l1_reserved:
            raise QCOW2FormatError(
                f"Entry L1 {l1_index} con bit riservati: 0x{l1_reserved:x}"
            )

        l2_table_offset = l1_entry & QCOW_OFFSET_MASK
        self._validate_host_cluster_offset(l2_table_offset, "tabella L2")
        return self._get_l2_table(l1_index, l2_table_offset)[l2_index]

    def is_compressed_cluster(self, guest_cluster: int) -> bool:
        return bool(self.raw_l2_entry(guest_cluster) & QCOW_OFLAG_COMPRESSED)

    def read_compressed_payload(self, guest_cluster: int) -> bytes:
        """Legge il payload compresso senza interpretarlo o decomprimerlo."""

        entry = self.raw_l2_entry(guest_cluster)
        if not entry & QCOW_OFLAG_COMPRESSED:
            raise ValueError(f"Cluster guest {guest_cluster} non compresso")

        size_bits = self.cluster_size.bit_length() - 1 - 8
        csize_shift = 62 - size_bits
        host_offset_mask = (1 << csize_shift) - 1
        additional_sector_mask = (1 << size_bits) - 1
        host_offset = entry & host_offset_mask
        additional_sectors = (
            entry >> csize_shift
        ) & additional_sector_mask
        compressed_size = (
            (additional_sectors + 1) * 512 - (host_offset & 511)
        )

        if compressed_size <= 0 or compressed_size > self.cluster_size * 2:
            raise QCOW2FormatError(
                f"Dimensione compressa non valida: {compressed_size}"
            )
        return self._read_exact_host(host_offset, compressed_size)

    def map_offset(self, guest_offset: int) -> Optional[int]:
        """Traduce un byte guest nel corrispondente offset host fisico."""

        self._validate_guest_range(guest_offset, 1)
        mapping = self.map_cluster(guest_offset // self.cluster_size)
        if not mapping.allocated or mapping.reads_as_zero:
            return None
        assert mapping.host_offset is not None
        return mapping.host_offset + (guest_offset % self.cluster_size)

    def iter_mappings(self) -> Iterator[ClusterMapping]:
        for guest_cluster in range(self.cluster_count):
            yield self.map_cluster(guest_cluster)

    def _read_header(self) -> QCOW2Header:
        prefix = self._read_exact_host(0, 72)
        magic, version = struct.unpack_from(">II", prefix, 0)
        if magic != QCOW2_MAGIC:
            raise QCOW2FormatError("Magic QCOW2 non valida")
        if version not in (2, 3):
            raise UnsupportedQCOW2Feature(
                f"Versione QCOW2 {version} non supportata"
            )

        backing_file_offset = struct.unpack_from(">Q", prefix, 8)[0]
        backing_file_size = struct.unpack_from(">I", prefix, 16)[0]
        cluster_bits = struct.unpack_from(">I", prefix, 20)[0]
        virtual_size = struct.unpack_from(">Q", prefix, 24)[0]
        crypt_method = struct.unpack_from(">I", prefix, 32)[0]
        l1_size = struct.unpack_from(">I", prefix, 36)[0]
        l1_table_offset = struct.unpack_from(">Q", prefix, 40)[0]
        refcount_table_offset = struct.unpack_from(">Q", prefix, 48)[0]
        refcount_table_clusters = struct.unpack_from(">I", prefix, 56)[0]
        snapshot_count = struct.unpack_from(">I", prefix, 60)[0]
        snapshots_offset = struct.unpack_from(">Q", prefix, 64)[0]

        if not QCOW2_MIN_CLUSTER_BITS <= cluster_bits <= QCOW2_MAX_CLUSTER_BITS:
            raise QCOW2FormatError(
                f"cluster_bits fuori intervallo: {cluster_bits}"
            )
        cluster_size = 1 << cluster_bits
        if virtual_size <= 0:
            raise QCOW2FormatError("Dimensione virtuale non valida")
        if crypt_method != 0:
            raise UnsupportedQCOW2Feature("QCOW2 cifrato non supportato")
        if backing_file_offset or backing_file_size:
            raise UnsupportedQCOW2Feature("Backing file QCOW2 non supportato")
        if l1_size <= 0:
            raise QCOW2FormatError("Tabella L1 vuota")
        if l1_size * 8 > QCOW2_MAX_L1_BYTES:
            raise QCOW2FormatError("Tabella L1 oltre il limite di sicurezza")
        if l1_table_offset == 0:
            raise QCOW2FormatError("Offset tabella L1 nullo")
        if l1_table_offset % cluster_size:
            raise QCOW2FormatError("Tabella L1 non allineata a un cluster")

        incompatible_features = 0
        compatible_features = 0
        autoclear_features = 0
        refcount_order = 4
        header_length = 72
        compression_type = 0

        if version == 3:
            version3 = self._read_exact_host(72, 32)
            incompatible_features = struct.unpack_from(">Q", version3, 0)[0]
            compatible_features = struct.unpack_from(">Q", version3, 8)[0]
            autoclear_features = struct.unpack_from(">Q", version3, 16)[0]
            refcount_order = struct.unpack_from(">I", version3, 24)[0]
            header_length = struct.unpack_from(">I", version3, 28)[0]

            if header_length < 104 or header_length > cluster_size:
                raise QCOW2FormatError(
                    f"Lunghezza header v3 non valida: {header_length}"
                )
            if header_length % 8:
                raise QCOW2FormatError(
                    f"Lunghezza header v3 non allineata: {header_length}"
                )
            if header_length > self._host_size:
                raise QCOW2FormatError("Header oltre la fine del file host")
            if refcount_order > 6:
                raise QCOW2FormatError(
                    f"refcount_order non valido: {refcount_order}"
                )
            if header_length >= 112:
                additional_header = self._read_exact_host(104, 8)
                compression_type = additional_header[0]
                if any(additional_header[1:]):
                    raise QCOW2FormatError(
                        "Padding header QCOW2 v3 non nullo"
                    )

            unknown = incompatible_features & ~QCOW2_KNOWN_INCOMPAT
            if unknown:
                raise UnsupportedQCOW2Feature(
                    f"Feature incompatibili sconosciute: 0x{unknown:x}"
                )
            if incompatible_features & QCOW2_INCOMPAT_CORRUPT:
                raise QCOW2FormatError("QCOW2 marcato come corrotto")
            if incompatible_features & QCOW2_INCOMPAT_EXTERNAL_DATA:
                raise UnsupportedQCOW2Feature(
                    "QCOW2 con file dati esterno non supportato"
                )
            if incompatible_features & QCOW2_INCOMPAT_EXTENDED_L2:
                raise UnsupportedQCOW2Feature(
                    "QCOW2 con entry L2 estese non supportato"
                )
            if incompatible_features & QCOW2_INCOMPAT_COMPRESSION_TYPE:
                if compression_type == 0:
                    raise QCOW2FormatError(
                        "Feature compression type senza tipo non-default"
                    )
                raise UnsupportedQCOW2Feature(
                    f"Compressione QCOW2 tipo {compression_type} non supportata"
                )
            if compression_type != 0:
                raise QCOW2FormatError(
                    "compression_type presente senza feature incompatibile"
                )

        return QCOW2Header(
            version=version,
            backing_file_offset=backing_file_offset,
            backing_file_size=backing_file_size,
            cluster_bits=cluster_bits,
            cluster_size=cluster_size,
            virtual_size=virtual_size,
            crypt_method=crypt_method,
            l1_size=l1_size,
            l1_table_offset=l1_table_offset,
            refcount_table_offset=refcount_table_offset,
            refcount_table_clusters=refcount_table_clusters,
            snapshot_count=snapshot_count,
            snapshots_offset=snapshots_offset,
            incompatible_features=incompatible_features,
            compatible_features=compatible_features,
            autoclear_features=autoclear_features,
            refcount_order=refcount_order,
            header_length=header_length,
            compression_type=compression_type,
        )

    def _read_l1_table(self) -> Tuple[int, ...]:
        header = self.header
        byte_count = header.l1_size * 8
        if header.l1_table_offset + byte_count > self._host_size:
            raise QCOW2FormatError("Tabella L1 troncata")
        raw = self._read_exact_host(header.l1_table_offset, byte_count)
        return struct.unpack(f">{header.l1_size}Q", raw)

    def _validate_l1_coverage(self) -> None:
        entries_per_l2 = self.cluster_size // 8
        required_l1 = (
            self.cluster_count + entries_per_l2 - 1
        ) // entries_per_l2
        if len(self._l1_table) < required_l1:
            raise QCOW2FormatError(
                f"Tabella L1 troppo corta: {len(self._l1_table)} < {required_l1}"
            )

    def _get_l2_table(
        self,
        l1_index: int,
        l2_table_offset: int,
    ) -> Tuple[int, ...]:
        cached = self._l2_cache.get(l1_index)
        if cached is not None:
            self._l2_cache.move_to_end(l1_index)
            return cached

        raw = self._read_exact_host(l2_table_offset, self.cluster_size)
        entries_per_l2 = self.cluster_size // 8
        table = struct.unpack(f">{entries_per_l2}Q", raw)
        self._l2_cache[l1_index] = table
        self._l2_cache.move_to_end(l1_index)
        while len(self._l2_cache) > QCOW2_MAX_CACHED_L2_TABLES:
            self._l2_cache.popitem(last=False)
        return table

    def _validate_host_cluster_offset(self, offset: int, label: str) -> None:
        if offset == 0:
            raise QCOW2FormatError(f"Offset nullo per {label}")
        if offset % self.cluster_size:
            raise QCOW2FormatError(f"Offset non allineato per {label}: 0x{offset:x}")
        if offset + self.cluster_size > self._host_size:
            raise QCOW2FormatError(f"{label.capitalize()} oltre il file host")

    def _validate_guest_range(self, offset: int, size: int) -> None:
        self._require_open()
        if not isinstance(offset, int) or not isinstance(size, int):
            raise TypeError("Offset e dimensione devono essere interi")
        if offset < 0 or size < 0:
            raise ValueError("Offset e dimensione devono essere >= 0")
        if offset > self.size or size > self.size - offset:
            raise ValueError("Lettura oltre la dimensione del disco guest")

    def _read_exact_host(self, offset: int, size: int) -> bytes:
        self._require_open()
        if offset < 0 or size < 0 or offset > self._host_size:
            raise QCOW2FormatError("Intervallo host non valido")
        if size > self._host_size - offset:
            raise QCOW2FormatError("Lettura oltre la fine del file host")

        assert self._file is not None
        self._file.seek(offset)
        data = self._file.read(size)
        if len(data) != size:
            raise QCOW2FormatError(
                f"Lettura host troncata: richiesti {size}, ottenuti {len(data)}"
            )
        return data

    def _require_open(self) -> None:
        if self._file is None:
            raise QCOW2Error("Block device non aperto; usare il context manager")
