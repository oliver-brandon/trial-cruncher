#!/usr/bin/env bash
# Exercise a signed PKG install on an ephemeral hosted runner, then the updater
# when a previous stable release exists. The candidate package is never modified.
set -euo pipefail

if [[ "${GITHUB_ACTIONS:-}" != "true" || "${RUNNER_OS:-}" != "macOS" || -z "${RUNNER_TEMP:-}" ]]; then
  echo "Run only on an isolated GitHub-hosted macOS runner." >&2
  exit 1
fi
if [[ "$#" -ne 1 || ! -f "$1" || -z "${GITHUB_REPOSITORY:-}" ]]; then
  echo "Usage: $0 candidate-full.nupkg (with GITHUB_REPOSITORY set)" >&2
  exit 2
fi
candidate="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
target_version="$(python3 - "$candidate" <<'PY'
import sys, zipfile, xml.etree.ElementTree as ET
with zipfile.ZipFile(sys.argv[1]) as archive:
    files = [name for name in archive.namelist() if name.endswith(".nuspec") and "/" not in name]
    if len(files) != 1:
        raise SystemExit("Expected one package manifest.")
    root = ET.fromstring(archive.read(files[0]))
    metadata = next(node for node in root if node.tag.split("}")[-1] == "metadata")
    fields = {node.tag.split("}")[-1]: node.text for node in metadata}
    if (fields.get("id") != "com.trialcruncher.app"
        or fields.get("channel") != "stable-osx-arm64"
        or fields.get("rid") != "osx-arm64" or not fields.get("version")):
        raise SystemExit("Unexpected package identity, channel, runtime or version.")
    print(fields["version"])
PY
)"
work="${RUNNER_TEMP}/trial-stable-upgrade"
mkdir -p "$work/packages" "$work/Applications"
cp -p "$candidate" "$work/packages/$(basename "$candidate")"
candidate="$work/packages/$(basename "$candidate")"

# The preflight job resolves this once for both platforms. An explicitly empty
# tag means this is the first release; an absent value is a configuration error.
if [[ -z "${PREVIOUS_TAG+x}" ]]; then
  echo "Preflight must supply PREVIOUS_TAG." >&2
  exit 1
fi
previous="$PREVIOUS_TAG"
if [[ -n "$previous" ]]; then
  gh release download "$previous" --repo "$GITHUB_REPOSITORY" --pattern '*-macOS.pkg' --dir "$work"
  installer_pkg="$(find "$work" -maxdepth 1 -name '*-macOS.pkg' -print -quit)"
else
  installer_pkg="$(find "$(dirname "$1")" -maxdepth 1 -name '*-Setup.pkg' -print -quit)"
fi
if [[ -z "$installer_pkg" || ! -f "$installer_pkg" ]]; then
  echo "Expected a single stable macOS installer." >&2
  exit 1
fi
pkgutil --check-signature "$installer_pkg"
spctl --assess --verbose=2 --type install "$installer_pkg"
sudo installer -pkg "$installer_pkg" -target /
installed="/Applications/Trial Cruncher.app"
test -d "$installed"
app="$work/Applications/Trial Cruncher.app"
ditto "$installed" "$app"
binary="$app/Contents/MacOS/Trial Cruncher"
updater="$app/Contents/MacOS/UpdateMac"
test -x "$binary"
test -x "$updater"
test "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$app/Contents/Info.plist")" = "com.trialcruncher.app"
codesign --verify --deep --strict "$app"
expected_initial="${previous#v}"
initial_version="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$app/Contents/Info.plist")"
test "$initial_version" = "${expected_initial:-$target_version}"
old_pid=""
new_pid=""
cleanup() {
  [[ -z "$old_pid" ]] || kill -TERM "$old_pid" 2>/dev/null || true
  [[ -z "$new_pid" ]] || kill -TERM "$new_pid" 2>/dev/null || true
}
trap cleanup EXIT
open -n "$app"
for _ in {1..60}; do
  old_pid="$(pgrep -f "^$binary" | head -1 || true)"
  [[ -n "$old_pid" ]] && break
  sleep 1
done
if [[ -z "$old_pid" ]]; then
  echo "Installed application did not start." >&2
  exit 1
fi
if [[ -n "$previous" ]]; then
  "$updater" --verbose --rootDir "$app" --packageDir "$work/packages" \
    apply --waitPid "$old_pid" --package "$candidate" > "$work/update.log" 2>&1 &
  update_pid=$!
  kill -TERM "$old_pid"
  wait "$update_pid" || { cat "$work/update.log" >&2; exit 1; }
  for _ in {1..120}; do
    version="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$app/Contents/Info.plist" 2>/dev/null || true)"
    new_pid="$(pgrep -f "^$binary" | head -1 || true)"
    [[ "$version" = "$target_version" && -n "$new_pid" && "$new_pid" != "$old_pid" ]] && break
    sleep 1
  done
  if [[ "${version:-}" != "$target_version" || -z "$new_pid" || "$new_pid" = "$old_pid" ]]; then
    cat "$work/update.log" >&2
    echo "UpdateMac did not replace and relaunch the expected version." >&2
    exit 1
  fi
  codesign --verify --deep --strict "$app"
else
  version="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$app/Contents/Info.plist")"
  test "$version" = "$target_version"
  new_pid="$old_pid"
fi
kill -TERM "$new_pid"
for _ in {1..30}; do
  kill -0 "$new_pid" 2>/dev/null || break
  sleep 1
done
if kill -0 "$new_pid" 2>/dev/null; then
  echo "Installed app did not close." >&2
  exit 1
fi
new_pid=""

# On an upgrade run the package above installs the previous release. Exercise
# the candidate PKG itself as well, since those are the installer bytes published.
if [[ -n "$previous" ]]; then
  candidate_pkg="$(find "$(dirname "$1")" -maxdepth 1 -name '*-Setup.pkg' -print -quit)"
  test -f "$candidate_pkg"
  pkgutil --check-signature "$candidate_pkg"
  spctl --assess --verbose=2 --type install "$candidate_pkg"
  sudo installer -pkg "$candidate_pkg" -target /
  test "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$installed/Contents/Info.plist")" = "com.trialcruncher.app"
  test "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$installed/Contents/Info.plist")" = "$target_version"
  codesign --verify --deep --strict "$installed"
  # Verify the executable from the candidate installer with the same synthetic
  # import/export flow used for the upgraded copy.
  .build-venv/bin/python scripts/smoke_installed_gui.py "$installed/Contents/MacOS/Trial Cruncher"
  .build-venv/bin/python scripts/smoke_packaged_analysis.py "$installed/Contents/Resources/bin/trial-cruncher-cli"
  open -n "$installed"
  for _ in {1..60}; do
    new_pid="$(pgrep -f "^$installed/Contents/MacOS/Trial Cruncher" | head -1 || true)"
    [[ -n "$new_pid" ]] && break
    sleep 1
  done
  if [[ -z "$new_pid" ]]; then
    echo "Candidate installer app did not start." >&2
    exit 1
  fi
  kill -TERM "$new_pid"
  for _ in {1..30}; do
    kill -0 "$new_pid" 2>/dev/null || break
    sleep 1
  done
  if kill -0 "$new_pid" 2>/dev/null; then
    echo "Candidate installer app did not close." >&2
    exit 1
  fi
  new_pid=""
fi
echo "Candidate installer and updated app ready for GUI verification."
