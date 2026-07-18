"""Restore chirurgico guest-aware da backup XBSV v6."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Union

from .backup import GameBackup, load_backup
from .qcow2 import QCOW2WriteError, QCOW2WritableBlockDevice


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


def restore_backup_to_path(
    backup: GameBackup,
    target_path: PathLike,
    verify: bool = True,
) -> RestoreReport:
    """Applica il backup sull'immagine target (solo overwrite allocato)."""

    target = Path(target_path)
    if not target.is_file():
        raise RestoreError(f"Target assente: {target}")

    try:
        with QCOW2WritableBlockDevice(target) as device:
            report = restore_backup_to_device(backup, device, verify=verify)
    except QCOW2WriteError as exc:
        raise RestoreError(str(exc)) from exc
    return report


def restore_backup_file(
    bin_path: PathLike,
    target_path: PathLike,
    json_path: Optional[PathLike] = None,
    verify: bool = True,
) -> RestoreReport:
    backup = load_backup(bin_path, json_path=json_path)
    return restore_backup_to_path(backup, target_path, verify=verify)


def restore_backup_to_device(
    backup: GameBackup,
    device: QCOW2WritableBlockDevice,
    verify: bool = True,
) -> RestoreReport:
    if backup.fatx_cluster_size <= 0:
        raise RestoreError("fatx_cluster_size non valido nel backup")

    # Preflight completo: nessuna scrittura se un solo segmento non è allocato.
    pending: List[Tuple[int, bytes]] = []
    for guest_offset, raw in backup.directory_entries:
        pending.append((guest_offset, raw))
    for _first, guest_offset, blob in backup.fat_runs:
        pending.append((guest_offset, blob))
    for _cluster, guest_offset, payload in backup.data_chunks:
        pending.append((guest_offset, payload))

    for guest_offset, payload in pending:
        _ensure_writable_range(device, guest_offset, len(payload))

    fat_bytes = 0
    for guest_offset, raw in backup.directory_entries:
        device.write_at(guest_offset, raw)
    for _first, guest_offset, blob in backup.fat_runs:
        device.write_at(guest_offset, blob)
        fat_bytes += len(blob)
    for _cluster, guest_offset, payload in backup.data_chunks:
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
        verified = True

    return RestoreReport(
        target_path=device.path,
        title_id=backup.title_id,
        directory_entries=len(backup.directory_entries),
        fat_bytes=fat_bytes,
        data_clusters=len(backup.data_chunks),
        verified=verified,
    )


def _ensure_writable_range(
    device: QCOW2WritableBlockDevice,
    offset: int,
    size: int,
) -> None:
    if size == 0:
        return
    cursor = 0
    while cursor < size:
        guest_offset = offset + cursor
        guest_cluster = guest_offset // device.cluster_size
        in_cluster = guest_offset % device.cluster_size
        chunk = min(size - cursor, device.cluster_size - in_cluster)
        device._require_writable_mapping(guest_cluster)
        cursor += chunk
