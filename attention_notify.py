"""Shared notification runner for Codex and Claude hooks.

This script is intentionally self-contained so every repo can point at the
same location without copying sound assets or helper code.

Paths are loaded from config.json next to this script.
Copy config.template.json to config.json and fill in your local paths.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import random
import subprocess
import sys
import time
import shutil
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

_SCRIPT_DIR = Path(__file__).resolve().parent
_CONFIG_PATH = _SCRIPT_DIR / "config.json"
_CONFIG_TEMPLATE_PATH = _SCRIPT_DIR / "config.template.json"


def _load_config() -> dict:
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"config.json not found at {_CONFIG_PATH}\n"
            f"Copy {_CONFIG_TEMPLATE_PATH.name} to config.json and fill in your local paths."
        )
    with _CONFIG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


_CONFIG = _load_config()

DEFAULT_NOTIFICATIONS_ROOT = Path(_CONFIG["notifications_root"])
DEFAULT_SOUND_DIR = Path(_CONFIG.get("sound_dir", str(DEFAULT_NOTIFICATIONS_ROOT / "sounds")))
SUPPORTED_SOUND_EXTENSIONS = {".mp3"}
MUTEX_NAME = "Global\\CodexClaudeAttentionNotify"


@dataclass(frozen=True)
class NotifyConfig:
    sound_dir: Path = DEFAULT_SOUND_DIR
    initial_delay_seconds: float = 2.0
    repeat_delay_seconds: float = 5.0
    poll_interval_seconds: float = 0.25
    recursive: bool = True


def discover_sound_files(sound_dir: Path, *, recursive: bool = True) -> list[Path]:
    sound_dir = sound_dir.expanduser().resolve()
    if not sound_dir.exists():
        return []

    iterator = sound_dir.rglob("*") if recursive else sound_dir.iterdir()
    sounds = [
        path
        for path in iterator
        if path.is_file() and path.suffix.lower() in SUPPORTED_SOUND_EXTENSIONS
    ]
    return sorted(sounds)


def wait_for_seconds_or_input(
    seconds: float,
    *,
    detector: Callable[[], bool],
    sleeper: Callable[[float], None],
    poll_interval_seconds: float,
) -> bool:
    remaining = max(0.0, seconds)
    while remaining > 0:
        if detector():
            return True
        step = min(poll_interval_seconds, remaining)
        sleeper(step)
        remaining -= step
    return detector()


def _windows_keyboard_pressed() -> bool:
    if os.name != "nt":
        return False

    user32 = ctypes.windll.user32
    for virtual_key in range(1, 256):
        if user32.GetAsyncKeyState(virtual_key) & 0x8000:
            return True
    return False


def _play_sound(path: Path) -> None:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SOUND_EXTENSIONS:
        raise ValueError(f"Unsupported sound file: {path}")

    if os.name != "nt":
        raise RuntimeError("Windows media playback is required.")

    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        raise RuntimeError("powershell.exe is required to play MP3 notifications.")

    path_text = str(path.resolve()).replace("'", "''")
    script = (
        "& { "
        "Add-Type -AssemblyName PresentationCore; "
        "$p = New-Object System.Windows.Media.MediaPlayer; "
        f"$p.Open([Uri]::new('{path_text}')); "
        "while(-not $p.NaturalDuration.HasTimeSpan) { Start-Sleep -Milliseconds 50 }; "
        "$p.Play(); "
        "Start-Sleep -Milliseconds ([int]$p.NaturalDuration.TimeSpan.TotalMilliseconds + 250) "
        "}"
    )

    subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", script],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


@contextmanager
def _single_instance_mutex() -> Iterator[bool]:
    if os.name != "nt":
        yield True
        return

    kernel32 = ctypes.windll.kernel32
    kernel32.SetLastError(0)
    handle = kernel32.CreateMutexW(None, True, MUTEX_NAME)
    already_running = ctypes.get_last_error() == 183
    try:
        yield not already_running
    finally:
        if handle and not already_running:
            kernel32.ReleaseMutex(handle)
            kernel32.CloseHandle(handle)
        elif handle:
            kernel32.CloseHandle(handle)


def _spawn_worker(config: NotifyConfig, stdin_payload: str) -> int:
    if os.name != "nt":
        return _run_worker(config, stdin_payload=stdin_payload)

    creation_flags = 0
    startupinfo = None
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        creation_flags |= subprocess.CREATE_NEW_PROCESS_GROUP
    if hasattr(subprocess, "DETACHED_PROCESS"):
        creation_flags |= subprocess.DETACHED_PROCESS

    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    except AttributeError:
        startupinfo = None

    args = [
        sys.executable,
        str(Path(__file__).resolve()),
        "worker",
        "--sounds",
        str(config.sound_dir),
        "--initial-delay",
        str(config.initial_delay_seconds),
        "--repeat-delay",
        str(config.repeat_delay_seconds),
        "--poll-interval",
        str(config.poll_interval_seconds),
    ]
    if not config.recursive:
        args.append("--no-recursive")

    subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
        startupinfo=startupinfo,
        cwd=str(DEFAULT_NOTIFICATIONS_ROOT),
    )
    return 0


def _run_worker(config: NotifyConfig, *, stdin_payload: str = "") -> int:
    del stdin_payload
    sounds = discover_sound_files(config.sound_dir, recursive=config.recursive)
    if not sounds:
        print(f"No supported sound files found in {config.sound_dir}", file=sys.stderr)
        return 2

    delay_seconds = config.initial_delay_seconds
    while True:
        selected_sound = random.choice(sounds)
        if wait_for_seconds_or_input(
            delay_seconds,
            detector=_windows_keyboard_pressed,
            sleeper=time.sleep,
            poll_interval_seconds=config.poll_interval_seconds,
        ):
            return 0
        _play_sound(selected_sound)
        delay_seconds = config.repeat_delay_seconds


def _codex_config_path() -> Path:
    return Path.home() / ".codex" / "config.toml"


def _claude_user_settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


def _notification_command(sound_dir: Path = DEFAULT_SOUND_DIR) -> list[str]:
    return [
        sys.executable,
        str(Path(__file__).resolve()),
        "hook",
        "--sounds",
        str(sound_dir.resolve()),
    ]


def _format_toml_array(values: list[str]) -> str:
    return "[" + ", ".join(json.dumps(value) for value in values) + "]"


def _merge_root_toml_key(text: str, key: str, value_toml: str) -> str:
    lines = text.splitlines()
    key_prefix = f"{key} = "
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(key_prefix):
            lines[index] = f"{key_prefix}{value_toml}"
            return "\n".join(lines).rstrip() + "\n"

    insert_at = len(lines)
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and not stripped.startswith("#"):
            insert_at = index
            break
    lines.insert(insert_at, f"{key_prefix}{value_toml}")
    return "\n".join(lines).rstrip() + "\n"


def _merge_claude_settings(text: str, command: list[str]) -> str:
    try:
        data = json.loads(text) if text.strip() else {}
        if not isinstance(data, dict):
            data = {}
    except json.JSONDecodeError:
        data = {}

    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}
    notification = hooks.get("Notification")
    if not isinstance(notification, list):
        notification = []

    command_str = " ".join(json.dumps(part) for part in command)
    script_token = json.dumps(str(Path(__file__).resolve()))

    notification = [
        hook
        for hook in notification
        if not (
            isinstance(hook, dict)
            and isinstance(hook.get("hooks"), list)
            and any(
                isinstance(inner, dict)
                and inner.get("type") == "command"
                and isinstance(inner.get("command"), str)
                and script_token in inner.get("command")
                for inner in hook.get("hooks", [])
            )
        )
    ]
    notification.append(
        {
            "hooks": [
                {
                    "type": "command",
                    "command": command_str,
                }
            ]
        }
    )
    hooks["Notification"] = notification
    data["hooks"] = hooks
    return json.dumps(data, indent=2) + "\n"


def setup_global_configs(*, sound_dir: Path = DEFAULT_SOUND_DIR) -> tuple[Path, Path]:
    sound_dir = sound_dir.resolve()
    codex_path = _codex_config_path()
    codex_path.parent.mkdir(parents=True, exist_ok=True)
    codex_text = codex_path.read_text(encoding="utf-8") if codex_path.exists() else ""
    codex_notify = _format_toml_array(_notification_command(sound_dir))
    codex_text = _merge_root_toml_key(codex_text, "notify", codex_notify)
    codex_path.write_text(codex_text, encoding="utf-8")

    claude_path = _claude_user_settings_path()
    claude_path.parent.mkdir(parents=True, exist_ok=True)
    claude_text = claude_path.read_text(encoding="utf-8") if claude_path.exists() else ""
    claude_text = _merge_claude_settings(claude_text, _notification_command(sound_dir))
    claude_path.write_text(claude_text, encoding="utf-8")
    return codex_path, claude_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="attention_notify")
    subparsers = parser.add_subparsers(dest="command", required=True)

    hook_parser = subparsers.add_parser("hook", help="Spawn a detached notifier worker for hooks.")
    hook_parser.add_argument("--sounds", type=Path, default=DEFAULT_SOUND_DIR)
    hook_parser.add_argument("--initial-delay", type=float, default=2.0)
    hook_parser.add_argument("--repeat-delay", type=float, default=5.0)
    hook_parser.add_argument("--poll-interval", type=float, default=0.25)
    hook_parser.add_argument("--no-recursive", action="store_true")

    worker_parser = subparsers.add_parser("worker", help="Run the detached notification loop.")
    worker_parser.add_argument("--sounds", type=Path, default=DEFAULT_SOUND_DIR)
    worker_parser.add_argument("--initial-delay", type=float, default=2.0)
    worker_parser.add_argument("--repeat-delay", type=float, default=5.0)
    worker_parser.add_argument("--poll-interval", type=float, default=0.25)
    worker_parser.add_argument("--no-recursive", action="store_true")

    global_parser = subparsers.add_parser("setup-global", help="Register the shared runner globally.")
    global_parser.add_argument("--sounds", type=Path, default=DEFAULT_SOUND_DIR)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "hook":
        config = NotifyConfig(
            sound_dir=args.sounds,
            initial_delay_seconds=args.initial_delay,
            repeat_delay_seconds=args.repeat_delay,
            poll_interval_seconds=args.poll_interval,
            recursive=not args.no_recursive,
        )
        stdin_payload = sys.stdin.read()
        with _single_instance_mutex() as acquired:
            if not acquired:
                return 0
            return _spawn_worker(config, stdin_payload)

    if args.command == "worker":
        config = NotifyConfig(
            sound_dir=args.sounds,
            initial_delay_seconds=args.initial_delay,
            repeat_delay_seconds=args.repeat_delay,
            poll_interval_seconds=args.poll_interval,
            recursive=not args.no_recursive,
        )
        stdin_payload = sys.stdin.read()
        return _run_worker(config, stdin_payload=stdin_payload)

    if args.command == "setup-global":
        codex_path, claude_path = setup_global_configs(sound_dir=args.sounds)
        print(f"Updated {codex_path}")
        print(f"Updated {claude_path}")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
