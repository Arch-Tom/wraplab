"""Capture/compare 72 synthetic production exports without packaging or GUI."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wraplab.domain import ObjectSpec, Project  # noqa: E402
from wraplab.svg import convert, export_svg, import_svg  # noqa: E402


def records():
    result = {}
    for filename in ("lettering.svg", "primitives.svg", "corel-like-transparent.svg"):
        art = import_svg((ROOT / "tests/fixtures" / filename).read_text(encoding="utf-8"))
        for mode in ("cylinder", "frustum", "measured"):
            for frame_name in ("page", "visible"):
                for scale in (1, 1.5):
                    p = Project(object=ObjectSpec(mode=mode), artwork_frame=frame_name)
                    frame = p.source_frame(art)
                    p.placement.width = 20 * scale
                    p.placement.height = p.placement.width * frame.height / frame.width
                    p.center_artwork()
                    conversion = convert(art, p)
                    for output in ("artwork", "guides"):
                        text = export_svg(conversion, p, output, filename)
                        key = f"{filename}/{mode}/{frame_name}/{scale}/{output}"
                        result[key] = hashlib.sha256(text.encode()).hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path)
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    result = records()
    assert len(result) == 72
    if args.capture:
        with args.capture.open("x", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, sort_keys=True)
    if args.compare:
        expected = json.loads(args.compare.read_text())
        different = [key for key in expected if result.get(key) != expected[key]]
        if different or result.keys() != expected.keys():
            raise RuntimeError(f"Protected exports changed: {different}")
    print("72 deterministic production export hashes " + ("matched" if args.compare else "captured"))


if __name__ == "__main__":
    main()
