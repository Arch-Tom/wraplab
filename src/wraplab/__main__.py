import sys


def main():
    if len(sys.argv) >= 3 and sys.argv[1] in {"--self-test", "--acceptance-pack"}:
        try:
            if sys.argv[1] == "--self-test":
                from .selftest import run

                return run(sys.argv[2], resume="--resume" in sys.argv[3:])
            from .acceptance import build

            build(sys.argv[2])
            return 0
        except Exception:
            # Windowed Windows executables have no console. Preserve the failure without
            # a modal traceback dialog blocking automated native acceptance.
            from pathlib import Path
            import traceback

            target = Path(sys.argv[2])
            target.mkdir(parents=True, exist_ok=True)
            (target / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
            return 1
    if len(sys.argv) > 1 and sys.argv[1] == "convert":
        from .cli import run

        return run(sys.argv[2:])
    from .ui.app import launch

    return launch(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
