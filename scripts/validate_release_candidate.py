#!/usr/bin/env python3
"""Validate a finished build-only run before reusing its release artifacts."""

import argparse
import hashlib
import json
import re
import runpy
import subprocess
import tempfile
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

WORKFLOW = ".github/workflows/build-desktop-apps.yml"
PLATFORMS = {
    "Build Windows installer and feed": (
        "Verify installation and available upgrade path",
        "Verify installed Trial Cruncher UI",
        "Verify packaged CLI analysis",
        "Upload Windows release payload",
    ),
    "Build signed macOS installer and feed": (
        "Build signed and notarized macOS Velopack release",
        "Verify installation and available upgrade path",
        "Verify installed Trial Cruncher UI",
        "Verify packaged CLI analysis",
        "Upload macOS release payload",
    ),
}
ARTIFACTS = ("stable-windows-release", "stable-macos-release")


def api(endpoint):
    return json.loads(subprocess.check_output(["gh", "api", endpoint], text=True))


def validate(run, jobs, artifacts, repo, sha, *, current_run=False, release_tag=None):
    """Return immutable artifact identifiers and hashes, or raise ValueError."""
    if (
        run.get("repository", {}).get("full_name") != repo
        or run.get("head_repository", {}).get("full_name") != repo
        or run.get("path") != WORKFLOW
        or run.get("head_sha") != sha
        or (
            not current_run
            and (
                run.get("event") != "workflow_dispatch"
                or run.get("head_branch") != "main"
                or run.get("status") != "completed"
                or run.get("conclusion") != "success"
            )
        )
        or (
            current_run
            and (
                run.get("status") != "in_progress"
                or (run.get("event"), run.get("head_branch"))
                not in {("workflow_dispatch", "main"), ("push", release_tag)}
            )
        )
    ):
        raise ValueError("Candidate run is not a successful main build of this commit.")
    by_name = {job.get("name"): job for job in jobs}
    if len(by_name) != len(jobs):
        raise ValueError("Candidate has duplicate job names.")
    required_ci = {
        f"Full CI / Full tests ({system}, {python})"
        for system in ("ubuntu-latest", "windows-latest", "macos-latest")
        for python in ("3.12", "3.14")
    }
    if any(by_name.get(name, {}).get("conclusion") != "success" for name in required_ci):
        raise ValueError("Candidate must pass the complete six-job test matrix.")
    for name in required_ci:
        if not any(
            step.get("name") == "Test" and step.get("conclusion") == "success"
            for step in by_name[name].get("steps", [])
        ):
            raise ValueError(f"Test execution unverified in {name}.")
    lint_steps = {
        step.get("name"): step.get("conclusion")
        for step in by_name["Full CI / Full tests (ubuntu-latest, 3.12)"].get("steps", [])
    }
    if any(lint_steps.get(name) != "success" for name in ("Lint", "Check formatting")):
        raise ValueError("Candidate must pass lint and format checks.")
    for name, required_steps in PLATFORMS.items():
        job = by_name.get(name, {})
        steps = {step.get("name"): step.get("conclusion") for step in job.get("steps", [])}
        if job.get("conclusion") != "success" or any(
            steps.get(step) != "success" for step in required_steps
        ):
            raise ValueError(f"Candidate did not pass all {name} checks.")
    publish = by_name.get("Publish verified stable release")
    if not current_run and (publish is None or publish.get("conclusion") != "skipped"):
        raise ValueError("Candidate was not a build-only run.")
    selected = {}
    for name in ARTIFACTS:
        matches = [item for item in artifacts if item.get("name") == name]
        if len(matches) != 1:
            raise ValueError(f"Candidate artifact {name} is missing or duplicated.")
        item = matches[0]
        digest = item.get("digest", "")
        if item.get("expired") is not False or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise ValueError(f"Candidate artifact {name} is expired or lacks a SHA-256 digest.")
        if (
            item.get("workflow_run", {}).get("id") != run.get("id")
            or item["workflow_run"].get("head_sha") != sha
            or type(item.get("id")) is not int
        ):
            raise ValueError(f"Candidate artifact {name} has invalid provenance.")
        platform_job = by_name[
            "Build Windows installer and feed"
            if name == "stable-windows-release"
            else "Build signed macOS installer and feed"
        ]
        try:
            created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
            started = datetime.fromisoformat(platform_job["started_at"].replace("Z", "+00:00"))
            completed = datetime.fromisoformat(platform_job["completed_at"].replace("Z", "+00:00"))
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError(f"Candidate artifact {name} lacks a valid creation time.") from exc
        if not started - timedelta(seconds=1) <= created <= completed + timedelta(seconds=1):
            raise ValueError(
                f"Candidate artifact {name} does not match the successful job attempt."
            )
        selected[name] = {"id": item["id"], "digest": digest}
    return selected


def discover(repo, sha):
    # Slurp every page to avoid mistaking pagination for a missing candidate.
    endpoint = (
        f"repos/{repo}/actions/workflows/build-desktop-apps.yml/runs"
        f"?event=workflow_dispatch&head_sha={sha}&branch=main&status=success&per_page=100"
    )
    pages = json.loads(
        subprocess.check_output(["gh", "api", "--paginate", "--slurp", endpoint], text=True)
    )
    if not isinstance(pages, list) or any("workflow_runs" not in page for page in pages):
        raise ValueError("Invalid candidate run listing.")
    candidates = [
        run
        for page in pages
        for run in page["workflow_runs"]
        if run.get("head_sha") == sha
        and run.get("head_branch") == "main"
        and run.get("status") == "completed"
        and run.get("conclusion") == "success"
    ]
    return max((run["id"] for run in candidates), default=None)


def download(repo, records, destination):
    destination.mkdir(parents=True, exist_ok=True)
    for name, info in records.items():
        target = destination / ("release-windows" if "windows" in name else "release-macos")
        target.mkdir()
        with tempfile.TemporaryFile() as stream:
            subprocess.run(
                [
                    "gh",
                    "api",
                    "--allow-escape-sequences",
                    f"repos/{repo}/actions/artifacts/{info['id']}/zip",
                ],
                stdout=stream,
                check=True,
            )
            stream.seek(0)
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if "sha256:" + digest != info["digest"]:
                raise ValueError(f"Candidate artifact {name} failed digest verification.")
            stream.seek(0)
            with zipfile.ZipFile(stream) as archive:
                # Only root-level regular release assets are expected.
                for item in archive.infolist():
                    if (
                        item.is_dir()
                        or Path(item.filename).name != item.filename
                        or "\\" in item.filename
                        or item.filename in (".", "..")
                        or (item.external_attr >> 16) & 0o170000 not in (0, 0o100000)
                    ):
                        raise ValueError("Unexpected path or file type in release artifact.")
                    output = target / item.filename
                    with archive.open(item) as source, output.open("xb") as out:
                        while block := source.read(1024 * 1024):
                            out.write(block)


def marker(sha, version, previous_tag, platform):
    return {"commit": sha, "version": version, "previous_tag": previous_tag, "platform": platform}


def verify_markers(directory, sha, version, previous_tag):
    for platform in ("windows", "macos"):
        path = directory / ("release-" + platform) / "tested-candidate.json"
        if json.loads(path.read_text(encoding="utf-8")) != marker(
            sha, version, previous_tag, platform
        ):
            raise ValueError(f"{platform} artifact was tested against different release inputs.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", type=int)
    parser.add_argument("--current-run", action="store_true")
    parser.add_argument("--expected", type=Path)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--repo")
    parser.add_argument("--version", required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--write-marker", type=Path)
    parser.add_argument("--previous-tag")
    parser.add_argument("--platform", choices=("windows", "macos"))
    args = parser.parse_args()
    version = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "src/trial_cruncher/version.py")
    )["__version__"]
    if args.version != version or not re.fullmatch(r"[0-9a-f]{40}", args.sha):
        raise ValueError("Candidate version or commit is invalid.")
    if args.write_marker:
        if args.previous_tag is None or args.platform is None:
            parser.error("Marker requires --previous-tag and --platform.")
        with args.write_marker.open("x", encoding="utf-8") as stream:
            json.dump(marker(args.sha, version, args.previous_tag, args.platform), stream)
            stream.write("\n")
        return
    if args.run_id is not None and args.run_id < 1:
        parser.error("Run ID must be a positive integer.")
    if not args.repo:
        parser.error("Candidate lookup requires --repo.")
    if args.current_run and not args.run_id:
        parser.error("--current-run requires --run-id.")
    run_id = args.run_id or discover(args.repo, args.sha)
    if run_id is None:
        print(json.dumps({"found": False}))
        return
    prefix = f"repos/{args.repo}/actions/runs/{run_id}"
    run = api(prefix)
    jobs = api(prefix + "/jobs?filter=latest&per_page=100")["jobs"]
    artifacts = api(prefix + "/artifacts?per_page=100")["artifacts"]
    result = validate(
        run,
        jobs,
        artifacts,
        args.repo,
        args.sha,
        current_run=args.current_run,
        release_tag=f"v{version}",
    )
    receipt = {"found": True, "run_id": run_id, "artifacts": result}
    if args.expected and json.loads(args.expected.read_text(encoding="utf-8")) != receipt:
        raise ValueError("Candidate artifact identifiers or digests changed since selection.")
    if args.output_dir:
        if args.previous_tag is None:
            parser.error("Download requires --previous-tag.")
        download(args.repo, result, args.output_dir)
        verify_markers(args.output_dir, args.sha, version, args.previous_tag)
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
