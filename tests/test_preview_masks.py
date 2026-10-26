"""Synthetic contracts only. Customer artwork and projects remain private."""

from copy import deepcopy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from wraplab.domain import ObjectSpec, Project
from wraplab.geometry.surfaces import develop
from wraplab.masks.model import Assignment, MaskGroup, source_identity, validate_assignment
from wraplab.masks.planner import plan_masks
from wraplab.masks.exporter import export_masks
from wraplab.persistence import load_project, save_project
from wraplab.preview.scene import build_scene
from wraplab.preview.settings import options
from wraplab.svg import import_svg, convert, export_svg

SYNTHETIC = '''<svg xmlns="http://www.w3.org/2000/svg" width="60mm" height="70mm" viewBox="0 0 60 70">
<path fill-rule="evenodd" d="M10 2H50V12H10Z M15 4H22V10H15Z M12 18H48V28H12Z M18 20H24V26H18Z"/>
<path fill-rule="evenodd" d="M14 34H42V44H14Z M18 36H23V42H18Z"/>
<path fill-rule="evenodd" d="M10 54H50V66H10Z M17 57H24V63H17Z"/>
</svg>'''


@pytest.fixture
def job():
    art=import_svg(SYNTHETIC)
    p=Project(object=ObjectSpec(mode="measured",points=[(0,70),(30,80),(70,120),(100,160)]),
              artwork_frame="visible",source_svg=SYNTHETIC)
    p.placement.width,p.placement.height,p.placement.z,p.placement.x=30,48,25,2.25
    assignment=Assignment(source_identity(art),tuple(MaskGroup("MASK_"+name,((i,tuple(range(len(shape.subpaths)))),))
                          for i,(name,shape) in enumerate(zip("ABC",art.shapes,strict=True))))
    return art,p,assignment


@pytest.mark.parametrize("mode",["cylinder","frustum","measured"])
@pytest.mark.parametrize("workflow",["front-view-vinyl","surface-template"])
def test_scene_vertices_agree_with_canonical_mapper_and_development(mode,workflow):
    p=Project(object=ObjectSpec(mode=mode),physical_model=workflow)
    p.placement.width,p.placement.height=20,15
    p.center_artwork()
    surface=p.validate()
    locate=p.surface_mapper(60,25)
    mapper=p.mapper(60,25)
    development=p.development()
    for y in np.linspace(0,25,9):
        for x in np.linspace(0,60,11):
            theta,z=locate(complex(x,y))
            expected=complex(*develop(development,theta,z))
            assert mapper(complex(x,y))==expected
            if workflow=="front-view-vinyl":
                assert surface.radius(z)*math.sin(theta)==pytest.approx(p.placement.x+p.placement.width*(x/60-.5),abs=1e-12)
    scene=build_scene(p)
    assert scene.version==1 and scene.identity["preview_only"]
    assert all(math.isfinite(v) for vertex in scene.body for v in vertex)
    assert min(vertex[1] for vertex in scene.body)==pytest.approx(-surface.height/2)
    assert max(vertex[1] for vertex in scene.body)==pytest.approx(surface.height/2)


def test_measured_scene_stations_and_domain_are_not_extrapolated(job):
    art,p,_=job
    scene=build_scene(p,art)
    surface=p.object.surface()
    for z,diameter in surface.points:
        row=[v for v in scene.body if v[1]==surface.height/2-z]
        assert row
        assert max(abs(math.hypot(v[0],v[2])-diameter/2) for v in row)<1e-10
    assert "measured" in scene.warnings[0].lower()
    locate=p.surface_mapper(p.placement.width,p.placement.height)
    for vertex in scene.artwork_mesh[::113]:
        theta,z=locate(complex(p.placement.width*vertex[6],p.placement.height*vertex[7]))
        assert vertex[1]==pytest.approx(surface.height/2-z,abs=1e-11)
        assert math.atan2(vertex[0],vertex[2])==pytest.approx(theta,abs=1e-12)
        assert math.hypot(vertex[0],vertex[2])==pytest.approx(surface.radius(z)+scene.identity["display_decal_lift_mm"],abs=1e-11)
    with pytest.raises(ValueError,match="outside"):
        surface.radius(math.nextafter(surface.height,math.inf))


def test_global_split_keeps_exact_contours_combined_group_and_asymmetric_placement(job):
    art,p,assignment=job
    full=convert(art,p)
    plan=plan_masks(art,p,assignment)
    assert len(plan.masks)==3
    assert len(plan.masks[0].conversion.paths[0].contours)==4  # two rows plus both counters
    assert plan.topology=={"contours":8,"openings":4}
    for i,mask in enumerate(plan.masks):
        assert mask.conversion.paths[0].contours==full.paths[i].contours
        assert mask.mapping_project is p
        assert "does not reduce" in mask.warnings[0]
        assert len(mask.references)==3
        ref=mask.references[0]
        radius=p.object.surface().radius(ref["z_down_mm"])
        assert radius*math.sin(ref["theta_radians"])==pytest.approx(ref["front_x_mm"])
        assert ref["signed_front_arc_mm"]==pytest.approx(radius*ref["theta_radians"])
    assert (plan.masks[0].support[0]+plan.masks[0].support[2])/2==pytest.approx(2.25)


def test_independent_combined_fit_matches_recovered_independent_reference(job):
    art,p,assignment=job
    spec=importlib.util.spec_from_file_location("independent_mask_reference",Path(__file__).parents[1]/"research/four_group/independent.py")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    global_plan=plan_masks(art,p,assignment)
    independent=plan_masks(art,p,assignment,"independent")
    for before,after in zip(global_plan.masks,independent.masks,strict=True):
        assert before.references==after.references
        assert before.support==after.support
        reference=module.Fit(module.Profile(p.object.surface().points),after.support)
        development=after.mapping_project.development()
        assert development.k==pytest.approx(reference.k,abs=2e-10)
        left,top,right,bottom=after.support
        points=np.array([[x,z] for z in np.linspace(top,bottom,7) for x in np.linspace(left,right,9)])
        expected=reference.mapping(points)
        actual=np.array([develop(development,math.asin(x/p.object.surface().radius(z)),z) for x,z in points])
        assert np.max(np.abs(actual-expected))<2e-8
        restored,residual=reference.inverse(actual)
        assert residual<3e-6
        assert np.max(np.abs(restored-points))<2e-6
    assert len(independent.masks[0].conversion.paths[0].contours)==4


@pytest.mark.parametrize("problem",["source","duplicate","missing","opening"])
def test_assignment_must_authenticate_and_preserve_containment(job,problem):
    art,p,assignment=job
    groups=list(assignment.groups)
    if problem=="source":
        assignment=Assignment("0"*64,assignment.groups)
    elif problem=="duplicate":
        groups.append(groups[0])
        assignment=Assignment(assignment.source_sha256,tuple(groups))
    elif problem=="missing":
        assignment=Assignment(assignment.source_sha256,assignment.groups[:-1])
    else:
        groups[0]=MaskGroup("MASK_A",((0,(0,2,3)),))
        groups.append(MaskGroup("HOLE",((0,(1,)),)))
        assignment=Assignment(assignment.source_sha256,tuple(groups))
    with pytest.raises(ValueError):
        validate_assignment(assignment,art,p)


def test_margin_outside_measured_band_rejected_without_extrapolation(job):
    art,p,assignment=job
    with pytest.raises(ValueError,match="no extrapolation"):
        plan_masks(art,p,assignment,"independent",(0,0,0,40))
    p.wrap_degrees=55
    with pytest.raises(ValueError,match="coverage seam"):
        plan_masks(art,p,assignment,margins=(3,3,0,0))


def test_carrier_conflict_rejected_and_physical_datum_is_explicit(job):
    art,p,assignment=job
    with pytest.raises(ValueError,match="overlaps"):
        plan_masks(art,p,assignment,margins=(0,0,0,8))
    p.preview_options={"physical_top_datum_mm":200}
    plan=plan_masks(art,p,assignment)
    for mask in plan.masks:
        for ref in mask.references:
            assert ref["physical_height_above_operator_datum_mm"]==200-ref["z_down_mm"]


@pytest.mark.parametrize("method",["global-split","independent"])
def test_mask_package_true_size_topology_determinism_and_reference_separation(job,tmp_path,method):
    art,p,assignment=job
    before=export_svg(convert(art,p),p)
    plan,manifest=export_masks(tmp_path/"one",art,p,assignment,method,acknowledge_experimental=True)
    export_masks(tmp_path/"two",art,p,assignment,method,acknowledge_experimental=True)
    assert manifest["mask_count"]==3 and not manifest["physical_acceptance"]
    for entry,mask in zip(manifest["masks"],plan.masks,strict=True):
        data=(tmp_path/"one"/entry["file"]).read_bytes()
        assert data==(tmp_path/"two"/entry["file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest()==entry["sha256"]
        root=ET.fromstring(data)
        width,height=[float(root.get(k)[:-2]) for k in ("width","height")]
        assert width>0 and height>0
        assert root.get("viewBox")==f"0 0 {root.get('width')[:-2]} {root.get('height')[:-2]}"
        assert [g.get("id") for g in root.findall("{*}g")]==["Artwork"]
        assert not root.findall(".//{*}text") and not root.findall(".//{*}image")
        from wraplab.svg.importer import parse_subpaths
        assert sum(len(parse_subpaths(path.get("d"))) for path in root.findall(".//{*}path"))==sum(len(path.contours) for path in mask.conversion.paths)
        metadata=json.loads(root.find("{*}metadata").text)
        assert metadata["mask_planning"]["operation"]=="ARTWORK_CUT_CONTOURS_ONLY"
        assert not metadata["mask_planning"]["carrier_trim_cuts_included"]
    ref=ET.fromstring((tmp_path/"one/REFERENCE_ONLY_DO_NOT_CUT.svg").read_text(encoding="utf-8"))
    assert ref.find("{*}title").text=="REFERENCE_ONLY_DO_NOT_CUT"
    assert (tmp_path/"one/manifest.json").read_bytes()==(tmp_path/"two/manifest.json").read_bytes()
    assert export_svg(convert(art,p),p)==before


def test_export_gates_and_transaction_preserve_existing_files(job,tmp_path,monkeypatch):
    art,p,assignment=job
    existing=tmp_path/"existing"
    existing.mkdir()
    (existing/"keep.svg").write_text("preserve")
    with pytest.raises(ValueError,match="preserved"):
        export_masks(existing,art,p,assignment)
    assert (existing/"keep.svg").read_text()=="preserve"
    with pytest.raises(ValueError,match="Acknowledge"):
        export_masks(tmp_path/"candidate",art,p,assignment,"independent")
    from wraplab.masks import exporter
    real=exporter.atomic_write
    calls=0
    def failed_write(path,text):
        nonlocal calls
        calls+=1
        if calls==2:
            raise PermissionError("Simulated storage denial")
        real(path,text)
    monkeypatch.setattr(exporter,"atomic_write",failed_write)
    with pytest.raises(PermissionError):
        export_masks(tmp_path/"failure",art,p,assignment)
    assert not (tmp_path/"failure").exists()
    assert not list(tmp_path.glob(".wraplab-masks-*"))
    assert (existing/"keep.svg").read_text()=="preserve"


def test_old_projects_and_planning_preferences_round_trip_without_export_change(job,tmp_path):
    art,p,assignment=job
    before=export_svg(convert(art,p),p)
    legacy=p.to_dict()
    legacy.pop("preview_options")
    restored=Project.from_dict(legacy)
    assert restored.preview_options=={}
    p.preview_options=options({"assignment":assignment.to_dict(),"selected_mask":"MASK_A",
        "camera":[25,15,1.4,.1,-.1],"registration":True,"method":"independent"})
    path=tmp_path/"project.wraplab"
    save_project(path,p)
    assert load_project(path).to_dict()==json.loads(json.dumps(p.to_dict()))
    assert export_svg(convert(art,p),p)==before
    invalid=deepcopy(p.to_dict())
    invalid["preview_options"]["camera"][0]=float("nan")
    with pytest.raises(ValueError,match="finite"):
        Project.from_dict(invalid)
