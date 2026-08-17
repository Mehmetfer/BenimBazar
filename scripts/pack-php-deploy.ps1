# php-site -> changex-php-YAYIN-{tarih}.zip (cPanel)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Src = Join-Path $Root "php-site"
$Pack = Join-Path $Root "deploy-pack"
$Date = Get-Date -Format "yyyyMMdd-HHmm"
$Out = Join-Path $Root "changex-php-YAYIN-$Date.zip"

if (-not (Test-Path (Join-Path $Src "index.php"))) {
    Write-Host "php-site eksik" -ForegroundColor Red
    exit 1
}

if (Test-Path $Pack) { Remove-Item $Pack -Recurse -Force }
New-Item -ItemType Directory -Path $Pack | Out-Null
Copy-Item -Path (Join-Path $Src "*") -Destination $Pack -Recurse -Force
# Sunucudaki MySQL sifresini ezmesin diye database.php zip'e konmaz
$dbPack = Join-Path $Pack "config\database.php"
if (Test-Path $dbPack) { Remove-Item $dbPack -Force }
Copy-Item (Join-Path $Src "config\database.local.php.example") (Join-Path $Pack "config\database.local.php.example") -Force

foreach ($dir in @("uploads", "storage", "storage/sessions")) {
    $p = Join-Path $Pack $dir
    if (-not (Test-Path $p)) { New-Item -ItemType Directory -Path $p -Force | Out-Null }
}

if (Test-Path $Out) { Remove-Item $Out -Force }
Compress-Archive -Path (Join-Path $Pack "*") -DestinationPath $Out -Force

$mb = [math]::Round((Get-Item $Out).Length / 1MB, 2)
Write-Host "ZIP: $Out ($mb MB)" -ForegroundColor Green
Write-Host "cPanel: zip ac -> changex.mehmetfer.com.tr kokune yukle" -ForegroundColor Yellow
Write-Host "KURULUM: php-site/KURULUM.txt" -ForegroundColor Cyan
