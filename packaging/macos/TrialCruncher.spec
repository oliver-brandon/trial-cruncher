# -*- mode: python ; coding: utf-8 -*-
"""macOS app bundle, including Qt WebEngine and Velopack."""
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, copy_metadata
from trial_cruncher.version import APP_NAME, BUNDLE_APP_NAME, BUNDLE_IDENTIFIER
from trial_cruncher import __version__

root = Path(SPECPATH).parents[1]
package = root / "src" / "trial_cruncher"
icon_path = package / "gui" / "web" / "icons" / "trial-cruncher.icns"
data, binaries, hidden = collect_all("velopack")
a = Analysis(
    [str(root / "packaging" / "desktop_entry.py")],
    pathex=[str(root / "src")],
    binaries=binaries,
    hiddenimports=["PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineCore",
                   "PySide6.QtWebChannel", "trial_cruncher.gui.web_shell", "velopack"] + hidden,
    datas=[(str(package / "gui" / "web"), "trial_cruncher/gui/web")] + data + sum((copy_metadata(name) for name in ("trial-cruncher", "PySide6", "numpy", "pandas", "openpyxl")), []),
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=BUNDLE_APP_NAME,
          console=False, upx=False, argv_emulation=False)

cli_a = Analysis(
    [str(root / "packaging" / "cli_entry.py")],
    pathex=[str(root / "src")],
    datas=copy_metadata("trial-cruncher"),
    excludes=["PySide6", "trial_cruncher.gui", "velopack"],
)
cli_pyz = PYZ(cli_a.pure)
cli_exe = EXE(cli_pyz, cli_a.scripts, cli_a.binaries, cli_a.datas, [],
              name="trial-cruncher-cli", console=True, upx=False,
              codesign_identity=os.environ.get("MACOS_DEVELOPER_ID_APPLICATION"))

coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=BUNDLE_APP_NAME)
app = BUNDLE(
    coll, name=f"{BUNDLE_APP_NAME}.app", bundle_identifier=BUNDLE_IDENTIFIER,
    icon=str(icon_path),
    info_plist={"CFBundleDisplayName": APP_NAME,
                "CFBundleShortVersionString": __version__, "CFBundleVersion": __version__,
                "LSApplicationCategoryType": "public.app-category.science",
                "NSHighResolutionCapable": True},
)
