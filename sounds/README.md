# Sounds

Drop notification sounds in this folder. They are gitignored — bring your own.

Supported formats:

- `.wav` — plays directly, no extra tooling needed
- `.mp3` — needs ffmpeg (`winget install Gyan.FFmpeg`), converted once and cached

Keep them short. The runner picks one at random each time it fires.
