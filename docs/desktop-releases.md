# Desktop installations and stable updates

Trial Cruncher’s package identity is `com.trialcruncher.app`. Installed copies
read stable updates from the Trial Cruncher repository.

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
   Secrets and variables → Actions. Use the original certificates and credentials from
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
   on `main` with **build_only** checked. The build waits for the full scientific,
   file-safety and GUI test suites on all six OS/Python combinations. The native
   jobs sign/package once and exercise the actual candidate installers, installed
   GUI and packaged CLI. Subsequent releases also test upgrading from the previous
   stable release. The two downloadable artifacts stay available for 30 days.
3. Try the installers from that build. To publish **those exact bytes**, dispatch
   the same workflow on `main`, uncheck **build_only**, and enter that build's run
   ID under **candidate_run_id**. Alternatively, push the matching `v<version>`
   tag at the tested commit. Without a run ID, publication looks for the latest
   successful build-only run at that exact commit. A verified match skips CI,
   signing, packaging and notarization. A new commit without a matching build
   runs the full checks and publishes the resulting tested packages.

   Promotion checks the repository, branch, commit, CI and installer job results,
   immutable artifact IDs, and SHA-256 of the downloaded archives. The archives
   also identify the version and previous stable release used during testing.
   An expired, incomplete or mismatched candidate stops publication. Run a new
   build-only candidate if needed. The publisher verifies draft asset hashes before
   making the release public. Retry an interrupted publish with the same artifacts.

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

For feed behavior, see [Velopack update sources](https://docs.velopack.io/integrating/update-sources).
