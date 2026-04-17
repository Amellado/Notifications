$configPath = Join-Path $PSScriptRoot "config.json"

if (-not (Test-Path $configPath)) {
    Write-Error "config.json not found. Copy config.template.json to config.json and fill in your local paths."
    exit 1
}

$config = Get-Content $configPath -Raw | ConvertFrom-Json

$python    = $config.python_executable
$soundsDir = $config.sound_dir
$script    = Join-Path $PSScriptRoot "attention_notify.py"

& $python $script setup-global --sounds $soundsDir
