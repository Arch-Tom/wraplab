import sys


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        from .selftest import run

        return run(sys.argv[2])
    if len(sys.argv) > 1 and sys.argv[1] == "convert":
        from .cli import run

        return run(sys.argv[2:])
    from .ui.app import launch

    return launch(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
