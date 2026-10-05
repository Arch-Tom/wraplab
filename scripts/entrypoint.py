"""PyInstaller entry point; source and frozen builds use the same application."""

from wraplab.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
