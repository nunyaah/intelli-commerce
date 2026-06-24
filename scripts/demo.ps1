# "Break it" demo (Windows / PowerShell). Deterministic + free, ~30s.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$env:RELIABILITY_MOCK = "1"
$env:RELIABILITY_DB = ".reliability/demo.db"

Write-Host "=== IntelliCommerce Agent Reliability - break-it demo ===" -ForegroundColor Cyan
python -m reliability.cli demo
