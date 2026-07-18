"""Restore chirurgico guest-aware da backup XBSV v6/v7."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union

from .backup import GameBackup, load_backup
from .fatx import FATXVolume, get_region
from .qcow2 import (
    QCOW2WriteError,
    QCOW2WritableBlockDevice,
    UnsupportedQCOW2Feature,
)


PathLike = Union[str, Path]


class RestoreError(Exception):
    """Restore rifiutato o fallito."""


@dataclass(frozen=True)
class RestoreReport:
    target_path: Path
    title_id: str
    directory_entries: int
    fat_bytes: int
    data_clusters: int
    verified: bool
    clusters_allocated: int = 0
    host_bytes_grown: int = 0
    allocate_used: bool = False
    envelopes_written: int = 0


def restore_backup_to_path(
    backup: GameBackup,
    target_path: PathLike,
    verify: bool = True,
    allow_allocate: bool = False,
) -> RestoreReport:
    """Applica il backup sull'immagine target.

    Con ``allow_allocate=False`` (default) richiede cluster QCOW2 già
    overwrite-safe. Con ``True`` alloca host cluster; per non corrompere
    FAT/root condivisi serve un backup v7 con envelope QCOW2 interi.
    """

    target = Path(target_path)
    if not target.is_file():
        raise RestoreError(f"Target assente: {target}")

    try:
        with QCOW2WritableBlockDevice(target) as device:
            report = restore_backup_to_device(
                backup,
                device,
                verify=verify,
                allow_allocate=allow_allocate,
            )
    except (QCOW2WriteError, UnsupportedQCOW2Feature) as exc:
        raise RestoreError(str(exc)) from exc
    return report


def restore_backup_file(
    bin_path: PathLike,
    target_path: PathLike,
    json_path: Optional[PathLike] = None,
    verify: bool = True,
    allow_allocate: bool = False,
) -> RestoreReport:
    backup = load_backup(bin_path, json_path=json_path)
    return restore_backup_to_path(
        backup,
        target_path,
        verify=verify,
        allow_allocate=allow_allocate,
    )


def restore_backup_to_device(
    backup: GameBackup,
    device: QCOW2WritableBlockDevice,
    verify: bool = True,
    allow_allocate: bool = False,
) -> RestoreReport:
    if backup.fatx_cluster_size <= 0:
        raise RestoreError("fatx_cluster_size non valido nel backup")

    pending: List[Tuple[int, bytes]] = []
    for guest_offset, raw in backup.directory_entries:
        pending.append((guest_offset, raw))
    for _first, guest_offset, blob in backup.fat_runs:
        pending.append((guest_offset, blob))
    for _cluster, guest_offset, payload in backup.data_chunks:
        pending.append((guest_offset, payload))

    allocated_before = device.clusters_allocated
    grown_before = device.host_bytes_grown
    envelopes_written = 0

    if allow_allocate:
        _preflight_allocate(backup, device, pending)
        with device.allocating():
            if backup.has_qcow2_envelopes:
                if (
                    backup.qcow2_cluster_size
                    and backup.qcow2_cluster_size != device.cluster_size
                ):
                    raise RestoreError(
                        "qcow2_cluster_size del backup "
                        f"({backup.qcow2_cluster_size}) != target "
                        f"({device.cluster_size})"
                    )
                # Envelope solo dove serve allocate. Dove il cluster è già
                # overwrite-safe: nessun envelope → solo byte chirurgici (= v6).
                for guest_cluster, payload in backup.qcow2_envelopes:
                    if not device.needs_allocation(guest_cluster):
                        continue
                    device.write_guest_cluster(
                        guest_cluster,
                        payload,
                        allocate=True,
                    )
                    envelopes_written += 1
            else:
                # Solo path compresso-safe senza envelope: RMW per cluster.
                _write_pending_allocating_coalesced(device, pending)

            for guest_offset, payload in pending:
                device.write_at(guest_offset, payload, allocate=True)
    else:
        for guest_offset, payload in pending:
            _ensure_range(
                device,
                guest_offset,
                len(payload),
                allocate=False,
            )
        for guest_offset, payload in pending:
            device.write_at(guest_offset, payload)
        device.flush()

    verified = False
    if verify:
        for guest_offset, payload in pending:
            actual = device.read_at(guest_offset, len(payload))
            if actual != payload:
                raise RestoreError(
                    f"Verifica read-back fallita @ guest 0x{guest_offset:x}"
                )
        _verify_title_visible(device, backup)
        verified = True

    fat_bytes = sum(len(blob) for _first, _off, blob in backup.fat_runs)
    return RestoreReport(
        target_path=device.path,
        title_id=backup.title_id,
        directory_entries=len(backup.directory_entries),
        fat_bytes=fat_bytes,
        data_clusters=len(backup.data_chunks),
        verified=verified,
        clusters_allocated=device.clusters_allocated - allocated_before,
        host_bytes_grown=device.host_bytes_grown - grown_before,
        allocate_used=allow_allocate,
        envelopes_written=envelopes_written,
    )


def _preflight_allocate(
    backup: GameBackup,
    device: QCOW2WritableBlockDevice,
    pending: List[Tuple[int, bytes]],
) -> None:
    """Rifiuta allocate pericoloso senza envelope su cluster unalloc/zero."""

    if backup.has_qcow2_envelopes:
        return

    touched = _touched_qcow2_clusters(pending, device.cluster_size)
    coverage = _coverage_by_cluster(pending, device.cluster_size)
    dangerous: List[int] = []
    for guest_cluster in sorted(touched):
        if not device.needs_allocation(guest_cluster):
            continue
        if device.is_compressed_cluster(guest_cluster):
            # Decompress + RMW preserva i byte non toccati.
            continue
        covered = coverage.get(guest_cluster, 0)
        if covered < device.cluster_size:
            dangerous.append(guest_cluster)

    if dangerous:
        raise RestoreError(
            "Allocate su cluster QCOW2 unallocated/zero con copertura "
            "parziale (condividono FAT/root con il save). I backup XBSV v6 "
            "senza envelope non sono sicuri su HDD vergine/sparse. "
            f"Cluster a rischio: {dangerous[:8]}"
            + ("..." if len(dangerous) > 8 else "")
            + ". Rifare il backup dal golden (XBSV v7 con envelope QCOW2)."
        )


def _write_pending_allocating_coalesced(
    device: QCOW2WritableBlockDevice,
    pending: List[Tuple[int, bytes]],
) -> None:
    """RMW per cluster QCOW2: base decompressa/zero + frammenti pending."""

    by_cluster: Dict[int, bytearray] = {}
    for offset, payload in pending:
        cursor = 0
        while cursor < len(payload):
            guest_offset = offset + cursor
            guest_cluster = guest_offset // device.cluster_size
            in_cluster = guest_offset % device.cluster_size
            chunk = min(
                len(payload) - cursor,
                device.cluster_size - in_cluster,
            )
            if guest_cluster not in by_cluster:
                by_cluster[guest_cluster] = bytearray(
                    device.read_cluster_content(guest_cluster)
                )
            by_cluster[guest_cluster][
                in_cluster : in_cluster + chunk
            ] = payload[cursor : cursor + chunk]
            cursor += chunk

    for guest_cluster, data in sorted(by_cluster.items()):
        device.write_guest_cluster(
            guest_cluster,
            bytes(data),
            allocate=True,
        )


def _verify_title_visible(
    device: QCOW2WritableBlockDevice,
    backup: GameBackup,
) -> None:
    try:
        region = get_region(backup.partition)
    except KeyError:
        return
    if region.end > device.size:
        # Fixture sintetiche più piccole del layout Xbox: skip.
        return

    try:
        volume = FATXVolume.open_partition(device, backup.partition)
    except Exception as exc:
        raise RestoreError(
            f"Verifica FATX fallita aprendo partizione {backup.partition}: {exc}"
        ) from exc

    title = backup.title_id.lower()
    found = [
        game
        for game in volume.list_games()
        if game.title_id.lower() == title
    ]
    if not found:
        raise RestoreError(
            f"Title ID {backup.title_id} non visibile in FATX dopo restore "
            "(probabile corruzione metadata QCOW2/FAT condivisi). "
            "Su vergine usare backup XBSV v7 con envelope."
        )


def _touched_qcow2_clusters(
    pending: List[Tuple[int, bytes]],
    cluster_size: int,
) -> Set[int]:
    touched: Set[int] = set()
    for offset, payload in pending:
        if not payload:
            continue
        start = offset // cluster_size
        end = (offset + len(payload) - 1) // cluster_size
        touched.update(range(start, end + 1))
    return touched


def _coverage_by_cluster(
    pending: List[Tuple[int, bytes]],
    cluster_size: int,
) -> Dict[int, int]:
    masks: Dict[int, bytearray] = {}
    for offset, payload in pending:
        cursor = 0
        while cursor < len(payload):
            guest_offset = offset + cursor
            guest_cluster = guest_offset // cluster_size
            in_cluster = guest_offset % cluster_size
            chunk = min(len(payload) - cursor, cluster_size - in_cluster)
            mask = masks.setdefault(guest_cluster, bytearray(cluster_size))
            for index in range(in_cluster, in_cluster + chunk):
                mask[index] = 1
            cursor += chunk
    return {gc: sum(mask) for gc, mask in masks.items()}


def _ensure_range(
    device: QCOW2WritableBlockDevice,
    offset: int,
    size: int,
    *,
    allocate: bool,
) -> None:
    if size == 0:
        return
    cursor = 0
    while cursor < size:
        guest_offset = offset + cursor
        guest_cluster = guest_offset // device.cluster_size
        in_cluster = guest_offset % device.cluster_size
        chunk = min(size - cursor, device.cluster_size - in_cluster)
        if allocate:
            device.ensure_allocated(guest_cluster)
        else:
            device._require_writable_mapping(guest_cluster)
        cursor += chunk
