"""External Windows QA observer. Not shipped or called by the application."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

from bundle_inventory import write_inventory
from release_checks import compare_directories, digest
from windows_runtime import Observer, WinAPI, file_snapshot, wait_for_window

ROOT = Path(__file__).resolve().parents[1]
BASE_SHA = "9a214b50cdf6d9d27cf8a3cf92bd92bb420181ec"
BASE_ZIP_SHA = "5d68abbc7fd8d62ef4c9c45927476c9df47e48af0bfc292ee212cacaa83d7e5b"
BASE_URL = "https://github.com/Arch-Tom/wraplab/releases/download/v0.1.0-rc4/WrapLab-0.1.0-Windows-x64-portable.zip"


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


class Trace:
    """Ordinary ETW diagnostics on a disposable CI runner; no endpoint settings changed."""
    def __init__(self, output):
        self.output = output
        self.name = f"WrapLabAudit-{os.getpid()}"
        self.etl = output / "kernel.etl"
        self.records = []
        self.active = False

    def command(self, args):
        result = subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=180)
        self.records.append({"command": args, "exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
        return result.returncode == 0

    def start(self):
        args = ["logman", "create", "trace", self.name, "-o", str(self.etl), "-bs", "1024", "-nb", "16", "256"]
        for provider, keywords in [
            ("Microsoft-Windows-Kernel-Process", "0x70"),
            ("Microsoft-Windows-Kernel-File", "0xffffffffffffffff"),
            ("Microsoft-Windows-Kernel-Network", "0xffffffffffffffff"),
            ("Microsoft-Windows-Kernel-Registry", "0xffffffffffffffff"),
            ("Microsoft-Windows-WMI-Activity", "0xffffffffffffffff"),
        ]:
            args += ["-p", provider, keywords, "5"]
        self.active = self.command([*args, "-ets"])

    def finish(self, cases):
        active = self.active
        if active:
            self.command(["logman", "stop", self.name, "-ets"])
            self.active = False
            self.command(["tracerpt", str(self.etl), "-o", str(self.output / "kernel.xml"), "-of", "XML", "-summary", str(self.output / "trace-summary.txt"), "-y"])
        save(self.output / "trace-commands.json", self.records)
        result = {"started": active, "parsed": False, "limitations": ["CI runner only; SentinelOne absent. Trace covers app processes, not all shell/OS broker work on their behalf."]}
        xml = self.output / "kernel.xml"
        if not xml.exists():
            result["limitations"].append("ETW unavailable: polling and static source/bundle audit cannot exclude very short events or transient deleted files.")
            return result
        ns = {"e": "http://schemas.microsoft.com/win/2004/08/events/event"}
        pids = {r["pid"] for case in cases for r in case.get("process_tree", [])}
        selected, counts = [], {}
        # First pass finds short-lived children not captured by polling. PID ownership
        # is constrained to the recorded test window; raw trace remains available.
        child_events = []
        for _, event in ET.iterparse(xml, events=["end"]):
            if event.tag.rsplit("}", 1)[-1] != "Event":
                continue
            system = event.find("e:System", ns)
            if system is not None:
                provider = system.find("e:Provider", ns)
                if provider is not None and provider.get("Name") == "Microsoft-Windows-Kernel-Process":
                    data = {d.get("Name", ""): d.text for d in event.findall("e:EventData/e:Data", ns)}
                    try:
                        parent = int(data.get("ParentProcessID", "-1"), 0)
                        pid = int(data.get("ProcessID", "-1"), 0)
                        if parent in pids and pid not in pids:
                            pids.add(pid)
                            child_events.append(data)
                    except (ValueError, TypeError):
                        pass
            event.clear()
        for _, event in ET.iterparse(xml, events=["end"]):
            if event.tag.rsplit("}", 1)[-1] != "Event":
                continue
            system = event.find("e:System", ns)
            if system is not None:
                execution = system.find("e:Execution", ns)
                data = {d.get("Name", ""): d.text for d in event.findall("e:EventData/e:Data", ns)}
                ids = [execution.get("ProcessID", "-1") if execution is not None else "-1"]
                ids += [data.get(k, "-1") for k in ["ProcessID", "ProcessId", "PID", "ClientProcessId"]]
                matches = False
                for value in ids:
                    try:
                        matches |= int(value, 0) in pids
                    except (ValueError, TypeError):
                        pass
                if matches:
                    provider = system.find("e:Provider", ns)
                    name = provider.get("Name", "") if provider is not None else "unknown"
                    task = system.find("e:Task", ns)
                    opcode = system.find("e:Opcode", ns)
                    event_id = system.find("e:EventID", ns)
                    created = system.find("e:TimeCreated", ns)
                    row = {"provider": name, "event_id": event_id.text if event_id is not None else None,
                           "task": task.text if task is not None else None, "opcode": opcode.text if opcode is not None else None,
                           "timestamp": created.get("SystemTime") if created is not None else None,
                           "execution_pid": execution.get("ProcessID") if execution is not None else None, "data": data}
                    selected.append(row)
                    counts[name] = counts.get(name, 0) + 1
            event.clear()
        save(self.output / "app-etw-events.json", selected)
        result.update(parsed=True, app_events=len(selected), events_by_provider=counts, additional_child_events=child_events)
        if not selected:
            result["limitations"].append("No decoded app events; inspect raw ETL/XML before drawing absence conclusions.")
        return result


def delta(before, after):
    return {"created": {k: v for k, v in after.items() if k not in before},
            "changed": {k: v for k, v in after.items() if k in before and v != before[k]},
            "deleted": [k for k in before if k not in after]}


def run_case(api, mode, operation, command, output, install):
    case = output / f"{mode}-{operation}"
    case.mkdir()
    temp = case / "TEMP"
    temp.mkdir()
    env = dict(os.environ, TEMP=str(temp), TMP=str(temp), QT_QPA_PLATFORM="windows", WRAPLAB_QA_LOG=str(case / "app-diagnostics.log"))
    local = Path(os.environ["LOCALAPPDATA"]) / "WrapLab" / "WrapLab"
    roots = {"TEMP": temp, "LOCALAPPDATA/WrapLab/WrapLab": local, "install": install}
    before = file_snapshot(roots)
    started = datetime.now(timezone.utc).isoformat()
    with (case / "process.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        observer = Observer(api, process.pid)
        failure = None
        try:
            if operation == "gui":
                window = wait_for_window(api, process, timeout=60)
                time.sleep(5)
                assert api.user.PostMessageW(window["handle"], 0x10, 0, 0), "WM_CLOSE failed"
            process.wait(timeout=180)
            assert process.returncode == 0, f"Application exited with {process.returncode}"
        except Exception as exc:
            failure = repr(exc)
            # Cleanup only the process this QA harness started, not any unrelated app.
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=30)
        finally:
            observed = observer.finish()
    after = file_snapshot(roots)
    report = {"mode": mode, "operation": operation, "command": command, "observer_parent_pid": os.getpid(),
              "started": started, "ended": datetime.now(timezone.utc).isoformat(), "exit_code": process.returncode,
              "failure": failure, "filesystem_delta": delta(before, after), **observed}
    save(case / "runtime.json", report)
    assert failure is None, report
    assert not report["observer_errors"], report["observer_errors"]
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-root", type=Path, default=ROOT / "artifacts/releases/Windows")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/forensics")
    args = parser.parse_args()
    assert sys.platform == "win32", "Native Windows required"
    output, release = args.output.resolve(), args.release_root.resolve()
    output.mkdir(parents=True)
    summary = {"status": "running", "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
               "baseline_commit": BASE_SHA, "sentinelone_available": False, "cases": [], "coreldraw_verified": False}
    trace = Trace(output)
    try:
        baseline_zip = output / "baseline-rc4.zip"
        urllib.request.urlretrieve(BASE_URL, baseline_zip)
        assert digest(baseline_zip) == BASE_ZIP_SHA
        baseline = output / "baseline"
        with zipfile.ZipFile(baseline_zip) as archive:
            assert archive.testzip() is None
            archive.extractall(baseline)
        baseline /= "WrapLab"
        candidate = release / "Extracted shop install שלום" / "WrapLab"
        baseline_inventory = write_inventory(baseline, output / "baseline-bundle.json")
        candidate_inventory = write_inventory(candidate, output / "candidate-bundle.json")
        summary["bundle_comparison"] = {"baseline_native_count": baseline_inventory["native_count"], "candidate_native_count": candidate_inventory["native_count"],
                                       "removed": sorted({r["path"] for r in baseline_inventory["native_files"]} - {r["path"] for r in candidate_inventory["native_files"]})}
        summary["baseline_zip_sha256"] = digest(baseline_zip)
        summary["candidate_zip"] = json.loads((release / "release-files.json").read_text())[0]
        summary["candidate_executable_sha256"] = digest(candidate / "WrapLab.exe")
        api = WinAPI()
        trace.start()
        modes = {"source": [str(Path(sys.executable).with_name("pythonw.exe")), "-m", "wraplab"],
                 "rc4": [str(baseline / "WrapLab.exe")], "diagnostic": [str(candidate / "WrapLab.exe")]}
        for mode, prefix in modes.items():
            install = {"source": ROOT / "src", "rc4": baseline, "diagnostic": candidate}[mode]
            # Clean ordinary launch; import/manipulation/export is exercised by the
            # next in-process functional QA case, without automating file dialogs.
            summary["cases"].append(run_case(api, mode, "gui", prefix, output, install))
            destination = output / f"{mode}-exports"
            summary["cases"].append(run_case(api, mode, "workflows", [*prefix, "--self-test", str(destination)], output, install))
            summary["cases"].append(run_case(api, mode, "restart", [*prefix, "--self-test", str(destination), "--resume"], output, install))
            pack = output / f"{mode}-corel"
            summary["cases"].append(run_case(api, mode, "acceptance", [*prefix, "--acceptance-pack", str(pack)], output, install))
        summary["comparisons"] = {}
        for mode in ["source", "diagnostic"]:
            # Self-test source input is deliberately not a production M/L/Z export.
            for name in ["rc4", mode]:
                comparison = output / f"{name}-comparison"
                comparison.mkdir(exist_ok=True)
                for path in (output / f"{name}-exports").glob("*.svg"):
                    if path.name != "self-test-source.svg":
                        shutil.copyfile(path, comparison / path.name)
            summary["comparisons"][f"rc4-vs-{mode}-workflows"] = compare_directories(output / "rc4-comparison", output / f"{mode}-comparison")
            summary["comparisons"][f"rc4-vs-{mode}-corel"] = compare_directories(output / "rc4-corel", output / f"{mode}-corel")
        for case in summary["cases"]:
            assert not case["child_processes"], case
            assert not case["network_endpoints"], case
            assert not case["visible_console_observed"], case
            if case["mode"] != "source":
                d = case["filesystem_delta"]
                assert not any(k.startswith("install/") for section in d.values() for k in section), case
                assert not any("\\temp\\" in module.lower() and module.lower().endswith((".dll", ".pyd", ".exe")) for module in case["loaded_modules"]), case
        summary["status"] = "passed"
    except Exception as exc:
        summary.update(status="failed", error=repr(exc))
        raise
    finally:
        summary["etw"] = trace.finish(summary["cases"])
        save(output / "forensic-report.json", summary)


if __name__ == "__main__":
    main()
