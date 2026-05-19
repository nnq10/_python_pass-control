$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

python -m PyInstaller `
  --noconfirm `
  --clean `
  --windowed `
  --name PassControl `
  --icon data\assets\app_icon.ico `
  --collect-all customtkinter `
  pass_control.py

$targetData = Join-Path $root "dist\PassControl\data"
if (Test-Path $targetData) {
  Remove-Item -LiteralPath $targetData -Recurse -Force
}

$sourceData = Join-Path $root "data"
New-Item -ItemType Directory -Force -Path $targetData | Out-Null

foreach ($file in @("passes.db", "users.json", "settings.json")) {
  $source = Join-Path $sourceData $file
  if (Test-Path $source) {
    Copy-Item -LiteralPath $source -Destination (Join-Path $targetData $file)
  }
}

foreach ($dir in @("photos", "qrcodes", "templates", "sounds", "assets")) {
  $source = Join-Path $sourceData $dir
  $target = Join-Path $targetData $dir
  if (Test-Path $source) {
    Copy-Item -LiteralPath $source -Destination $target -Recurse
  } else {
    New-Item -ItemType Directory -Force -Path $target | Out-Null
  }
}

foreach ($dir in @("prints", "backups")) {
  New-Item -ItemType Directory -Force -Path (Join-Path $targetData $dir) | Out-Null
}

Write-Host ""
Write-Host "Done: dist\PassControl\PassControl.exe"
Write-Host "For deployment, copy the whole dist\PassControl folder."
