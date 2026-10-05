# Restore WrapLab from durable source

Use the published release tag or exact source commit recorded in its validation JSON:

```
git clone https://github.com/Arch-Tom/wraplab.git WrapLab
cd WrapLab
git checkout <release-tag-or-commit>
```

On Windows install Python 3.12, run scripts/setup-windows.ps1, then use .venv/Scripts/python.exe.
On Linux run `bash scripts/setup.sh`, then use .venv/bin/python. Dependencies are pinned in
requirements.lock. Runtime operation is offline; installation needs the package registry.

From that interpreter run:

```
python -m pip check
python -m pytest -q
python -m ruff check src tests scripts
python -m wraplab --self-test artifacts/restoration-smoke
python scripts/build_portable.py
```

For headless Linux, set QT_QPA_PLATFORM=offscreen and writable XDG_DATA_HOME/XDG_CACHE_HOME.
Native Windows package validation requires QT_QPA_PLATFORM=windows. The release script selects
these correctly. It places new artifacts under artifacts/releases/<OS>; do not overwrite a completed
release directory. Read docs/windows-release.md for publication, checksums and operator instructions.

A Git bundle can recover the complete preserved history when the remote is unavailable:
`git clone WrapLab-source.bundle WrapLab-recovered`. It contains source history, not installed
Python dependencies or release ZIPs. Verify the bundle with `git bundle verify` before recovery.

Do not claim a fresh restore passed until the clone, new environment, installation and actual tests/
launch have completed. The cloud configuration draft and the running machine are separate; publication
and a new cloud task are separate from a manually tested fresh checkout. Evidence records distinguish them.
