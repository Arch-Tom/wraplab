"""PyInstaller entry point; source and frozen builds use the same application."""

if __name__ == "__main__":
    import os
    from pathlib import Path
    import traceback

    diagnostic = os.environ.get("WRAPLAB_QA_LOG")

    def record(message):
        if diagnostic:
            with Path(diagnostic).open("a", encoding="utf-8") as handle:
                handle.write(message + "\n")

    record(f"Starting packaged process {os.getpid()}")
    try:
        from wraplab.__main__ import main

        result = main()
        record(f"Completed with result {result}")
    except Exception:
        if not diagnostic:
            raise
        # QA must expose startup/CLI exceptions instead of leaving a windowed
        # PyInstaller traceback dialog waiting for a person on the CI desktop.
        record(traceback.format_exc())
        raise SystemExit(1) from None
    raise SystemExit(result)
