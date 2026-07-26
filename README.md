# attention_notify

A lightweight one-shot notification tool for AI coding agents (Claude Code, Codex, etc.).

When an agent needs your attention, it plays a random sound from your sounds folder once.

## How it works

- Picks a random sound from your `sounds/` folder
- Plays it immediately
- Single-instance: multiple hook firings won't stack up
- No terminal flash — playback runs fully detached and hidden
- Plays `.wav` directly; `.mp3` is converted once to a cached `.wav` via ffmpeg

## Install (Windows)

```powershell
git clone https://github.com/Amellado/Notifications.git
cd Notifications
.\install.ps1
```

`install.ps1` does everything:

1. Finds a usable Python 3.8+ (tries the `py` launcher, then `PATH`, then the
   usual install locations and uv-managed interpreters). It rejects the
   Microsoft Store stub and anything that can't `import winsound`.
2. Detects ffmpeg — on `PATH` or installed via winget.
3. Writes `config.json` with the paths for *this* machine.
4. Registers the hook globally for Claude Code and Codex.
5. Precaches your mp3 files and plays one test sound.

Then **restart Claude Code** so it reads the new hook.

Re-running it is safe: it rewrites `config.json` and replaces its own hook entry
instead of stacking duplicates.

If PowerShell refuses to run the script:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

### Options

```powershell
.\install.ps1 -Sounds "D:\my-sounds"          # keep sounds outside the repo
.\install.ps1 -Python "C:\path\to\python.exe" # skip autodetection
.\install.ps1 -SkipTest                       # don't play a test sound
```

### Add sounds

Sound files are **not** in this repo — they're gitignored. Drop your own short
clips into `sounds/`:

- `.wav` plays with no extra tooling. Prefer this if you don't want ffmpeg.
- `.mp3` needs ffmpeg: `winget install Gyan.FFmpeg`, then re-run `.\install.ps1`.

The installer registers the hook even with an empty folder — it just stays
silent until you add audio.

## Requirements

- Windows (`winsound` playback)
- Python 3.8+ — the installer tells you how to get it if you don't have it
- ffmpeg, only if you use `.mp3` sounds
- No third-party Python packages

## Layout

```
Notifications/
├── attention_notify.py     # The runner (used directly by hooks)
├── install.ps1             # One-shot installer — start here
├── setup_global.ps1        # Re-register the hook using an existing config.json
├── config.json             # Your local config (gitignored, written by install.ps1)
├── config.template.json    # Reference for the config fields
├── .wav-cache/             # Converted mp3 -> wav cache (gitignored)
└── sounds/                 # Your sound files (gitignored)
    └── README.md
```

### config.json

`install.ps1` generates this for you. Fields:

| Field | Meaning |
| --- | --- |
| `notifications_root` | Absolute path to this checkout |
| `sound_dir` | Where your sound files live |
| `python_executable` | Absolute path to the Python interpreter |
| `ffmpeg_executable` | `ffmpeg`, or an absolute path to it |

If `config.json` is missing, the runner falls back to the repo layout (checkout
as root, `sounds/` next to it, `ffmpeg` from `PATH`), so a fresh clone still
plays sounds — you only lose the machine-specific overrides.

## Manual usage

```bash
# Trigger a notification the way the hook does (detached worker)
python attention_notify.py hook

# Same, with visible debug logs
python attention_notify.py hook --debug

# Use a custom sounds folder
python attention_notify.py hook --sounds /path/to/sounds

# Run playback in the foreground with debug logging — best way to test
python attention_notify.py worker --debug

# Preconvert all MP3 files into cached WAV files
python attention_notify.py precache --debug

# Re-register the global hooks with a custom sounds path
python attention_notify.py setup-global --sounds /path/to/sounds
```

## Troubleshooting

Run the foreground worker first — it prints exactly what happens:

```powershell
python attention_notify.py worker --debug
```

| Symptom | Cause |
| --- | --- |
| `No supported sound files found` | Empty `sounds/`, or `sound_dir` points somewhere wrong |
| `ffmpeg is required to play MP3 notifications` | ffmpeg missing — install it or switch to `.wav` |
| Worker exits silently, code 0 | Another instance holds the single-instance mutex |
| Nothing fires from the agent | Claude Code wasn't restarted after install |

To confirm the hook is registered, check the `hooks.Notification` entry in
`~/.claude/settings.json` and the `notify` key in `~/.codex/config.toml`.
