# Build on Windows with build_windows.ps1 (runs: python -m PyInstaller --noconfirm PerfectMatchLFP26.spec)
from pathlib import Path
import pulp

project = Path(SPECPATH)
cbc = Path(pulp.__file__).parent / "solverdir" / "cbc" / "win" / "i64"
if not (cbc / "cbc.exe").is_file():
    raise RuntimeError("Build this Windows package with 64-bit Python and PuLP 3.3.0.")

a = Analysis(
    [str(project / "app.py")],
    pathex=[str(project)],
    binaries=[(str(cbc / "cbc.exe"), "pulp/solverdir/cbc/win/i64")],
    datas=[(str(project / "static" / name), "static") for name in ("index.html", "app.js", "app.css")]
          + [(str(project / "manual.pdf"), "."),
             (str(project / "examples" / "survey_example.csv"), "examples"),
             (str(cbc / "coin-license.txt"), "pulp/solverdir/cbc/win/i64")],
    hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=["tkinter", "IPython", "matplotlib", "numpy", "pandas"], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="PerfectMatchLFP26",
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="PerfectMatchLFP26")
