from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class Affine:
    a: float = 1
    b: float = 0
    c: float = 0
    d: float = 1
    e: float = 0
    f: float = 0

    def __call__(self, p: complex):
        return complex(
            self.a * p.real + self.c * p.imag + self.e, self.b * p.real + self.d * p.imag + self.f
        )

    def __matmul__(self, other):
        o = other
        return Affine(
            self.a * o.a + self.c * o.b,
            self.b * o.a + self.d * o.b,
            self.a * o.c + self.c * o.d,
            self.b * o.c + self.d * o.d,
            self.a * o.e + self.c * o.f + self.e,
            self.b * o.e + self.d * o.f + self.f,
        )

    @property
    def scale_bound(self):
        return (self.a**2 + self.b**2 + self.c**2 + self.d**2) ** 0.5


@dataclass(frozen=True)
class Subpath:
    segments: tuple[Any, ...]
    closed: bool


@dataclass(frozen=True)
class Shape:
    subpaths: tuple[Subpath, ...]
    transform: Affine
    style: Mapping[str, str]
    name: str


@dataclass(frozen=True)
class Artwork:
    width_mm: float
    height_mm: float
    shapes: tuple[Shape, ...]
    source: str
    warnings: tuple[str, ...] = ()


@dataclass
class Contour:
    points: list[complex]
    closed: bool = True


@dataclass
class VectorPath:
    contours: list[Contour]
    fill: str = "#000000"
    fill_rule: str = "nonzero"
    opacity: float = 1.0
    stroke: str = "none"
    stroke_width: float = 0.0


@dataclass
class Conversion:
    paths: list[VectorPath]
    warnings: list[str]
    tolerance_mm: float

    @property
    def node_count(self):
        return sum(len(c.points) for p in self.paths for c in p.contours)
