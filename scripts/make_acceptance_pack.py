"""Generate the same specimens as the packaged --acceptance-pack command."""

from pathlib import Path
import sys
from wraplab.acceptance import build

if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else Path("artifacts/corel-acceptance"))
