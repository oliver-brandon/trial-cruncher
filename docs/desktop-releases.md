# Desktop installations and stable updates

Trial Cruncher uses the stable Photon Cruncher distribution pattern. Its package
identity is `com.trialcruncher.app`, and its update feed is the Trial Cruncher
repository. Photon Cruncher and Trial Cruncher can be installed side by side.

| Platform | First installation | Later updates |
| --- | --- | --- |
| Apple Silicon Mac | Run the Developer ID signed, notarized `Trial-Cruncher-v<version>-macOS.pkg`. Open Trial Cruncher in Applications. | The installed app reads `stable-osx-arm64`. |
| Windows x64 | Run `Trial-Cruncher-v<version>-Windows.exe`. Open Trial Cruncher from the Start menu. Windows may show SmartScreen for the unsigned installer. | The installed app reads `stable-win-x64`. |
| Ubuntu | Install the source checkout in a Python 3.12+ virtual environment. | Pull the branch and refresh the editable installation. See [Ubuntu source launches](ubuntu-source.md). |

The one-time installer is also how an existing Mac or Windows source user moves to
managed updates. Keep your recordings and projects in their existing locations.
A portable archive is a separate release asset. For the managed path, start the
installed copy. Intel Mac and Windows ARM64 native installers are outside these two feeds.

The desktop checks shortly after startup and every six hours. **Help → Check for
Updates…** runs a manual check. When a newer stable version is available, the
update indicator opens its release notes and offers download and restart. An active
analysis, import, export, or unsaved project must be finished or saved before the
handoff. Automatic checks can fail quietly offline. Source launches use the Git
workflow, including when the repository is private and the owner has access.

## Owner setup

1. Choose the release host. As configured, installers read stable GitHub Releases
   from **oliver-brandon/trial-cruncher** anonymously. This exact setup needs a
   public repository for distribution. A private repository works for building and
   testing candidates with authenticated GitHub Actions. To keep the source private
   while offering login-free updates, use a separate public release repository or
   a public package host and adapt both the publishing destination and the updater
   source. A private feed requires an authenticated distribution design. Keep
   publishing credentials out of client binaries.
2. Enable GitHub Actions with available build minutes or spending capacity for the
   Windows and macOS jobs. The build jobs read repository contents. Only the final
   publish job requests `contents: write`.
3. Configure the following **repository Actions secrets** under Settings →
   Secrets and variables → Actions. Photon Cruncher's repository-scoped secrets
   belong to that repository. Use the original certificates and credentials from
   their secure store, or grant this repository access to equivalent organization
   secrets. GitHub does not return existing secret values.

| Secret | Value needed by the macOS build |
| --- | --- |
| `MACOS_DEVELOPER_ID_APPLICATION_P12_BASE64` | Base64 export of Developer ID Application certificate and its private key |
| `MACOS_DEVELOPER_ID_INSTALLER_P12_BASE64` | Base64 export of Developer ID Installer certificate and its private key |
| `MACOS_CERTIFICATE_PASSWORD` | Password for the two PKCS#12 exports |
| `MACOS_KEYCHAIN_PASSWORD` | Password for the temporary CI keychain |
| `MACOS_DEVELOPER_ID_APPLICATION` | Exact Developer ID Application signing identity |
| `MACOS_DEVELOPER_ID_INSTALLER` | Exact Developer ID Installer signing identity |
| `APPLE_ID`, `APPLE_APP_PASSWORD`, `APPLE_TEAM_ID` | Notarization Apple ID, app-specific password, and team identifier |

## Build and release

1. Set the numeric version in `src/trial_cruncher/version.py` and update the heading
   and notes in `packaging/velopack/release-notes.md`. The Python wheel, desktop,
   installer metadata and stable tag use the same version. Keep the package ID and
   platform channels stable across releases.
2. After the release changes are on `main`, run **Publish stable desktop updates**
   in GitHub Actions on `main` with **build_only** checked (the default). This
   builds both native packages, installs the candidate on the first release, and
   exercises the installed desktop and packaged CLI with synthetic recordings.
   On subsequent releases the workflow obtains the previous stable package,
   applies the candidate via Velopack and checks the relaunched app. Build-only
   outputs are workflow artifacts for testing.
3. To publish, push the matching `v<version>` tag at a commit on `main`, or
   explicitly dispatch the workflow on `main` with **build_only** unchecked.
   Both platform jobs must succeed. The publisher verifies the package identities,
   sizes and hashes, stages the installers, portable archives, full packages and
   channel JSON in a draft, then verifies uploaded assets before publication.
   The first release establishes the full-package baseline. A subsequent release
   also supplies a delta from its predecessor. Retrying a draft verifies any
   previously uploaded files. Published tags cannot be reused for replacement binaries.
4. For a local platform build, install Python 3.12+ and run
   `scripts/build_macos_app.sh` or `scripts/build_windows_app.ps1` on the
   corresponding OS. For installer packaging use the matching
   `scripts/package_*_update` script and the pinned `vpk` CLI. The macOS package
   step requires both signing identities and the notary profile; the workflow
   sets them up in a temporary keychain. Project data, recordings, exports and
   credentials stay outside the application payload.

The platform smoke jobs verify local install/apply paths. After a release,
verify discovery from an installed previous version against the published GitHub
feed using **Help → Check for Updates…**.

Reference implementations and feed behavior are documented in [Photon Cruncher's
stable release](https://github.com/oliver-brandon/photon-cruncher/releases/tag/v2.1.0)
and [Velopack update sources](https://docs.velopack.io/integrating/update-sources).
