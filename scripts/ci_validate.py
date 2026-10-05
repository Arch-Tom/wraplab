"""Preserve native CI evidence and command failures, including failed package builds."""

import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "ci"
OUT.mkdir(parents=True, exist_ok=True)
REPORT = {
    "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "platform": platform.platform(),
    "python": platform.python_version(),
    "checks": [],
    "status": "running",
}


def save():
    (OUT / "summary.json").write_text(json.dumps(REPORT, indent=2) + "\n", encoding="utf-8")


def run(name, command, timeout=1800):
    started = time.monotonic()
    with (OUT / (name + ".log")).open("w", encoding="utf-8") as handle:
        result = subprocess.run(
            command, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT, timeout=timeout
        )
    REPORT["checks"].append(
        {
            "name": name,
            "exit_code": result.returncode,
            "seconds": round(time.monotonic() - started, 2),
        }
    )
    save()
    if result.returncode:
        print((OUT / (name + ".log")).read_text(encoding="utf-8", errors="replace")[-16000:])
        raise RuntimeError(name + " failed")


def main():
    try:
        run("install", [sys.executable, "-m", "pip", "install", "-r", "requirements.lock"])
        run(
            "project-install",
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--no-build-isolation",
                "-e",
                ".",
            ],
        )
        run("dependency-check", [sys.executable, "-m", "pip", "check"])
        if os.name == "nt":
            run("documented-dependency-patch", [sys.executable, "scripts/patch_build_dependencies.py"])
        run("lint", [sys.executable, "-m", "ruff", "check", "src", "tests", "scripts"])
        run("tests", [sys.executable, "-m", "pytest", "-q", "--junitxml", str(OUT / "tests.xml")])
        cases = ET.parse(OUT / "tests.xml").getroot().findall(".//testcase")
        assert len(cases) >= 150 and not any(c.find("skipped") is not None for c in cases)
        independent = sum(
            c.get("name", "").startswith("test_complete_independent_packet_a_corpus[")
            for c in cases
        )
        assert independent == 18
        REPORT["tests_passed"] = len(cases)
        REPORT["independent_fixtures_passed"] = independent
        audit_env = ROOT / "artifacts" / "audit-env"
        run("audit-environment", [sys.executable, "-m", "venv", str(audit_env)])
        audit_python = audit_env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        run("audit-install", [str(audit_python), "-m", "pip", "install", "pip-audit==2.10.1"])
        run(
            "security-audit",
            [
                str(audit_python),
                "-m",
                "pip_audit",
                "--disable-pip",
                "--no-deps",
                "-r",
                "requirements.lock",
                "-f",
                "json",
                "-o",
                str(OUT / "dependency-audit.json"),
            ],
        )
        build_command = [sys.executable, "scripts/build_portable.py"]
        if "--diagnostic" in sys.argv[1:]:
            build_command.append("--diagnostic")
        run("portable-build", build_command)
        REPORT["status"] = "passed"
        return 0
    except Exception as exc:
        REPORT["status"] = "failed"
        REPORT["error"] = str(exc)
        return 1
    finally:
        save()


if __name__ == "__main__":
    sys.exit(main())
