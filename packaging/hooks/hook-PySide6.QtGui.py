"""Keep PyInstaller's stock Qt collection, omitting the unused network TUIO backend.

Native Windows touch/mouse input continues through qwindows. WrapLab has no TUIO feature.
This is a build hook; it is not shipped or run by WrapLab.
"""

from pathlib import Path

from PyInstaller.utils.hooks.qt import add_qt6_dependencies

hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
binaries = [
    item for item in binaries if "tuiotouch" not in Path(item[0]).name.lower()
]
