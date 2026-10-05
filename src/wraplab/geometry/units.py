"""All persisted/model lengths are millimeters. Display conversions never mutate them."""

import math
from enum import StrEnum


class Unit(StrEnum):
    MM = "mm"
    INCH = "in"

    @property
    def millimeters(self) -> float:
        return 25.4 if self == Unit.INCH else 1.0

    def to_mm(self, value: float) -> float:
        return finite(value) * self.millimeters

    def from_mm(self, value: float) -> float:
        return finite(value) / self.millimeters


def finite(value: float, label: str = "Measurement") -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a number.")
    try:
        number = float(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{label} must be a number.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite.")
    return number


def positive(value: float, label: str) -> float:
    value = finite(value, label)
    if not 0 < value <= 1_000_000:
        raise ValueError(f"{label} must be positive and no greater than 1,000,000 mm.")
    return value
