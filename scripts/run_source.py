"""Launch Windows source with the checkout's isolated Python and Qt environment."""

import os
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]


def configure():
    if sys.platform != "win32" or sys.version_info[:3] != (3, 12, 10):
        raise RuntimeError("Use Windows x64 with Python 3.12.10 for this source launcher.")
    if not sys.flags.isolated:
        raise RuntimeError("Launch with Python's -I option to exclude inherited Python paths.")
    environment = ROOT / ".venv"
    if Path(sys.prefix).resolve() != environment.resolve():
        raise RuntimeError("Launch with this checkout's .venv/Scripts/python.exe or pythonw.exe.")
    base = Path(sys.base_prefix)
    windows = Path(os.environ.get("SystemRoot", "C:/Windows"))
    os.environ["PATH"] = os.pathsep.join(map(str, [
        environment / "Scripts", base, base / "DLLs", windows / "System32", windows,
    ]))
    for key in list(os.environ):
        if key.startswith(("QT_", "QML_")):
            del os.environ[key]
    plugins = environment / "Lib/site-packages/PySide6/plugins"
    os.environ["QT_PLUGIN_PATH"] = str(plugins)
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(plugins / "platforms")
    os.environ["QT_QPA_PLATFORM"] = "windows"
    sys.path.insert(0, str(ROOT / "src"))


def main():
    output = ROOT / "artifacts/source-run"
    output.mkdir(parents=True, exist_ok=True)
    with (output / "gui.log").open("a", encoding="utf-8", buffering=1) as log:
        sys.stdout = sys.stderr = log
        try:
            configure()
            os.chdir(ROOT)
            from PySide6.QtCore import qInstallMessageHandler
            from wraplab.__main__ import main as launch

            qInstallMessageHandler(lambda kind, context, message: print("Qt:", message, file=log))
            print("Starting WrapLab directly from source", flush=True)
            return launch()
        except Exception:
            traceback.print_exc(file=log)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
