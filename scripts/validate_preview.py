"""Native source-only renderer/mask QA. Customer input and output must stay private."""

import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]


def module(name,path,package=False):
    spec=importlib.util.spec_from_file_location(name,path,
        submodule_search_locations=[str(path.parent)] if package else None)
    result=importlib.util.module_from_spec(spec)
    sys.modules[name]=result
    spec.loader.exec_module(result)
    return result


def run(args):
    module("preview_source_launcher",ROOT/"scripts/run_source.py").configure()
    if args.scale_factor!=1:
        import os
        if not 1<=args.scale_factor<=2:
            raise ValueError("QA scale must be between 1 and 2")
        os.environ["QT_SCALE_FACTOR"]=str(args.scale_factor)
    from PySide6.QtCore import QPoint, qVersion
    from PySide6.QtWidgets import QApplication
    from wraplab.domain import Project
    from wraplab.masks.model import cantor_assignment, cantor_trial
    from wraplab.masks.exporter import export_masks
    from wraplab.persistence import save_project
    from wraplab.preview.settings import options
    from wraplab.svg import import_svg
    from wraplab.ui.app import MainWindow,STYLE

    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    reference=args.reference_source.resolve()
    module("preview_reference",reference/"src/wraplab/__init__.py",True)
    domain=__import__("preview_reference.domain",fromlist=["Project"])
    svg=__import__("preview_reference.svg",fromlist=["convert"])
    app=QApplication([])
    assert app.platformName()=="windows"
    app.setStyleSheet(STYLE)
    source=args.private_svg if args.private_svg else ROOT/"tests/fixtures/lettering.svg"
    art=import_svg(source.read_bytes().decode("utf-8-sig"))
    p=cantor_trial(art) if args.private_svg else Project(source_svg=art.source,source_name=source.name)
    if not args.private_svg:
        p.placement.height=16.666666666666668
    w=MainWindow(output/"user-data")
    windows=[w]

    def settle():
        deadline=time.monotonic()+90
        while w._busy or w._timer.isActive():
            app.processEvents()
            time.sleep(.01)
            if time.monotonic()>deadline:
                raise RuntimeError("Native source preview timed out")
        for _ in range(6):
            app.processEvents()

    def screenshot(name,width=1370,height=900):
        w.resize(width,height)
        app.processEvents()
        assert w.grab().save(str(output/(name+".png")))
        bounds=w.export_button.rect().translated(w.export_button.mapTo(w,QPoint(0,0)))
        assert w.rect().contains(bounds),"Ordinary export button is clipped"

    report={"qt_platform":app.platformName(),"python":sys.version.split()[0],"qt":qVersion(),
            "scale_factor":args.scale_factor,"private_customer_source":bool(args.private_svg),
            "packaged":False,"physical_acceptance":False,"coreldraw_tested":False}
    try:
        w.project,w.artwork=p,art
        w._load_controls()
        w.refresh()
        w.show()
        settle()
        assert w.scene_view.isValid() and not w.scene_view.failure
        assert w._scene and w.export_button.isEnabled()
        data=p.to_dict()
        data.pop("preview_options",None)
        baseline=domain.Project.from_dict(data)
        baseline_art=svg.import_svg(art.source)
        comparisons=[]
        for mode in ("artwork","guides","template","original"):
            _,text=w.export_to(output/("ordinary-"+mode+".svg"),mode)
            old=svg.convert(baseline_art,baseline,original=mode=="original") if mode!="template" else None
            expected=svg.export_svg(old,baseline,mode,p.source_name)
            assert text==expected, "Ordinary export changed: "+mode
            comparisons.append(mode)
        screenshot("front")
        for name in ("Left","Right","Rear","Seam","Front"):
            w.scene_view.set_camera_view(name)
            app.processEvents()
            assert not w.scene_view.grabFramebuffer().isNull()
            screenshot("camera-"+name.lower())
        screenshot("compact",1050,700)
        screenshot("minimum",980,650)
        w.resize(1370,900)
        app.processEvents()
        report["ordinary_byte_identical_modes"]=comparisons
        report["graphics_context_valid"]=True
        if args.private_svg:
            assignment=cantor_assignment(art)
            plans={}
            for method in ("global-split","independent"):
                settings=options(w.project.preview_options)
                settings.update(method=method,mask_layout=method=="independent")
                w.preview_settings_changed(settings)
                settle()
                assert w._plan is not None
                plan,manifest=export_masks(output/("masks-"+method),art,w.project,assignment,method,
                    acknowledge_experimental=True)
                assert len(plan.masks)==3 and plan.topology=={"contours":44,"openings":12}
                assert [m.id for m in plan.masks]==["STAR","HEBREW","CANTORLAND"]
                assert sum(len(v.contours) for v in plan.masks[1].conversion.paths)==22
                plans[method]={"topology":plan.topology,"global_strain":plan.global_strain,
                    "masks":[{"id":m.id,"strain":m.strain,"support":m.support,"references":m.references}
                             for m in plan.masks],"manifest_mask_count":manifest["mask_count"]}
                screenshot("method-"+method)
                for selected in ("STAR","HEBREW","CANTORLAND"):
                    settings=options(w.project.preview_options)
                    settings.update(selected_mask=selected,isolate=True,registration=True,cut_paths=True)
                    w.preview_settings_changed(settings)
                    app.processEvents()
                    assert w.planner.mask.currentData()==selected
                    assert len(w.mask_canvas.mask_items)==1
                    screenshot(method+"-"+selected.lower())
            report["plans"]=plans
        project_path=output/"saved-project.wraplab"
        save_project(project_path,w.project)
        expected_options=w.project.preview_options
        w.dirty=False
        w.close()
        app.processEvents()
        w=MainWindow(output/"reopened-data")
        windows.append(w)
        w.load_file(project_path)
        w.show()
        settle()
        assert w.project.preview_options==expected_options
        assert w.scene_view.isValid() and not w.scene_view.failure
        screenshot("reopened")
        report.update(status="passed",save_close_reopen="passed",camera_views="passed",
                      frame_cpu_ms=w.scene_view.last_frame_ms)
        (output/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
        print(json.dumps({k:v for k,v in report.items() if k!="plans"},indent=2))
    finally:
        for window in windows:
            window.dirty=False
            window.close()
        app.processEvents()


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--reference-source",type=Path,required=True)
    parser.add_argument("--private-svg",type=Path)
    parser.add_argument("--scale-factor",type=float,default=1.)
    run(parser.parse_args())
