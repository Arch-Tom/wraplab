"""Append small CI reports to a dedicated branch; never force-push or publish binaries in Git."""

import json
import os
from pathlib import Path
import shutil
import subprocess


def git(repo, *args, check=True):
    return subprocess.run(
        ["git", "-C", str(repo), *args], text=True, capture_output=True, check=check
    )


def main():
    repo = Path("evidence-checkout")
    branch = "release-evidence"
    query = git(repo, "ls-remote", "--exit-code", "--heads", "origin", branch, check=False)
    if query.returncode == 0:
        git(repo, "fetch", "origin", branch)
        git(repo, "checkout", "-B", branch, "FETCH_HEAD")
    elif query.returncode == 2:
        git(repo, "checkout", "--orphan", branch)
        git(repo, "rm", "-rf", "--ignore-unmatch", ".")
    else:
        raise RuntimeError(query.stderr)
    source = os.environ["GITHUB_SHA"]
    run = os.environ["GITHUB_RUN_ID"] + "-" + os.environ["GITHUB_RUN_ATTEMPT"]
    destination = repo / "evidence" / source / run
    assert not destination.exists(), "Evidence record already exists; do not overwrite it"
    destination.mkdir(parents=True)
    for path in Path("evidence-downloads").rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {
            ".json",
            ".xml",
            ".log",
            ".txt",
            ".md",
            ".csv",
            ".svg",
            ".png",
        }:
            continue
        target = destination / "reports" / path.relative_to("evidence-downloads")
        target.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".log":
            target.write_bytes(path.read_bytes()[-100000:])
        elif path.stat().st_size <= 2_000_000:
            shutil.copyfile(path, target)
    summary = {
        "source_commit": source,
        "source_tree": os.environ["SOURCE_TREE"],
        "run_id": os.environ["GITHUB_RUN_ID"],
        "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
        "workflow_run_url": os.environ["GITHUB_SERVER_URL"]
        + "/"
        + os.environ["GITHUB_REPOSITORY"]
        + "/actions/runs/"
        + os.environ["GITHUB_RUN_ID"],
        "jobs": json.loads(os.environ["JOB_RESULTS"]),
        "coreldraw_2019_verified": False,
        "physical_bell_verified": False,
    }
    (destination / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    git(repo, "config", "user.name", "WrapLab CI")
    git(repo, "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    git(repo, "add", "evidence")
    git(repo, "commit", "-m", f"Record release validation {source[:12]} run {run}")
    for _ in range(3):
        pushed = git(repo, "push", "origin", f"HEAD:refs/heads/{branch}", check=False)
        if pushed.returncode == 0:
            print(str(destination))
            return
        git(repo, "pull", "--rebase", "origin", branch)
    raise RuntimeError("Evidence push failed after concurrent-update retries")


if __name__ == "__main__":
    main()
