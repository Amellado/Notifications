# attention_notify

A lightweight attention notification tool for AI coding agents (Codex, Claude Code, etc.).

When an agent finishes a task and needs your attention, it plays a random sound from your sounds folder. Repeats until you press a key.

## How it works

- Picks a random sound from your `sounds/` folder
- Waits 2 seconds before the first sound (grace period to cancel)
- Repeats every 10 seconds until keyboard input is detected
- Stops on any keyboard or mouse button press
- Single-instance: multiple hook firings won't stack up
- No terminal flash — PowerShell runs fully hidden
- Supports `.mp3`

## Setup

### 1. Clone and configure

```bash
git clone https://github.com/Amellado/Notifications.git
cd Notifications
cp config.template.json config.json
```

Edit `config.json` with your local paths:

```json
{
  "notifications_root": "C:/path/to/Notifications",
  "sound_dir": "C:/path/to/Notifications/sounds",
  "python_executable": "python"
}
```

- `notifications_root` — absolute path to where you cloned this repo
- `sound_dir` — where your sound files live (usually `<notifications_root>/sounds`)
- `python_executable` — path to your Python 3 interpreter (`python`, `python3`, or a full path)

### 2. Add sounds

Drop `.mp3` files into the `sounds/` folder. They are gitignored — add your own.

### 3. Register globally

```powershell
.\setup_global.ps1
```

This writes the hook into:
- `~/.codex/config.toml` (Codex)
- `~/.claude/settings.json` (Claude Code)

Both point at the same runner and sound folder. No per-project setup needed.

## Layout

```
Notifications/
├── attention_notify.py     # The runner (used directly by hooks)
├── setup_global.ps1        # One-time global setup script
├── config.json             # Your local config (gitignored)
├── config.template.json    # Template — copy this to config.json
└── sounds/                 # Your sound files (gitignored)
    └── README.md
```

## Manual usage

```bash
# Trigger a notification manually
python attention_notify.py hook

# Trigger with visible debug logs
python attention_notify.py hook --debug

# Use a custom sounds folder
python attention_notify.py hook --sounds /path/to/sounds

# Run the worker in the foreground with debug logging
python attention_notify.py worker --debug

# Re-run global setup with a custom sounds path
python attention_notify.py setup-global --sounds /path/to/sounds
```

## Requirements

- Windows (uses PowerShell for MP3 playback via `System.Windows.Media.MediaPlayer`)
- Python 3.8+
- No third-party dependencies
