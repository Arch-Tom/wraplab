"""Bounded, versioned, JSON-only preferences; no renderer or executable content."""

import math
from copy import deepcopy


DEFAULTS = {
    "version": 1, "view": "3d", "camera": [0, 0, 1, 0, 0],
    "selected_mask": "all", "isolate": False, "artwork": True, "cut_paths": False,
    "carriers": True, "registration": False, "seam": True, "bounds": True, "mask_layout": False,
    "method": "global-split", "margins_mm": [0, 0, 0, 0], "assignment": None,
    "physical_top_datum_mm": None,
}


def options(values=None):
    if not isinstance(values if values is not None else {}, dict):
        raise ValueError("Preview settings must be an object.")
    values = values or {}
    if values.keys() - DEFAULTS.keys():
        raise ValueError("Unsupported preview option; preserve the project and use its original application.")
    result = {**deepcopy(DEFAULTS), **deepcopy(values)}
    if result["version"] != 1 or result["view"] not in {"3d", "2d"}:
        raise ValueError("Unsupported preview settings version or view.")
    if result["method"] not in {"global-split", "independent"}:
        raise ValueError("Choose global split or experimental independent masks.")
    for key in ("isolate", "artwork", "cut_paths", "carriers", "registration", "seam", "bounds", "mask_layout"):
        if type(result[key]) is not bool:
            raise ValueError(f"Preview option {key} must be enabled or disabled.")
    camera, margins = result["camera"], result["margins_mm"]
    for sequence, count in ((camera, 5), (margins, 4)):
        if not isinstance(sequence, (tuple, list)) or len(sequence) != count or not all(
            type(v) in {int, float} and math.isfinite(v) for v in sequence
        ):
            raise ValueError("Camera and handling margins require finite numeric values.")
    if not (-360 <= camera[0] <= 360 and -85 <= camera[1] <= 85 and .2 <= camera[2] <= 8
            and all(abs(v) <= 4 for v in camera[3:])):
        raise ValueError("Saved camera lies outside the supported range. Reset its view.")
    if any(not 0 <= v <= 50 for v in margins):
        raise ValueError("Handling margins must be between 0 and 50 mm.")
    selected = result["selected_mask"]
    if not isinstance(selected, str) or len(selected) > 32:
        raise ValueError("Invalid selected mask.")
    if result["assignment"] is not None:
        from ..masks.model import assignment_from_dict
        assignment_from_dict(result["assignment"])
    datum=result["physical_top_datum_mm"]
    if datum is not None and (type(datum) not in {int,float} or not math.isfinite(datum) or abs(datum)>1_000_000):
        raise ValueError("Physical TOP datum must be a finite height in millimeters.")
    return result
