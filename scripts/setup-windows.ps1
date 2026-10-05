$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
py -3.12 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is required.' }
& .\.venv\Scripts\python.exe -m pip install --disable-pip-version-check -r requirements.lock
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& .\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
if ($LASTEXITCODE -ne 0) { throw 'WrapLab installation failed.' }
& .\.venv\Scripts\python.exe scripts/patch_build_dependencies.py
if ($LASTEXITCODE -ne 0) { throw 'Documented Windows dependency patch failed.' }
Write-Output 'Launch: .\.venv\Scripts\python.exe -m wraplab'
