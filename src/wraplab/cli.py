"""Headless production conversion uses exactly the desktop pipeline."""

import argparse
from pathlib import Path

from .domain import ObjectSpec, Project
from .persistence import load_project
from .svg import convert, export_svg, import_svg
from .svg.exporter import write_export


def run(argv):
    parser = argparse.ArgumentParser(description="WrapLab offline surface-template SVG conversion")
    parser.add_argument("input", type=Path, help="Path-based SVG; source stays untouched")
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--project", type=Path, help="Use geometry/placement from a saved .wraplab file"
    )
    parser.add_argument("--mode", choices=["cylinder", "frustum", "measured"], default="cylinder")
    parser.add_argument(
        "--workflow", choices=["front-view-vinyl", "surface-template"], default="front-view-vinyl"
    )
    parser.add_argument("--diameter", type=float, default=80, help="Cylinder diameter in mm")
    parser.add_argument("--bottom", type=float, default=90, help="Frustum bottom diameter in mm")
    parser.add_argument("--top", type=float, default=65, help="Frustum top diameter in mm")
    parser.add_argument("--height", type=float, default=100, help="Axial object height in mm")
    parser.add_argument("--width", type=float, help="Artwork width in mm (aspect ratio preserved)")
    parser.add_argument("--coverage", type=float, default=180, help="Wrap coverage in degrees")
    parser.add_argument("--tolerance", type=float, default=0.01, help="Production tolerance in mm")
    parser.add_argument(
        "--export", choices=["artwork", "guides", "template", "original"], default="artwork"
    )
    args = parser.parse_args(argv)
    try:
        artwork = import_svg(args.input.read_text(encoding="utf-8-sig"))
        if args.project:
            project = load_project(args.project)
        else:
            project = Project(
                object=ObjectSpec(
                    mode=args.mode,
                    diameter=args.diameter,
                    bottom_diameter=args.bottom,
                    top_diameter=args.top,
                    height=args.height,
                ),
                wrap_degrees=args.coverage,
                export_tolerance_mm=args.tolerance,
                physical_model=args.workflow,
            )
            project.placement.width = args.width or artwork.width_mm
            project.placement.height = (
                artwork.height_mm * project.placement.width / artwork.width_mm
            )
            project.center_artwork()
        result = convert(artwork, project, original=args.export == "original")
        text = export_svg(result, project, args.export, args.input.name)
        write_export(args.output, text, args.input)
        print(
            f"Exported {args.output.name}: {result.node_count} nodes, {project.object.surface().status}"
        )
        for warning in result.warnings:
            print("Note:", warning)
        return 0
    except (ValueError, OSError) as exc:
        parser.exit(2, f"WrapLab: {exc}\n")
