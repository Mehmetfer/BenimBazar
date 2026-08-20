# Otomatik canli deploy (FTP)
# Kullanim:  .\deploy.ps1
# veya:      python scripts\deploy_live_php.py

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
python (Join-Path $PSScriptRoot "scripts\deploy_live_php.py")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Deploy bitti." -ForegroundColor Green
