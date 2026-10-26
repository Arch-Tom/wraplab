"""Separate, deterministic mask packages. No change to ordinary SVG export."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import xml.etree.ElementTree as ET

from ..persistence import atomic_write
from ..svg import export_svg
from ..svg.exporter import number, validate_serialized
from .planner import plan_masks


def mask_svg(mask, plan, project):
    text = export_svg(mask.conversion, mask.mapping_project, "artwork", project.source_name)
    root = ET.fromstring(text)
    metadata = root.find("{*}metadata")
    record = json.loads(metadata.text)
    record["mask_planning"] = {
        "version": 1, "mask": mask.id, "method": plan.method,
        "source_sha256": plan.source_sha256, "profile_sha256": plan.profile_sha256,
        "operation": "ARTWORK_CUT_CONTOURS_ONLY", "carrier_trim_cuts_included": False,
        "experimental": plan.method == "independent" or project.object.mode == "measured",
        "physical_acceptance": False, "support_front_xz_mm": list(mask.support),
        "registration": mask.references, "warnings": mask.warnings + plan.warnings,
    }
    root.find("{*}title").text = (
        "EXPERIMENTAL — " if record["mask_planning"]["experimental"] else "") + mask.id + " — artwork cutting contours only"
    metadata.text = json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    ET.indent(root, space="  ")
    text = '<?xml version="1.0" encoding="UTF-8"?>\n'+ET.tostring(root, encoding="unicode")+'\n'
    validate_serialized(text, mask.conversion.paths, complex(*record["page_origin_mm"]))
    return text, record


def reference_svg(plan, project):
    surface = project.object.surface()
    zs = [surface.height*(i/160) for i in range(160)]+[surface.height]
    radius = max(surface.radius(z) for z in zs)
    pad = max(8., surface.height*.07)
    width, height = 2*radius+2*pad, surface.height+2*pad
    root = ET.Element("svg", xmlns="http://www.w3.org/2000/svg", width=number(width)+"mm",
                      height=number(height)+"mm", viewBox=f"{number(-radius-pad)} {number(-pad)} {number(width)} {number(height)}")
    ET.SubElement(root,"title").text = "REFERENCE_ONLY_DO_NOT_CUT"
    ET.SubElement(root,"metadata").text = json.dumps({"operation":"REFERENCE_ONLY_DO_NOT_CUT",
        "source_sha256":plan.source_sha256,"profile_sha256":plan.profile_sha256,
        "units":"mm","z":"down from measured TOP","horizontal":"front projected x; tape arcs listed separately",
        "method":plan.method,"physical_acceptance":False},sort_keys=True)
    group = ET.SubElement(root,"g",id="REFERENCE_ONLY_DO_NOT_CUT",fill="none",stroke="#61818b",
                          **{"stroke-width":"0.2"})
    outline = [(-surface.radius(z),z) for z in zs]+[(surface.radius(z),z) for z in reversed(zs)]
    ET.SubElement(group,"path",d=" ".join(("M" if i==0 else "L")+number(x)+" "+number(z)
                  for i,(x,z) in enumerate(outline))+" Z")
    ET.SubElement(group,"path",d=f"M0 0 L0 {number(surface.height)}",stroke="#b56e25")
    for mask in plan.masks:
        left,top,right,bottom=mask.support
        ET.SubElement(group,"rect",x=number(left),y=number(top),width=number(right-left),
                      height=number(bottom-top),**{"data-mask":mask.id})
        for ref in mask.references:
            x,z=ref["front_x_mm"],ref["z_down_mm"]
            ET.SubElement(group,"path",d=f"M{number(x-1.5)} {number(z)} h3 M{number(x)} {number(z-1.5)} v3")
            ET.SubElement(root,"text",x=number(x+2),y=number(z-2),fill="#6b511e",
                          **{"font-size":"2.6"}).text=mask.id+" "+ref["label"]
    ET.SubElement(root,"text",x=number(-radius),y=number(-pad/2),fill="#953e2e",
                  **{"font-size":"3.2"}).text="REFERENCE_ONLY_DO_NOT_CUT · mm · measured band only"
    return '<?xml version="1.0" encoding="UTF-8"?>\n'+ET.tostring(root,encoding="unicode")+'\n'


def export_masks(destination, artwork, project, assignment, method="global-split", margins=(0,0,0,0),
                 acknowledge_experimental=False):
    """All files become visible together in a NEW directory, or none do.

    Existing destinations are never replaced. Reference guides cannot enter a mask SVG.
    """
    destination=Path(destination).resolve()
    if destination.exists():
        raise ValueError("Choose a new mask-package folder. Existing files will be preserved.")
    if method=="independent" and not acknowledge_experimental:
        raise ValueError("Acknowledge the experimental independent fit before exporting candidate masks.")
    plan=plan_masks(artwork,project,assignment,method,margins)
    files, records={},[]
    for mask in plan.masks:
        text,record=mask_svg(mask,plan,project)
        filename=mask.id+".svg"
        files[filename]=text
        records.append({"file":filename,"mask":mask.id,
            "sha256":hashlib.sha256(text.encode()).hexdigest(),
            "flat_dimensions_mm":[float(ET.fromstring(text).get(k)[:-2]) for k in ("width","height")],
            "flat_origin_in_common_mapping_mm":record["page_origin_mm"],
            "support_front_xz_mm":list(mask.support),"registration":mask.references,
            "carrier_boundary_flat_reference_mm":[[point.real,point.imag] for point in mask.carrier_flat],
            "flat_reference_positions_mm":[{"label":ref["label"],"common_mapping_mm":[point.real,point.imag],
                "cut_canvas_mm":[point.real-record["page_origin_mm"][0],point.imag-record["page_origin_mm"][1]]}
                for ref,point in zip(mask.references,mask.flat_reference_points,strict=True)],
            "modeled_strain_range":list(mask.strain),"operation":"ARTWORK_CUT_CONTOURS_ONLY"})
    files["REFERENCE_ONLY_DO_NOT_CUT.svg"]=reference_svg(plan,project)
    instructions=["WRAPLAB MASK REGISTRATION — REFERENCE ONLY — DO NOT CUT",
        "Software candidate; no material, cutter or CorelDRAW approval.",
        "Mark the same FRONT meridian and measured TOP datum on the object for every mask.",
        "z-down is straight vertical distance below measured TOP, in mm.",
        "Tape arc is SIGNED circumferential distance at that height from FRONT; it is not projected x.",
        "Positive arc is to the viewer's right in the original front view; negative is left.",
        "L, R and TOP are three noncollinear reference positions, not cutter marks.",
        "Blank-page gaps and independent flat-pattern positions are NOT installation spacing.",
        "Carrier edges have no added trim cuts; zero margins provide no handling allowance."]
    for mask in plan.masks:
        instructions.append("\n"+mask.id+" — "+plan.method)
        for ref in mask.references:
            line=f"{ref['label']}: z-down {ref['z_down_mm']:.6f} mm; front tape arc {ref['signed_front_arc_mm']:+.6f} mm"
            height=ref["physical_height_above_operator_datum_mm"]
            if height is not None:
                line+=f"; physical height above recorded datum {height:.6f} mm"
            instructions.append(line)
    files["REGISTRATION_REFERENCE_ONLY_DO_NOT_CUT.txt"]="\n".join(instructions)+"\n"
    manifest={"version":1,"units":"mm","method":method,"mask_count":len(plan.masks),
        "source_sha256":plan.source_sha256,"profile_sha256":plan.profile_sha256,
        "profile":project.to_dict()["object"],"placement":vars(project.placement),
        "artwork_frame":project.artwork_frame,"margins_left_right_top_bottom_mm":list(margins),
        "source_topology":plan.topology,"global_modeled_strain_range":list(plan.global_strain),
        "masks":records,"assignment":assignment.to_dict(),"warnings":plan.warnings,
        "reference_file":"REFERENCE_ONLY_DO_NOT_CUT.svg", "physical_acceptance":False,
        "coreldraw_2019_verified":False,"carrier_trim_cuts_included":False,
        "registration_rule":"Place using common on-object references, never global flat-pattern gaps.",
        "measurement_limit":"No geometry extrapolated beyond the measured stations."}
    files["manifest.json"]=json.dumps(manifest,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False)+"\n"
    # Generate and validate everything before creating output. Same-filesystem rename
    # of a unique staging directory commits the complete package on Windows.
    destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=Path(tempfile.mkdtemp(prefix=".wraplab-masks-",dir=destination.parent))
    try:
        for filename,text in files.items():
            atomic_write(temporary/filename,text)
        if destination.exists():
            raise FileExistsError("The chosen package folder appeared during export; preserved it.")
        os.rename(temporary,destination)
    finally:
        if temporary.exists():
            # This is only the unique, locally created staging directory above.
            if temporary.resolve().parent != destination.parent or not temporary.name.startswith(".wraplab-masks-"):
                raise RuntimeError("Unexpected staging path; cleanup refused.")
            shutil.rmtree(temporary)
    return plan,manifest
