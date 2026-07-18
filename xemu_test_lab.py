#!/usr/bin/env python3
"""Ingresso unico del laboratorio sicuro QCOW2/FATX per xemu."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

from xemu_lab.backup import (
    DEFAULT_BACKUP_DIR,
    BackupError,
    backup_display_label,
    backup_title_id_from_path,
    list_backups,
    load_backup,
    save_backup,
)
from xemu_lab.titles import game_display_name
from xemu_lab.catalog import (
    CatalogEntry,
    HDDCatalog,
    read_xemu_hdd_path,
)
from xemu_lab.compare import GuestDiffSummary, compare_paths
from xemu_lab.fatx import (
    FATXError,
    FATXVolume,
    XBOX_REGIONS,
    discover_fatx_volumes,
)
from xemu_lab.qcow2 import (
    QCOW2BlockDevice,
    QCOW2Error,
    UnsupportedQCOW2Feature,
)
from xemu_lab.restore import RestoreError, restore_backup_to_path
from xemu_lab.safety import (
    SafetyError,
    assert_not_golden,
    assert_xemu_closed,
    atomic_copy_qcow2,
    rollback_active_from_golden,
)
from xemu_lab.titles import list_games_on_image


EXPECTED_GUEST_SIZE = 8 * 1024 * 1024 * 1024
EXPECTED_QCOW2_CLUSTER_SIZE = 64 * 1024
PARTITION_E_OFFSET = 0xABE80000
MERCENARIES_TITLE_ID = "4c410015"
DEFAULT_CYCLE_SCENARIO = "1"

BLACK_EXPECTED_TOTAL = 64
BLACK_EXPECTED_CONFIG = 1
BLACK_EXPECTED_CLUSTERS = {5: 2, 9: 2, 11: 59}

HALO_EXPECTED_TOTAL = 428_287_103
HALO_EXPECTED_Y = 427_278_322
HALO_EXPECTED_E = 1_008_759
HALO_EXPECTED_OTHER = 22


@dataclass(frozen=True)
class LabResult:
    timestamp: datetime
    name: str
    passed: Optional[bool]
    details: Tuple[str, ...]


class XemuTestLab:
    def __init__(self, catalog: Optional[HDDCatalog] = None):
        self.catalog = catalog or HDDCatalog()
        self.results: List[LabResult] = []

    def run(self) -> None:
        self._print_banner()
        while True:
            print()
            print("MENU PRINCIPALE")
            print("  1. Ciclo guidato HDD1 Mercenaries")
            print("  2. Solo backup save (da golden, rb)")
            print("  3. Solo restore save (solo HDD attivo)")
            print("  4. Ripristina HDD attivo da golden")
            print("  5. Analizza/confronta HDD")
            print("  6. Catalogo HDD e risultati")
            print("  0. Esci")
            choice = input("\nScelta: ").strip()

            if choice == "0":
                print("Uscita.")
                return
            if choice == "1":
                self._guided_cycle_hdd1()
            elif choice == "2":
                self._menu_backup_save()
            elif choice == "3":
                self._menu_restore_save()
            elif choice == "4":
                self._menu_copy_golden_to_active()
            elif choice == "5":
                self._analysis_menu()
            elif choice == "6":
                self._show_catalog_and_results()
            else:
                print("Scelta non valida.")

    def _print_banner(self) -> None:
        print("=" * 72)
        print("XEMU TEST LAB - QCOW2/FATX guest-aware (QEMU-free)")
        print("=" * 72)
        print("FASE ATTUALE: lettura + scrittura overwrite su cluster allocati.")
        print(
            "Archivio HDD (golden, mai in scrittura): "
            f"{self.catalog.config.backup_folder}"
        )
        print(f"HDD attivo:      {self.catalog.config.target_path}")
        print(f"Backup v6:       {DEFAULT_BACKUP_DIR}")
        print("Niente qemu-img. I golden in D:\\xemu\\bk non vengono aperti in scrittura.")

    def _guided_cycle_hdd1(self) -> None:
        print()
        print("CICLO GUIDATO HDD1 / Mercenaries")
        print(
            "Sequenza: backup da golden → copia su attivo → "
            "(pausa cancellazione save) → restore → test → rollback opzionale."
        )
        try:
            assert_xemu_closed()
            golden = self.catalog.find(DEFAULT_CYCLE_SCENARIO)
            if not golden.exists:
                raise FileNotFoundError("HDD 1 golden non trovato")
            active = self.catalog.config.target_path
            title_id = MERCENARIES_TITLE_ID

            print(f"\n[1/5] Backup {title_id} da {golden.actual_path.name}...")
            backup = backup_title_id_from_path(golden.actual_path, title_id)
            bin_path, json_path = save_backup(backup)
            print(
                f"  OK: {backup.cluster_count} cluster, "
                f"{backup.directory_entry_count} dir entries"
            )
            print(f"  {bin_path}")

            print(f"\n[2/5] Copia atomica golden → attivo...")
            copy_report = atomic_copy_qcow2(
                golden.actual_path,
                active,
                self.catalog.config.backup_folder,
            )
            print(f"  OK sha256={copy_report.sha256[:16]}...")

            print()
            print("[3/5] PAUSA MANUALE")
            print("  1. Avvia xemu sull'HDD attivo appena copiato.")
            print("  2. Cancella il save di Mercenaries in gioco.")
            print("  3. Chiudi xemu completamente.")
            input("Premi INVIO solo quando xemu è chiuso e il save è cancellato...")
            assert_xemu_closed()

            print(f"\n[4/5] Restore {title_id} sull'HDD attivo...")
            assert_not_golden(active, self.catalog.config.backup_folder)
            report = restore_backup_to_path(backup, active, verify=True)
            print(
                f"  OK: dir={report.directory_entries}, "
                f"fat_bytes={report.fat_bytes}, "
                f"clusters={report.data_clusters}, "
                f"verified={report.verified}"
            )

            print()
            print("[5/5] TEST IN XEMU")
            print("  Avvia xemu e verifica che Mercenaries carichi il save.")
            print("  Non usare B1/B2 come golden: questo ciclo usa solo HDD 1.")
            answer = input(
                "Rollback (ricopia HDD1 sull'attivo) ora? (s/N): "
            ).strip().lower()
            if answer in {"s", "y"}:
                assert_xemu_closed()
                rb = rollback_active_from_golden(
                    golden.actual_path,
                    active,
                    self.catalog.config.backup_folder,
                )
                print(f"  Rollback OK sha256={rb.sha256[:16]}...")
                details = (
                    f"Backup {bin_path.name}",
                    "Restore completato poi rollback eseguito",
                )
            else:
                details = (
                    f"Backup {bin_path.name}",
                    f"Restore verificato su {active.name}",
                    "Rollback non richiesto",
                )

            self._record_and_print(
                LabResult(
                    timestamp=datetime.now(),
                    name="Ciclo guidato HDD1 Mercenaries",
                    passed=True,
                    details=details,
                )
            )
        except (
            SafetyError,
            BackupError,
            RestoreError,
            FileNotFoundError,
            KeyError,
            OSError,
            QCOW2Error,
            FATXError,
            ValueError,
        ) as exc:
            self._record_and_print(
                LabResult(
                    timestamp=datetime.now(),
                    name="Ciclo guidato HDD1 Mercenaries",
                    passed=False,
                    details=(f"{type(exc).__name__}: {exc}",),
                )
            )
        self._pause()

    def _menu_backup_save(self) -> None:
        print()
        print("BACKUP SAVE (golden in sola lettura → XBSV v6)")
        path = self._select_golden_image("Golden da cui estrarre il save")
        if path is None:
            return
        title_id = self._select_title_id_from_image(path)
        if title_id is None:
            return
        try:
            backup = backup_title_id_from_path(path, title_id)
            bin_path, json_path = save_backup(backup)
            self._record_and_print(
                LabResult(
                    timestamp=datetime.now(),
                    name=f"Backup {title_id}",
                    passed=True,
                    details=(
                        f"Sorgente: {path}",
                        f"Cluster: {backup.cluster_count}",
                        f"Dir entries: {backup.directory_entry_count}",
                        f"File: {bin_path.name}",
                        f"Meta: {json_path.name}",
                    ),
                )
            )
        except (BackupError, OSError, QCOW2Error, FATXError, ValueError) as exc:
            print(f"ERRORE: {type(exc).__name__}: {exc}")
        self._pause()

    def _select_title_id_from_image(self, path: Path) -> Optional[str]:
        """Scansiona UDATA e propone i giochi con nome (come il merger v5.5)."""

        print()
        print(f"Scansione giochi su: {path.name}")
        try:
            games = list_games_on_image(path, areas=("UDATA",))
        except (OSError, QCOW2Error, FATXError, ValueError) as exc:
            print(f"ERRORE scansione: {type(exc).__name__}: {exc}")
            return None

        if not games:
            print("Nessun Title ID trovato in E:\\UDATA.")
            return None

        print("\nGiochi disponibili:")
        for index, game in enumerate(games, start=1):
            print(
                f"  {index:2}. {game.title_id}: {game.name} "
                f"(cluster {game.first_cluster})"
            )
        print("   0. Annulla")
        choice = input("Numero gioco: ").strip()
        if choice == "0" or not choice:
            return None
        try:
            index = int(choice) - 1
        except ValueError:
            print("Selezione non valida.")
            return None
        if not 0 <= index < len(games):
            print("Selezione non valida.")
            return None
        return games[index].title_id

    def _menu_restore_save(self) -> None:
        print()
        print("RESTORE SAVE (solo HDD attivo, overwrite cluster allocati)")
        active = self.catalog.config.target_path
        backups = list_backups()
        if not backups:
            print(f"Nessun backup v6 in {DEFAULT_BACKUP_DIR}")
            self._pause()
            return
        for index, meta_path in enumerate(backups, start=1):
            print(f"  {index:2}. {backup_display_label(meta_path)}")
        print("   0. Annulla")
        choice = input("Selezione: ").strip()
        try:
            index = int(choice) - 1
        except ValueError:
            print("Selezione non valida.")
            self._pause()
            return
        if index < 0 or index >= len(backups):
            print("Annullato.")
            self._pause()
            return
        meta_path = backups[index]
        try:
            assert_xemu_closed()
            assert_not_golden(active, self.catalog.config.backup_folder)
            info = json.loads(meta_path.read_text(encoding="utf-8"))
            bin_path = meta_path.with_name(info["bin_file"])
            backup = load_backup(bin_path, json_path=meta_path)
            label = backup_display_label(meta_path)
            print(f"Target: {active}")
            confirm = input(
                f"Confermi restore di {label}? (s/N): "
            ).strip().lower()
            if confirm not in {"s", "y"}:
                print("Annullato.")
                self._pause()
                return
            report = restore_backup_to_path(backup, active, verify=True)
            self._record_and_print(
                LabResult(
                    timestamp=datetime.now(),
                    name=f"Restore {game_display_name(backup.title_id)}",
                    passed=True,
                    details=(
                        f"Target: {active}",
                        f"Dir={report.directory_entries} "
                        f"fat_bytes={report.fat_bytes} "
                        f"clusters={report.data_clusters}",
                        f"verified={report.verified}",
                    ),
                )
            )
        except (
            SafetyError,
            BackupError,
            RestoreError,
            OSError,
            QCOW2Error,
            KeyError,
            ValueError,
        ) as exc:
            print(f"ERRORE: {type(exc).__name__}: {exc}")
        self._pause()

    def _menu_copy_golden_to_active(self) -> None:
        print()
        print("COPIA GOLDEN → HDD ATTIVO (atomica + hash)")
        path = self._select_golden_image("Golden da copiare sull'attivo")
        if path is None:
            return
        active = self.catalog.config.target_path
        print(f"Destinazione: {active}")
        confirm = input("Confermi la sovrascrittura dell'HDD attivo? (s/N): ").strip().lower()
        if confirm not in {"s", "y"}:
            print("Annullato.")
            self._pause()
            return
        try:
            report = atomic_copy_qcow2(
                path,
                active,
                self.catalog.config.backup_folder,
            )
            self._record_and_print(
                LabResult(
                    timestamp=datetime.now(),
                    name="Copia golden → attivo",
                    passed=True,
                    details=(
                        f"Da: {report.source}",
                        f"A:  {report.destination}",
                        f"sha256: {report.sha256}",
                    ),
                )
            )
        except (SafetyError, OSError) as exc:
            print(f"ERRORE: {type(exc).__name__}: {exc}")
        self._pause()

    def _select_golden_image(self, prompt: str) -> Optional[Path]:
        entries = [
            entry
            for entry in self.catalog.entries(include_unregistered=False)
            if entry.exists and entry.registered
        ]
        print()
        print(prompt)
        for index, entry in enumerate(entries, start=1):
            marker = ""
            if entry.scenario_id in {"b1", "b2"}:
                marker = " [fixture forense, non usare come golden restore]"
            print(
                f"  {index:2}. [{entry.display_id}] "
                f"{entry.actual_path.name} - {entry.description}{marker}"
            )
        print("   0. Annulla")
        choice = input("Selezione: ").strip()
        if choice == "0" or not choice:
            return None
        try:
            index = int(choice) - 1
        except ValueError:
            print("Selezione non valida.")
            return None
        if not 0 <= index < len(entries):
            print("Selezione non valida.")
            return None
        return entries[index].actual_path

    def _analysis_menu(self) -> None:
        while True:
            print()
            print("ANALISI READ-ONLY")
            print("  1. Ispeziona un HDD")
            print("  2. Confronta due HDD guest-aware")
            print("  3. Autoverifica Black B1/B2")
            print("  4. Autoverifica Halo H1/H2 (lenta)")
            print("  0. Torna al menu principale")
            choice = input("\nScelta: ").strip()

            if choice == "0":
                return
            if choice == "1":
                path = self._select_image("HDD da ispezionare")
                if path is not None:
                    self._inspect_image(path)
                    self._pause()
            elif choice == "2":
                left = self._select_image("Primo HDD")
                if left is None:
                    continue
                right = self._select_image("Secondo HDD")
                if right is None:
                    continue
                self._run_free_comparison(left, right)
                self._pause()
            elif choice == "3":
                result = self.verify_black()
                self._record_and_print(result)
                self._pause()
            elif choice == "4":
                answer = input(
                    "Il confronto può richiedere diversi minuti. Procedere? (s/N): "
                ).strip().lower()
                if answer in {"s", "y"}:
                    result = self.verify_halo()
                    self._record_and_print(result)
                else:
                    print("Operazione annullata.")
                self._pause()
            else:
                print("Scelta non valida.")

    def verify_black(self) -> LabResult:
        details: List[str] = []
        checks: List[bool] = []
        try:
            b1 = self.catalog.find("b1")
            b2 = self.catalog.find("b2")
            if not b1.exists or not b2.exists:
                raise FileNotFoundError("Fixture B1/B2 non disponibili")

            for label, entry in (("B1", b1), ("B2", b2)):
                with QCOW2BlockDevice(entry.actual_path) as device:
                    checks.extend(
                        [
                            _check(
                                details,
                                f"{label} QCOW2 v3",
                                device.header.version,
                                3,
                            ),
                            _check(
                                details,
                                f"{label} guest size",
                                device.size,
                                EXPECTED_GUEST_SIZE,
                            ),
                            _check(
                                details,
                                f"{label} cluster QCOW2",
                                device.cluster_size,
                                EXPECTED_QCOW2_CLUSTER_SIZE,
                            ),
                            _check(
                                details,
                                f"{label} mapping E host",
                                device.map_offset(PARTITION_E_OFFSET),
                                0x1A0000,
                                formatter=_format_optional_hex,
                            ),
                        ]
                    )
                    volume = FATXVolume.open_partition(device, "E")
                    save_meta = volume.find_named_entries("SaveMeta.xbx")
                    save_meta_clusters = sorted(
                        {
                            item.entry.directory_cluster
                            for item in save_meta
                        }
                    )
                    has_cluster_9 = 9 in save_meta_clusters
                    checks.append(has_cluster_9)
                    details.append(
                        f"{'OK' if has_cluster_9 else 'ERRORE'} - "
                        f"{label} SaveMeta.xbx in directory cluster: "
                        f"{save_meta_clusters or 'non trovato'}; atteso 9"
                    )

            print("\nConfronto guest-aware B1/B2...")
            summary = compare_paths(
                b1.actual_path,
                b2.actual_path,
                progress=_console_progress,
            )
            print()
            region_totals = summary.region_totals()
            cluster_totals = summary.cluster_totals("E")
            checks.extend(
                [
                    _check(
                        details,
                        "Byte diversi totali",
                        summary.total_different_bytes,
                        BLACK_EXPECTED_TOTAL,
                    ),
                    _check(
                        details,
                        "Byte diversi CONFIG",
                        region_totals.get("CONFIG", 0),
                        BLACK_EXPECTED_CONFIG,
                    ),
                    _check(
                        details,
                        "Delta cluster dati E",
                        cluster_totals,
                        BLACK_EXPECTED_CLUSTERS,
                    ),
                ]
            )
            details.append(
                "Nota: questo prova coerenza strutturale e delta noto, "
                "non l'integrità gameplay di B1 o B2."
            )
        except Exception as exc:
            checks.append(False)
            details.append(f"ERRORE - {type(exc).__name__}: {exc}")

        return LabResult(
            timestamp=datetime.now(),
            name="Autoverifica Black B1/B2",
            passed=bool(checks) and all(checks),
            details=tuple(details),
        )

    def verify_halo(self) -> LabResult:
        details: List[str] = []
        checks: List[bool] = []
        try:
            h1 = self.catalog.find("h1")
            h2 = self.catalog.find("h2")
            if not h1.exists or not h2.exists:
                raise FileNotFoundError("Fixture H1/H2 non disponibili")

            for label, entry in (("H1", h1), ("H2", h2)):
                with QCOW2BlockDevice(entry.actual_path) as device:
                    checks.extend(
                        [
                            _check(
                                details,
                                f"{label} QCOW2 v3",
                                device.header.version,
                                3,
                            ),
                            _check(
                                details,
                                f"{label} guest size",
                                device.size,
                                EXPECTED_GUEST_SIZE,
                            ),
                            _check(
                                details,
                                f"{label} cluster QCOW2",
                                device.cluster_size,
                                EXPECTED_QCOW2_CLUSTER_SIZE,
                            ),
                        ]
                    )
                    volumes = discover_fatx_volumes(
                        device,
                        names=("Y", "E"),
                    )
                    found = sorted(volumes)
                    valid_volumes = found == ["E", "Y"]
                    checks.append(valid_volumes)
                    details.append(
                        f"{'OK' if valid_volumes else 'ERRORE'} - "
                        f"{label} partizioni FATX richieste: {found}; "
                        "atteso ['E', 'Y']"
                    )
                    if "E" in volumes:
                        title_ids = {
                            game.title_id for game in volumes["E"].list_games()
                        }
                        has_halo = "4d530064" in title_ids
                        checks.append(has_halo)
                        details.append(
                            f"{'OK' if has_halo else 'ERRORE'} - "
                            f"{label} Halo 2 in E: {sorted(title_ids)}"
                        )

            print("\nConfronto guest-aware H1/H2...")
            summary = compare_paths(
                h1.actual_path,
                h2.actual_path,
                progress=_console_progress,
                sample_limit=5,
            )
            print()
            regions = summary.region_totals()
            checks.extend(
                [
                    _check(
                        details,
                        "Byte diversi totali",
                        summary.total_different_bytes,
                        HALO_EXPECTED_TOTAL,
                    ),
                    _check(
                        details,
                        "Byte diversi Y-cache",
                        regions.get("Y", 0),
                        HALO_EXPECTED_Y,
                    ),
                    _check(
                        details,
                        "Byte diversi E-data",
                        regions.get("E", 0),
                        HALO_EXPECTED_E,
                    ),
                    _check(
                        details,
                        "Byte diversi fuori Y/E",
                        summary.other_than("Y", "E"),
                        HALO_EXPECTED_OTHER,
                    ),
                ]
            )
        except Exception as exc:
            checks.append(False)
            details.append(f"ERRORE - {type(exc).__name__}: {exc}")

        return LabResult(
            timestamp=datetime.now(),
            name="Autoverifica Halo H1/H2",
            passed=bool(checks) and all(checks),
            details=tuple(details),
        )

    def _inspect_image(self, path: Path) -> None:
        print()
        print(f"ISPEZIONE READ-ONLY: {path}")
        try:
            with QCOW2BlockDevice(path) as device:
                header = device.header
                print(f"Host size:       {_format_bytes(device.host_size)}")
                print(f"QCOW2 version:   {header.version}")
                print(f"Guest size:      {_format_bytes(device.size)}")
                print(f"Cluster QCOW2:   {_format_bytes(device.cluster_size)}")
                print(f"L1:              {header.l1_size} entry @ 0x{header.l1_table_offset:x}")
                print(f"Dirty flag:      {'SI' if header.is_dirty else 'no'}")
                print()
                print("PARTIZIONI")
                volumes = discover_fatx_volumes(device)
                for region in XBOX_REGIONS:
                    if not region.is_fatx:
                        continue
                    try:
                        host_offset = device.map_offset(region.offset)
                        magic = device.read_at(region.offset, 4)
                        mapping = (
                            _format_optional_hex(host_offset)
                            if host_offset is not None
                            else "non allocato/zero"
                        )
                        status = "FATX" if magic == b"FATX" else repr(magic)
                        print(
                            f"  {region.name}: guest 0x{region.offset:08x} "
                            f"-> host {mapping}; {status}"
                        )
                    except UnsupportedQCOW2Feature as exc:
                        print(f"  {region.name}: non ispezionata ({exc})")

                volume_e = volumes.get("E")
                if volume_e is not None:
                    fat_name = (
                        "FAT16"
                        if volume_e.header.is_fat16
                        else "FAT32"
                    )
                    print()
                    print("FATX E")
                    print(
                        f"  Cluster FATX:  {_format_bytes(volume_e.header.cluster_size)}"
                    )
                    print(f"  Tipo FAT:      {fat_name}")
                    print(
                        f"  File area:     0x{volume_e.header.file_area_offset:x}"
                    )
                    games = volume_e.list_games()
                    if games:
                        print("  Giochi UDATA/TDATA:")
                        for game in games:
                            print(
                                f"    {game.area}\\{game.title_id} "
                                f"(cluster {game.entry.first_cluster})"
                            )
                    else:
                        print("  Nessun Title ID trovato in UDATA/TDATA.")
        except (OSError, QCOW2Error, FATXError, ValueError) as exc:
            print(f"ERRORE: {type(exc).__name__}: {exc}")

    def _run_free_comparison(self, left: Path, right: Path) -> None:
        print()
        print(f"Sinistra: {left}")
        print(f"Destra:   {right}")
        try:
            summary = compare_paths(
                left,
                right,
                progress=_console_progress,
            )
            print()
            _print_diff_summary(summary)
            result = LabResult(
                timestamp=datetime.now(),
                name=f"Confronto {left.name} / {right.name}",
                passed=None,
                details=(
                    f"Byte diversi: {summary.total_different_bytes:,}",
                    "Confronto completato senza errori di formato.",
                ),
            )
            self.results.append(result)
        except Exception as exc:
            print()
            print(f"ERRORE: {type(exc).__name__}: {exc}")
            self.results.append(
                LabResult(
                    timestamp=datetime.now(),
                    name=f"Confronto {left.name} / {right.name}",
                    passed=False,
                    details=(f"{type(exc).__name__}: {exc}",),
                )
            )

    def _show_catalog_and_results(self) -> None:
        print()
        print("CATALOGO HDD (sola lettura)")
        entries = self.catalog.entries(include_unregistered=True)
        for entry in entries:
            marker = "REG" if entry.registered else "NON CATALOGATO"
            if entry.scenario_id in {"b1", "b2"}:
                marker = "FIXTURE FORENSE - NON GOLDEN"
            identifier = entry.display_id.rjust(2)
            if not entry.exists:
                print(
                    f"  [{identifier}] MANCANTE {entry.actual_path.name} "
                    f"- {entry.description}"
                )
                continue
            host_size = (
                _format_bytes(entry.host_size)
                if entry.host_size is not None
                else "?"
            )
            qcow = (
                f"QCOW2 v{entry.qcow2.version}, "
                f"guest {_format_bytes(entry.qcow2.guest_size)}"
                if entry.qcow2 is not None
                else f"errore: {entry.error}"
            )
            print(
                f"  [{identifier}] {entry.actual_path.name} "
                f"({host_size}) [{marker}]"
            )
            print(f"       {entry.description}; {qcow}")
            if entry.filename_case_mismatch:
                print(
                    f"       NOTA: JSON={entry.configured_filename}, "
                    f"disco={entry.actual_path.name}"
                )

        configured_active = self.catalog.config.target_path
        xemu_active = read_xemu_hdd_path()
        print()
        print(f"HDD attivo da catalogo: {configured_active}")
        print(f"HDD attivo da xemu.toml: {xemu_active or 'non rilevato'}")
        if (
            xemu_active is not None
            and _normalized_path(xemu_active)
            != _normalized_path(configured_active)
        ):
            print("ATTENZIONE: i due percorsi attivi non coincidono.")

        print()
        print("RISULTATI DELLA SESSIONE")
        if not self.results:
            print("  Nessun test eseguito in questa sessione.")
        for result in self.results:
            state = (
                "PASS"
                if result.passed is True
                else "FAIL"
                if result.passed is False
                else "INFO"
            )
            print(
                f"  [{state}] {result.timestamp:%H:%M:%S} - {result.name}"
            )
            for detail in result.details:
                print(f"       {detail}")
        self._pause()

    def _select_image(self, prompt: str) -> Optional[Path]:
        entries = [
            entry
            for entry in self.catalog.entries(include_unregistered=True)
            if entry.exists
        ]
        print()
        print(prompt)
        for index, entry in enumerate(entries, start=1):
            identifier = (
                entry.scenario_id
                if entry.scenario_id is not None
                else "non catalogato"
            )
            if entry.scenario_id in {"b1", "b2"}:
                identifier += ", fixture forense NON golden"
            print(
                f"  {index:2}. {entry.actual_path.name} [{identifier}]"
            )
        active_index = len(entries) + 1
        print(
            f"  {active_index:2}. HDD attivo "
            f"({self.catalog.config.target_path})"
        )
        print("   0. Annulla")

        choice = input("Selezione: ").strip()
        if choice == "0" or not choice:
            return None
        try:
            index = int(choice) - 1
        except ValueError:
            print("Selezione non valida.")
            return None
        if index == len(entries):
            return self.catalog.config.target_path
        if not 0 <= index < len(entries):
            print("Selezione non valida.")
            return None
        return entries[index].actual_path

    def _record_and_print(self, result: LabResult) -> None:
        self.results.append(result)
        state = (
            "PASS"
            if result.passed is True
            else "FAIL"
            if result.passed is False
            else "INFO"
        )
        print()
        print("=" * 72)
        print(f"{state} - {result.name}")
        print("=" * 72)
        for detail in result.details:
            print(detail)

    @staticmethod
    def _pause() -> None:
        input("\nPremi INVIO per continuare...")


def _check(
    details: List[str],
    label: str,
    actual,
    expected,
    formatter: Callable[[object], str] = str,
) -> bool:
    passed = actual == expected
    details.append(
        f"{'OK' if passed else 'ERRORE'} - {label}: "
        f"{formatter(actual)}; atteso {formatter(expected)}"
    )
    return passed


def _console_progress(done: int, total: int, different_bytes: int) -> None:
    percent = (done / total * 100) if total else 100.0
    print(
        f"\rScansione guest: {percent:6.2f}% "
        f"({done:,}/{total:,} cluster), "
        f"diff {different_bytes:,} byte",
        end="",
        flush=True,
    )


def _print_diff_summary(summary: GuestDiffSummary) -> None:
    print(f"Byte diversi:          {summary.total_different_bytes:,}")
    print(f"Cluster QCOW diversi:  {summary.differing_guest_clusters:,}")
    print("Per regione:")
    for region, count in sorted(
        summary.region_totals().items(),
        key=lambda item: (-item[1], item[0]),
    ):
        print(f"  {region:8} {count:>15,}")

    print("Bucket principali:")
    for bucket, count in sorted(
        summary.buckets.items(),
        key=lambda item: (-item[1], item[0].label),
    )[:20]:
        print(f"  {bucket.label:<32} {count:>15,}")

    if summary.samples:
        print("Prime differenze:")
        for sample in summary.samples:
            print(
                f"  guest 0x{sample.guest_offset:08x}: "
                f"{sample.left_byte:02x} -> {sample.right_byte:02x} "
                f"({sample.bucket.label})"
            )


def _format_bytes(value: Optional[int]) -> str:
    if value is None:
        return "?"
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.2f} {unit}"
        amount /= 1024
    return f"{value} B"


def _format_optional_hex(value: object) -> str:
    if value is None:
        return "None"
    if isinstance(value, int):
        return f"0x{value:x}"
    return str(value)


def _normalized_path(path: Path) -> str:
    return str(path).replace("/", "\\").casefold()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Laboratorio read-only QCOW2/FATX per xemu"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--verify-black",
        action="store_true",
        help="esegue l'autoverifica read-only B1/B2",
    )
    group.add_argument(
        "--verify-halo",
        action="store_true",
        help="esegue l'autoverifica read-only H1/H2",
    )
    group.add_argument(
        "--catalog",
        action="store_true",
        help="stampa il catalogo e termina",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        lab = XemuTestLab()
        if args.verify_black:
            result = lab.verify_black()
            lab._record_and_print(result)
            return 0 if result.passed is True else 1
        if args.verify_halo:
            result = lab.verify_halo()
            lab._record_and_print(result)
            return 0 if result.passed is True else 1
        if args.catalog:
            for entry in lab.catalog.entries(include_unregistered=True):
                print(
                    f"{entry.display_id}\t{entry.actual_path}\t"
                    f"{'registered' if entry.registered else 'unregistered'}"
                )
            return 0
        lab.run()
        return 0
    except KeyboardInterrupt:
        print("\nInterrotto dall'utente. Nessun HDD è stato modificato.")
        return 130
    except Exception as exc:
        print(f"ERRORE FATALE: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
