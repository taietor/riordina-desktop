"""
Riordina-Installa.exe: il file da mandare agli amici (si costruisce con strumenti/build.py).

Al primo doppio clic si copia in %LOCALAPPDATA%\\Programs\\Riordina Desktop, mette i collegamenti
(Desktop e menu Start), si registra tra le "App installate" di Windows e apre il programma.
Dopo, i collegamenti aprono direttamente l'app.

    Riordina-Installa.exe                 installa (o apre, se gia' installato)
    "Riordina Desktop.exe" --disinstalla  toglie app, collegamenti e voce in "App installate"
                                          (impostazioni e registro dei riordini restano in %LOCALAPPDATA%\\RiordinaDesktop)

Niente amministratore: tutto nella cartella dell'utente. Solo libreria standard + tkinter.
Per le prove: RIORDINA_TEST_DIR=<cartella> installa li', senza collegamenti, registro di Windows e finestre.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import riordina_core as core

NAME = "Riordina Desktop"
EXE_NAME = f"{NAME}.exe"
NO_WINDOW = 0x08000000
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\RiordinaDesktop"
TEST_DIR = os.environ.get("RIORDINA_TEST_DIR")
INSTALL_DIR = Path(TEST_DIR) if TEST_DIR else \
    Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Programs" / NAME


# ---------------------------------------------------------------- utilita'
def _powershell(script: str) -> str:
    res = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                         capture_output=True, text=True, creationflags=NO_WINDOW)
    return res.stdout.strip()


def shortcut_paths() -> list[Path]:
    desktop = _powershell("[Environment]::GetFolderPath('Desktop')")
    programs = _powershell("[Environment]::GetFolderPath('Programs')")
    return [Path(p) / f"{NAME}.lnk" for p in (desktop, programs) if p]


def make_shortcuts(target: Path) -> None:
    q = lambda s: str(s).replace("'", "''")
    for path in shortcut_paths():
        _powershell(
            f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{q(path)}');"
            f"$s.TargetPath='{q(target)}';$s.WorkingDirectory='{q(target.parent)}';"
            f"$s.IconLocation='{q(target)},0';"
            f"$s.Description='Riordina il Desktop in cartelle, con anteprima e consigli';$s.Save()"
        )


def register_uninstall(target: Path) -> None:
    import winreg
    size_kb = max(1, target.stat().st_size // 1024)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as k:
        for name, value in {
            "DisplayName": NAME,
            "DisplayVersion": core.__version__,
            "DisplayIcon": f'"{target}",0',
            "Publisher": "taietor",
            "InstallLocation": str(target.parent),
            "UninstallString": f'"{target}" --disinstalla',
            "URLInfoAbout": "https://github.com/taietor/riordina-desktop",
        }.items():
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
        winreg.SetValueEx(k, "EstimatedSize", 0, winreg.REG_DWORD, size_kb)
        winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)


def unregister_uninstall() -> None:
    import winreg
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except OSError:
        pass


def _ask(title: str, text: str) -> bool:
    if TEST_DIR:
        return True
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk()
    root.withdraw()
    try:
        return messagebox.askyesno(title, text, parent=root)
    finally:
        root.destroy()


def _info(title: str, text: str, error: bool = False) -> None:
    if TEST_DIR:
        print(text)
        return
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk()
    root.withdraw()
    (messagebox.showerror if error else messagebox.showinfo)(title, text, parent=root)
    root.destroy()


# ---------------------------------------------------------------- azioni
def install() -> Path:
    src = Path(sys.executable).resolve()
    dst = INSTALL_DIR / EXE_NAME
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    if not TEST_DIR:
        make_shortcuts(dst)
        register_uninstall(dst)
    return dst


def uninstall() -> None:
    if not _ask(f"Disinstalla {NAME}",
                f"Vuoi togliere {NAME} dal PC?\n\nI file che hai riordinato restano dove sono."):
        return
    if not TEST_DIR:
        for path in shortcut_paths():
            try:
                path.unlink()
            except OSError:
                pass
        unregister_uninstall()
    # l'exe in uso non si puo' cancellare da se': lo fa cmd appena questo processo si chiude
    subprocess.Popen(f'cmd /c timeout /t 2 /nobreak >nul & rmdir /s /q "{INSTALL_DIR}"',
                     creationflags=NO_WINDOW, close_fds=True)
    _info(NAME, f"{NAME} è stato disinstallato.")


def running_installed() -> bool:
    try:
        return Path(sys.executable).resolve().parent == INSTALL_DIR.resolve()
    except OSError:
        return False


def main() -> None:
    args = sys.argv[1:]
    if not core.FROZEN:  # da sorgente: apre solo l'app
        from riordina_gui import main as gui
        return gui()
    if "--disinstalla" in args:
        return uninstall()
    if running_installed() or "--solo-app" in args:
        from riordina_gui import main as gui
        return gui()

    update = (INSTALL_DIR / EXE_NAME).exists()
    question = (f"Aggiornare {NAME} alla versione {core.__version__}?" if update else
                f"Installare {NAME} {core.__version__}?\n\n"
                f"• Cartella: {INSTALL_DIR}\n• Collegamenti sul Desktop e nel menu Start\n"
                "• Si toglie da Impostazioni → App installate\n\n"
                "Non servono permessi di amministratore e non viene spostato nessun file finché "
                "non premi «Riordina ora» nel programma.")
    if not _ask(f"Installa {NAME}", question):
        return
    try:
        dst = install()
    except OSError as e:
        if update:  # probabilmente il programma e' aperto
            return _info(NAME, f"Non riesco ad aggiornarlo: chiudi {NAME} e riprova.\n\n({e})", error=True)
        return _info(NAME, f"Installazione non riuscita:\n{e}", error=True)
    _info(NAME, f"{NAME} è installato!\n\nLo trovi sul Desktop e nel menu Start. Ora si apre.")
    if not TEST_DIR:
        env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")  # la copia installata e' un processo nuovo
        subprocess.Popen([str(dst)], cwd=str(dst.parent), close_fds=True, env=env)


if __name__ == "__main__":
    main()
