# Security scanning for LendFlow
$ErrorActionPreference = 'Continue'

# Ensure UTF-8 output for Python-based tools
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

Write-Host "`n=== Bandit (Python SAST) ===" -ForegroundColor Cyan
bandit -c .bandit -r apps core config -ll -f screen

Write-Host "`n=== pip-audit (dependency CVEs) ===" -ForegroundColor Cyan
pip-audit -r requirements/base.txt

Write-Host "`n=== Semgrep (Django rules) ===" -ForegroundColor Cyan
semgrep --config=p/django apps core
if ($LASTEXITCODE -eq 0) {
    Write-Host "Semgrep: clean." -ForegroundColor Green
}

Write-Host "`nDone." -ForegroundColor Green