# Notifications

Shared notification tooling for all projects in `F:\2026-work`.

## Layout

- `sounds\` - central folder for notification sounds
- `attention_notify.py` - shared runner used by Codex and Claude hooks
- `setup_global.ps1` - registers the shared runner in global Codex and Claude configs

## Behavior

- Picks a random sound from `sounds\`
- Waits 2 seconds before the first sound
- Repeats every 5 seconds
- Stops when keyboard input is detected
- Supports `.mp3` only

## Recommended setup

Run the global setup once:

```powershell
.\setup_global.ps1
```

That updates:

- `~/.codex/config.toml`
- `~/.claude/settings.json`

Both point at the same shared runner and sound folder.

There is no per-project setup. Every repo uses the same global hook and the
same shared sound folder.
