"""Verify the temporary signing keychain without printing credential values."""

import os
import re
import subprocess


def verify(keychain: str) -> None:
    listed = subprocess.check_output(["security", "find-identity", "-v", keychain], text=True)
    identities = re.findall(r'^\s*\d+\) ([0-9a-fA-F]{40}) "([^"]+)"', listed, re.M)
    team = os.environ["APPLE_TEAM_ID"].strip()
    for role in ("Application", "Installer"):
        variable = "MACOS_DEVELOPER_ID_" + role.upper()
        configured = os.environ[variable].strip()
        valid = [
            (digest, name)
            for digest, name in identities
            if name.startswith(f"Developer ID {role}: ") and name.endswith(f"({team})")
        ]
        if not valid:
            raise SystemExit(
                f"No valid Developer ID {role} identity for APPLE_TEAM_ID in the build keychain. "
                f"Check {variable}_P12_BASE64 contains the current certificate AND its private key."
            )
        matches = [
            (digest, name)
            for digest, name in valid
            if configured == name or configured.upper() == digest.upper()
        ]
        if len(matches) != 1:
            raise SystemExit(
                f"The imported Developer ID {role} identity is valid. "
                f"Set {variable} to its exact certificate common name or SHA-1 fingerprint."
            )
        # codesign accepts the fingerprint; the installer signer uses the certificate name.
        identity = matches[0][0] if role == "Application" else matches[0][1]
        with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as env:
            print(f"VERIFIED_{role.upper()}_IDENTITY={identity}", file=env)
    print("Both Developer ID signing identities are valid and match the configured team.")


if __name__ == "__main__":
    verify(os.environ["MACOS_SIGNING_KEYCHAIN"])
