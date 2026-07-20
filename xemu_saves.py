#!/usr/bin/env python3
"""Standalone surgical Xbox save backup/restore for xemu (no SaveState required).

Discovers the live QCOW2 from xemu.toml when possible, otherwise asks for a path.
Uses xemu_lab (guest-aware QCOW2 + FATX, XBSV v7, same-guest / allocate / remap).
"""

from __future__ import annotations

import json
import os
import platform
import re
import sys
from pathlib import Path
from typing import Optional

try:
    import tomllib
except ImportError:  # Python < 3.11
    tomllib = None  # type: ignore

from colorama import Fore, Style, init as colorama_init

from xemu_lab.backup import (
    DEFAULT_BACKUP_DIR,
    BackupError,
    backup_display_label,
    backup_title_id_from_path,
    list_backups,
    save_backup,
)
from xemu_lab.restore import RestoreError, safe_restore_backup_file
from xemu_lab.safety import SafetyError, assert_xemu_closed
from xemu_lab.titles import game_display_name, list_games_on_image

colorama_init(autoreset=True)

# Portfolio green (#58b036) — truecolor for modern terminals
ACCENT = "\033[38;2;88;176;54m"

ROOT = Path(__file__).resolve().parent
TITLE_MAP_PATH = ROOT / "xbox_title_id_map.json"

_title_map: dict[str, str] = {}
_title_map_loaded = False


def c(text: str, color: str = "") -> str:
    if not color:
        return text
    return f"{color}{text}{Style.RESET_ALL}"


def ok(msg: str) -> None:
    print(c(f"  OK: {msg}", ACCENT))


def warn(msg: str) -> None:
    print(c(f"  ! {msg}", Fore.YELLOW))


def err(msg: str) -> None:
    print(c(f"  ERROR: {msg}", Fore.RED))


def info(msg: str) -> None:
    print(c(f"  {msg}", Fore.CYAN))


def load_title_map() -> dict[str, str]:
    global _title_map, _title_map_loaded
    if _title_map_loaded:
        return _title_map
    _title_map_loaded = True
    if not TITLE_MAP_PATH.is_file():
        return _title_map
    try:
        raw = json.loads(TITLE_MAP_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _title_map
    if isinstance(raw, dict):
        for tid, name in raw.items():
            if isinstance(tid, str) and isinstance(name, str):
                _title_map[tid.strip().lower()] = name
    return _title_map


def display_name(title_id: str) -> str:
    tid = title_id.strip().lower()
    names = load_title_map()
    if tid in names:
        return names[tid]
    return game_display_name(tid)


def candidate_toml_paths() -> list[Path]:
    candidates: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        key = os.path.normcase(str(path.resolve()) if path.exists() else str(path))
        if key in seen:
            return
        seen.add(key)
        candidates.append(path)

    system = platform.system()
    home = Path.home()

    if system == "Windows":
        appdata = os.getenv("APPDATA")
        if appdata:
            add(Path(appdata) / "xemu" / "xemu" / "xemu.toml")
        add(Path.cwd() / "xemu.toml")
    elif system == "Linux":
        xdg_data = Path(os.getenv("XDG_DATA_HOME", home / ".local" / "share"))
        add(xdg_data / "xemu" / "xemu" / "xemu.toml")
        add(
            home
            / ".var"
            / "app"
            / "app.xemu.xemu"
            / "data"
            / "xemu"
            / "xemu"
            / "xemu.toml"
        )
        xdg_config = Path(os.getenv("XDG_CONFIG_HOME", home / ".config"))
        add(xdg_config / "xemu" / "xemu" / "xemu.toml")
    elif system == "Darwin":
        add(home / "Library" / "Application Support" / "xemu" / "xemu" / "xemu.toml")

    return candidates


def parse_hdd_path_simple(text: str) -> Optional[str]:
    in_section = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            in_section = line.lower() == "[sys.files]"
            continue
        if not in_section:
            continue
        match = re.match(
            r"^hdd_path\s*=\s*(['\"])(.*)\1\s*$",
            line,
            flags=re.IGNORECASE,
        )
        if match:
            return match.group(2).strip() or None
        match = re.match(r"^hdd_path\s*=\s*(.+)$", line, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip().strip("\"'") or None
    return None


def read_hdd_path_from_toml(toml_path: Path) -> Optional[Path]:
    try:
        raw = toml_path.read_bytes()
    except OSError:
        return None

    hdd: Optional[str] = None
    if tomllib is not None:
        try:
            data = tomllib.loads(raw.decode("utf-8"))
            files = data.get("sys", {}).get("files", {})
            if isinstance(files, dict):
                value = files.get("hdd_path")
                if isinstance(value, str) and value.strip():
                    hdd = value.strip()
        except Exception:
            hdd = None

    if not hdd:
        hdd = parse_hdd_path_simple(raw.decode("utf-8", errors="replace"))
    if not hdd:
        return None

    path = Path(hdd)
    if not path.is_absolute():
        path = (toml_path.parent / path).resolve()
    return path


def find_xemu_hdd() -> tuple[Optional[Path], Optional[Path]]:
    """Return (hdd_path, toml_path). Either may be None."""

    for toml_path in candidate_toml_paths():
        if not toml_path.is_file():
            continue
        hdd = read_hdd_path_from_toml(toml_path)
        if hdd is not None and hdd.is_file():
            return hdd, toml_path
        if hdd is not None:
            return hdd, toml_path  # configured but missing — caller can warn
    return None, None


def prompt(msg: str) -> str:
    return input(c(msg, Fore.WHITE)).strip()


def ask_yes_no(msg: str, default: bool = False) -> bool:
    suffix = " [Y/n]: " if default else " [y/N]: "
    answer = prompt(msg + suffix).lower()
    if not answer:
        return default
    return answer in {"y", "yes"}


def resolve_hdd_interactive(current: Optional[Path]) -> Optional[Path]:
    if current is not None and current.is_file():
        return current

    if current is not None:
        warn(f"Configured HDD not found: {current}")
    else:
        warn("Could not auto-detect xemu HDD from xemu.toml.")

    while True:
        raw = prompt("Enter path to xbox_hdd.qcow2 (or blank to cancel): ")
        if not raw:
            return None
        path = Path(raw.strip().strip('"'))
        if path.is_file():
            return path.resolve()
        err(f"File not found: {path}")


def change_hdd(current: Optional[Path]) -> Optional[Path]:
    print()
    print(c("Change HDD path", Fore.MAGENTA + Style.BRIGHT))
    if current:
        info(f"Current: {current}")
    raw = prompt("New .qcow2 path (blank = keep current): ")
    if not raw:
        return current
    path = Path(raw.strip().strip('"'))
    if not path.is_file():
        err(f"File not found: {path}")
        return current
    ok(f"Using {path.resolve()}")
    return path.resolve()


def print_banner(hdd: Optional[Path], toml_path: Optional[Path]) -> None:
    print()
    print(c("=" * 64, ACCENT))
    print(c("  xemu surgical save tool  (standalone)", Style.BRIGHT))
    print(c("  QEMU-free · XBSV v7 · same-guest / allocate / remap", ACCENT))
    print(c("=" * 64, ACCENT))
    if toml_path and toml_path.is_file():
        info(f"Config: {toml_path}")
    if hdd and hdd.is_file():
        ok(f"HDD:    {hdd}")
    elif hdd:
        warn(f"HDD set but missing: {hdd}")
    else:
        warn("HDD:    (not set)")
    info(f"Backups: {DEFAULT_BACKUP_DIR}")
    print()


def colored_backup_label(json_path: Path) -> str:
    """Accent only on the game name; keep date/version uncolored."""

    label = backup_display_label(json_path)
    if " (" in label:
        name, rest = label.split(" (", 1)
        return f"{c(name, ACCENT)} ({rest}"
    match = re.match(r"^(.*?)( v\d+)$", label)
    if match:
        return f"{c(match.group(1), ACCENT)}{match.group(2)}"
    return c(label, ACCENT)


def list_games(hdd: Path) -> list:
    try:
        games = list_games_on_image(hdd, partition="E", areas=("UDATA",))
    except Exception as exc:
        err(f"Failed to scan HDD: {exc}")
        return []
    if not games:
        warn("No UDATA titles found on this HDD.")
        return []
    print()
    print(c("Games on HDD (UDATA)", Style.BRIGHT))
    for i, game in enumerate(games, start=1):
        name = display_name(game.title_id)
        print(f"  {i}. {c(name, ACCENT)}  [{game.title_id}]")
    return games


def do_backup(hdd: Path) -> None:
    print()
    print(c("Backup Title ID", Fore.MAGENTA + Style.BRIGHT))
    games = list_games(hdd)
    title_id = ""
    if games:
        choice = prompt("Number, or paste an 8-hex Title ID: ")
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(games):
                title_id = games[idx - 1].title_id
        elif len(choice) == 8 and all(
            ch in "0123456789abcdefABCDEF" for ch in choice
        ):
            title_id = choice.lower()
    else:
        title_id = prompt("Title ID (8 hex): ").lower()

    if len(title_id) != 8:
        err("Invalid Title ID.")
        return

    try:
        assert_xemu_closed()
    except SafetyError as exc:
        err(str(exc))
        return

    print()
    info(f"Backing up {display_name(title_id)} [{title_id}] …")
    try:
        backup = backup_title_id_from_path(hdd, title_id)
        bin_path, json_path = save_backup(backup)
    except (BackupError, SafetyError, OSError) as exc:
        err(str(exc))
        return

    ok(f"{backup.cluster_count} data clusters, {backup.directory_entry_count} dir entries")
    ok(f"{bin_path.name}")
    info(str(bin_path))
    info(str(json_path))


def do_restore(hdd: Path) -> None:
    print()
    print(c("Restore backup", Fore.MAGENTA + Style.BRIGHT))
    backups = list_backups(DEFAULT_BACKUP_DIR)
    if not backups:
        warn(f"No XBSV backups in {DEFAULT_BACKUP_DIR}")
        raw = prompt("Or enter path to a .bin / .json backup: ")
        if not raw:
            return
        path = Path(raw.strip().strip('"'))
        json_path = path if path.suffix.lower() == ".json" else path.with_suffix(".json")
        bin_path = path if path.suffix.lower() == ".bin" else path.with_suffix(".bin")
        if not bin_path.is_file():
            err(f"Missing {bin_path}")
            return
    else:
        print()
        for i, jp in enumerate(backups, start=1):
            print(f"  {i}. {colored_backup_label(jp)}")
        choice = prompt("Number (blank cancel): ")
        if not choice.isdigit():
            return
        idx = int(choice)
        if not (1 <= idx <= len(backups)):
            err("Invalid selection.")
            return
        json_path = backups[idx - 1]
        bin_path = json_path.with_suffix(".bin")
        if not bin_path.is_file():
            err(f"Missing companion .bin: {bin_path}")
            return

    label = backup_display_label(json_path) if json_path.is_file() else bin_path.name
    warn("This writes into your live xemu HDD.")
    info(f"Target: {hdd}")
    info(f"Backup: {label}")
    if not ask_yes_no("Continue?", default=False):
        warn("Cancelled.")
        return

    try:
        assert_xemu_closed()
    except SafetyError as exc:
        err(str(exc))
        return

    print()
    info("Restoring (allocate + remap enabled when needed) …")
    try:
        report = safe_restore_backup_file(
            bin_path,
            hdd,
            json_path=json_path if json_path.is_file() else None,
            verify=True,
            allow_allocate=True,
            require_xemu_closed=True,
        )
    except (RestoreError, SafetyError, OSError) as exc:
        err(str(exc))
        return

    if report.verified:
        ok(
            f"Restored {report.title_id}  mode={report.mode}  "
            f"remapped={report.clusters_remapped}  "
            f"envelopes={report.envelopes_written}"
        )
    else:
        err(
            f"Finished but verification failed "
            f"(mode={report.mode}, remapped={report.clusters_remapped})"
        )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    hdd, toml_path = find_xemu_hdd()
    print_banner(hdd, toml_path)
    hdd = resolve_hdd_interactive(hdd)
    if hdd is None:
        err("No HDD selected. Exiting.")
        return 1

    while True:
        print()
        print(c("MENU", Style.BRIGHT))
        print("  1. List games on HDD")
        print("  2. Backup a game save")
        print("  3. Restore a backup")
        print("  4. Change HDD path")
        print("  0. Exit")
        choice = prompt("\nChoice: ")

        if choice == "0":
            print(c("Bye.", ACCENT))
            return 0
        if choice == "1":
            list_games(hdd)
        elif choice == "2":
            do_backup(hdd)
        elif choice == "3":
            do_restore(hdd)
        elif choice == "4":
            hdd = change_hdd(hdd) or hdd
            print_banner(hdd, toml_path)
        else:
            warn("Invalid choice.")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print()
        warn("Interrupted.")
        raise SystemExit(130)
