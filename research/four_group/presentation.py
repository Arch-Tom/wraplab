"""Standalone research figures and a true-size front reference, not product UI."""

from copy import deepcopy
import json
import xml.etree.ElementTree as ET

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from wraplab.svg import convert, export_svg

from .artifacts import label, line, root_svg, save_svg
from .core import split_global_svg

COLORS = ["#2977b7", "#008370", "#d47b21", "#9862b1"]


def figures(output, config, art, group_art, global_project, local_projects, rows, baseline):
    folder = output / "ANALYSIS_NOT_FOR_CUTTING"
    folder.mkdir()
    plt.rcParams.update({"font.size": 9, "svg.fonttype": "none"})
    names = list(group_art)
    fig, ax = plt.subplots(figsize=(9, 4.5), layout="constrained")
    a = baseline["A"]["fit"]
    z = np.linspace(a.support[1], a.support[3], 501)
    ax.plot(
        float(config["physical_top_height_in"]) - z / 25.4,
        100 * a.strain(z),
        color="#182c40",
        label="A and B: same global field",
    )
    for name, color in zip(names, COLORS, strict=True):
        fit = baseline[name]["fit"]
        z = np.linspace(fit.support[1], fit.support[3], 201)
        ax.plot(
            float(config["physical_top_height_in"]) - z / 25.4,
            100 * fit.strain(z),
            color=color,
            lw=2,
            label="C: " + name,
        )
    ax.set(
        xlabel="Physical height above common bottom datum (in)",
        ylabel="Modeled application strain (%)",
        title="Nominal reconstruction: global field versus independently fitted group bands",
    )
    ax.axhline(0, color="#aaa", lw=0.6)
    ax.grid(alpha=0.2)
    ax.legend(fontsize=8)
    fig.savefig(folder / "modeled-strain.svg")
    fig.savefig(folder / "modeled-strain.pdf")
    plt.close(fig)

    valid = [r for r in rows if r["complete_layout_valid"]]
    fig, axes = plt.subplots(1, 2, figsize=(12, 8), layout="constrained")
    values = np.array(
        [[r["fits"][n]["C_to_AB_max_abs_strain_ratio"] for n in names] for r in valid]
    )
    m = axes[0].imshow(values, aspect="auto", vmin=0, vmax=1, cmap="viridis_r")
    axes[0].set_xticks(range(4), names, rotation=25, ha="right")
    axes[0].set_yticks(range(len(valid)), [r["scenario"]["id"] for r in valid], fontsize=7)
    axes[0].set_title(
        "C / A-or-B maximum absolute strain\nWithin each group band; lower is less modeled strain"
    )
    fig.colorbar(m, ax=axes[0], shrink=0.6)
    geometric = np.array(
        [
            [
                r["fits"][n].get("change_from_nominal", {}).get("sampled_max_difference_mm", 0)
                for n in names
            ]
            for r in valid
        ]
    )
    m = axes[1].imshow(geometric, aspect="auto", cmap="magma")
    axes[1].set_xticks(range(4), names, rotation=25, ha="right")
    axes[1].set_yticks(range(len(valid)), [""] * len(valid))
    axes[1].set_title(
        "Change from nominal C contours (sampled mm)\nMean translation removed; no rotation removed"
    )
    fig.colorbar(m, ax=axes[1], shrink=0.6, label="mm")
    fig.savefig(folder / "hypothetical-sensitivity.svg")
    fig.savefig(folder / "hypothetical-sensitivity.pdf")
    plt.close(fig)

    from .core import source_samples, target_points

    fig, axes = plt.subplots(4, 1, figsize=(10, 11), layout="constrained")
    for ax, name, color in zip(axes, names, COLORS, strict=True):
        targets = target_points(
            source_samples(group_art[name], 17), art.visible_frame, global_project
        )
        A = baseline["A"]["fit"].mapping(targets)
        C = baseline[name]["fit"].mapping(targets)
        p = local_projects[name].placement
        center = np.array([[p.x, p.z + p.height / 2]])
        translation = (
            baseline[name]["fit"].mapping(center) - baseline["A"]["fit"].mapping(center)
        )[0]
        C -= translation
        ax.scatter(A[:, 0], A[:, 1], s=0.8, color="#182c40", label="A/B global")
        ax.scatter(C[:, 0], C[:, 1], s=0.8, color=color, label="C after target-center translation")
        ax.set_aspect("equal")
        ax.invert_yaxis()
        ax.set_title(name + " — no rotation removed")
        ax.set_xlabel("Flat X (mm)")
        ax.set_ylabel("Flat Y (mm)")
        ax.legend(markerscale=4, fontsize=8)
    fig.savefig(folder / "sampled-shape-comparison.svg")
    fig.savefig(folder / "sampled-shape-comparison.pdf")
    plt.close(fig)

    # This file contains reference lines/text and is never placed in artwork-only.
    original = export_svg(convert(art, global_project, original=True), global_project, "original")
    w, h = global_project.placement.width, global_project.placement.height
    sheet = root_svg(
        w + 40, h + 50, "REFERENCE ONLY — intended front layout, not a flat cutting pattern"
    )
    for definition, color in zip(config["groups"], COLORS, strict=True):
        subset = ET.fromstring(
            split_global_svg(
                original_with_research(original), definition, condition="front-reference"
            )
        )
        shape = deepcopy(subset.find("{*}g"))
        shape.set("transform", "translate(20 20)")
        for child in shape:
            child.set("fill", color)
        sheet.append(shape)
    line(sheet, w / 2 + 20, 15, w / 2 + 20, h + 25, "#777")
    label(sheet, 4, 5, "REFERENCE ONLY — DO NOT CUT / PRINT AT 100%", 3)
    label(
        sheet,
        4,
        11,
        "Intended front layout, not a physical flat wrap. Nominal reconstruction.",
        2.5,
    )
    label(sheet, 4, h + 30, "Top: 7.8 in; bottom: 3.8 in above common bottom datum.", 2.5)
    label(sheet, 4, h + 35, "x=0 is the shared front center; star is +2.19579 mm off center.", 2.5)
    line(sheet, 20, h + 42, 120, h + 42, "#000")
    label(sheet, 45, h + 40, "100 mm X", 2.5)
    line(sheet, w + 33, 20, w + 33, 120, "#000")
    label(sheet, w + 12, 17, "100 mm Y", 2.5)
    save_svg(sheet, output / "REFERENCE_ONLY_DO_NOT_CUT/REFERENCE_ONLY_true_size_front_layout.svg")


def original_with_research(text):
    root = ET.fromstring(text)
    node = root.find("{*}metadata")
    data = json.loads(node.text)
    data["research"] = {"warning": "REFERENCE ONLY — DO NOT CUT"}
    node.text = json.dumps(data)
    return ET.tostring(root, encoding="unicode")
