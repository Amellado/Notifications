param(
  [string]$SoundsRoot = "F:\2026-work\Notifications\sounds"
)

$script = Join-Path $PSScriptRoot "attention_notify.py"
$python = "C:\Users\darkf\AppData\Roaming\uv\python\cpython-3.13.11-windows-x86_64-none\python.exe"
& $python $script setup-global --sounds $SoundsRoot
