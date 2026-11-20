"""Resolve a previous stable tag without hiding authentication or network errors."""

import json
import os
import re
import subprocess

_VERSION = re.compile(r"v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)\Z")


def main():
    candidate = os.environ["CANDIDATE_VERSION"]
    match = _VERSION.fullmatch("v" + candidate)
    if not match:
        raise ValueError("Candidate version must be a three-part stable version.")
    current = tuple(map(int, match.groups()))
    response = subprocess.check_output(
        ["gh", "api", "--paginate", "--slurp", f"repos/{os.environ['GITHUB_REPOSITORY']}/releases"],
        text=True,
    )
    releases = json.loads(response)
    versions = []
    for release in (item for page in releases for item in page):
        if release["draft"] or release["prerelease"]:
            continue
        found = _VERSION.fullmatch(release["tag_name"])
        if found:
            versions.append((tuple(map(int, found.groups())), release["tag_name"]))
    if versions and max(versions)[0] >= current:
        raise ValueError("Candidate version must be newer than the latest stable release.")
    print(max(versions)[1] if versions else "")


if __name__ == "__main__":
    main()
