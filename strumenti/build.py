"""
Costruisce dist/Riordina-Installa.exe (un solo file, senza bisogno di Python) con PyInstaller.

    python -m venv .venv
    .venv\\Scripts\\pip install pyinstaller
    .venv\\Scripts\\python strumenti\\build.py

L'icona viene ridisegnata (strumenti/collegamento.py) e messa sia sull'exe sia dentro, per la finestra.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "strumenti"))

import riordina_core as core  # noqa: E402
from collegamento import make_icon  # noqa: E402

NAME = "Riordina-Installa"


def version_file(path: Path) -> Path:
    """Dati mostrati in Proprieta' → Dettagli dell'exe."""
    major, minor, patch = (int(x) for x in core.__version__.split("."))
    path.write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({major}, {minor}, {patch}, 0), prodvers=({major}, {minor}, {patch}, 0)),
  kids=[StringFileInfo([StringTable('041004B0', [
      StringStruct('CompanyName', 'taietor'),
      StringStruct('FileDescription', 'Riordina Desktop'),
      StringStruct('FileVersion', '{core.__version__}'),
      StringStruct('ProductName', 'Riordina Desktop'),
      StringStruct('ProductVersion', '{core.__version__}'),
      StringStruct('OriginalFilename', '{NAME}.exe')])]),
    VarFileInfo([VarStruct('Translation', [0x0410, 1200])])])
""", encoding="utf-8")
    return path


def main() -> None:
    import PyInstaller.__main__

    icon = make_icon()
    work = ROOT / "build"
    work.mkdir(exist_ok=True)
    PyInstaller.__main__.run([
        str(ROOT / "installa.py"),
        "--name", NAME,
        "--onefile", "--windowed", "--noconfirm", "--clean",
        "--icon", str(icon),
        "--add-data", f"{icon}{';'}.",
        "--version-file", str(version_file(work / "version.txt")),
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(work),
        "--specpath", str(work),
        "--exclude-module", "PIL", "--exclude-module", "pypdf",  # opzionali: l'exe resta piccolo
    ])
    exe = ROOT / "dist" / f"{NAME}.exe"
    print(f"\nPronto: {exe}  ({exe.stat().st_size / 1024 / 1024:.1f} MB)")
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
