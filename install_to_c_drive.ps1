$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$source = Join-Path $root "dist\PassControl"
$target = "C:\PassControl"
$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "PassControl.lnk"

if (-not (Test-Path $source)) {
  throw "Build folder not found: $source. Run build_exe.ps1 first."
}

if (Test-Path $target) {
  $backup = "C:\PassControl_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
  Move-Item -LiteralPath $target -Destination $backup
  Write-Host "Old installation moved to: $backup"
}

Copy-Item -LiteralPath $source -Destination $target -Recurse

$exe = Join-Path $target "PassControl.exe"
$sourceExe = Join-Path $source "PassControl.exe"
$icon = Join-Path $target "data\assets\app_icon.ico"
$shell = New-Object -ComObject WScript.Shell

Get-ChildItem -LiteralPath $desktop -Filter "*.lnk" -ErrorAction SilentlyContinue | ForEach-Object {
  try {
    $oldShortcut = $shell.CreateShortcut($_.FullName)
    if (($oldShortcut.TargetPath -eq $exe) -or ($oldShortcut.TargetPath -eq $sourceExe)) {
      Remove-Item -LiteralPath $_.FullName -Force
    }
  } catch {
  }
}

$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $exe
$shortcut.WorkingDirectory = $target
if (Test-Path $icon) {
  $shortcut.IconLocation = $icon
} else {
  $shortcut.IconLocation = "$exe,0"
}
$shortcut.Save()

Write-Host "Installed to: $target"
Write-Host "Desktop shortcut: $shortcutPath"
Write-Host "Local data folder: C:\PassControl\data"
