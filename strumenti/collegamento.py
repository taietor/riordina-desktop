"""
I collegamenti «Riordina Desktop» (Desktop e menu Start): aprono l'app senza finestra del terminale
(pythonw.exe) con la sua icona, disegnata qui sotto senza librerie esterne.

    python strumenti/collegamento.py            crea icona + collegamenti
    python strumenti/collegamento.py --rimuovi  toglie i collegamenti

Rifallo se sposti la cartella del progetto.
"""

from __future__ import annotations

import math
import os
import struct
import subprocess
import sys
import zlib
from pathlib import Path

NAME = "Riordina Desktop"
ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "riordina_desktop.pyw"
ICON = ROOT / "riordina.ico"
SIZES = (256, 64, 48, 32, 24, 16)


# ---------------------------------------------------------------- icona
def _rounded_rect(x, y, x0, y0, x1, y1, r):
    """Distanza con segno da un rettangolo arrotondato (negativa = dentro)."""
    cx, cy = min(max(x, x0 + r), x1 - r), min(max(y, y0 + r), y1 - r)
    return math.hypot(x - cx, y - cy) - r


def _pixel(x: float, y: float):
    """Colore RGBA (0..1) nel punto (x, y) con coordinate normalizzate 0..1."""
    # sfondo: quadrato arrotondato con sfumatura viola
    if _rounded_rect(x, y, 0.04, 0.04, 0.96, 0.96, 0.22) > 0:
        return None
    t = (x + y) / 2
    col = (0.43 - 0.17 * t, 0.37 - 0.15 * t, 0.99 - 0.20 * t)

    # stellina gialla (in alto a destra)
    sx, sy, sr = abs(x - 0.75), abs(y - 0.25), 0.13
    if sx ** 0.5 + sy ** 0.5 < sr ** 0.5:
        return (0.99, 0.75, 0.15, 1)
    if math.hypot(x - 0.86, y - 0.40) < 0.025 or math.hypot(x - 0.62, y - 0.13) < 0.02:
        return (1, 0.86, 0.45, 1)

    # cartella bianca: linguetta + corpo
    tab = _rounded_rect(x, y, 0.16, 0.30, 0.46, 0.42, 0.05) < 0
    body = _rounded_rect(x, y, 0.16, 0.37, 0.84, 0.80, 0.07) < 0
    if tab or body:
        # righe ordinate dentro la cartella
        for ly, lx1, c in ((0.51, 0.70, (0.36, 0.33, 0.91)), (0.60, 0.62, (0.55, 0.52, 0.97)),
                           (0.69, 0.66, (0.36, 0.33, 0.91))):
            if _rounded_rect(x, y, 0.27, ly - 0.025, lx1, ly + 0.025, 0.025) < 0:
                return (*c, 1)
        shade = 0.96 if y < 0.42 and not body else 1.0
        return (shade, shade, 1.0, 1)
    return (*col, 1)


def _render(size: int, ss: int = 4) -> bytes:
    """Immagine RGBA size x size con antialiasing (ss x ss campioni per pixel)."""
    rows = []
    for py in range(size):
        row = bytearray([0])  # filtro PNG "nessuno"
        for px in range(size):
            r = g = b = a = 0.0
            for sy in range(ss):
                for sx in range(ss):
                    c = _pixel((px + (sx + 0.5) / ss) / size, (py + (sy + 0.5) / ss) / size)
                    if c:
                        r, g, b, a = r + c[0] * c[3], g + c[1] * c[3], b + c[2] * c[3], a + c[3]
            n = ss * ss
            if a:
                row += bytes((round(255 * r / a), round(255 * g / a), round(255 * b / a), round(255 * a / n)))
            else:
                row += b"\0\0\0\0"
        rows.append(bytes(row))
    return b"".join(rows)


def _png(size: int) -> bytes:
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(_render(size), 9)) + chunk(b"IEND", b"")


def make_icon(dst: Path = ICON) -> Path:
    """File .ico con un'immagine PNG per ogni misura (come l'icona di Deneris)."""
    images = [(s, _png(s)) for s in SIZES]
    head = struct.pack("<HHH", 0, 1, len(images))
    offset = len(head) + 16 * len(images)
    entries, data = b"", b""
    for size, png in images:
        side = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(png), offset + len(data))
        data += png
    dst.write_bytes(head + entries + data)
    return dst


# ---------------------------------------------------------------- collegamenti
def _powershell(script: str, capture: bool = False) -> str:
    res = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                         capture_output=True, text=True, creationflags=0x08000000)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip())
    return res.stdout.strip()


def shortcut_paths() -> list[Path]:
    desktop = _powershell("[Environment]::GetFolderPath('Desktop')")
    programs = _powershell("[Environment]::GetFolderPath('Programs')")
    return [Path(desktop) / f"{NAME}.lnk", Path(programs) / f"{NAME}.lnk"]


def pythonw() -> Path:
    exe = Path(sys.executable)
    w = exe.with_name("pythonw.exe")
    return w if w.exists() else exe


def create_shortcuts() -> list[Path]:
    icon = make_icon()
    q = lambda s: str(s).replace("'", "''")
    done = []
    for path in shortcut_paths():
        _powershell(
            f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{q(path)}');"
            f"$s.TargetPath='{q(pythonw())}';$s.Arguments='\"{q(APP)}\"';"
            f"$s.WorkingDirectory='{q(ROOT)}';$s.IconLocation='{q(icon)},0';"
            f"$s.Description='Riordina il Desktop in cartelle, con anteprima e consigli';$s.Save()"
        )
        done.append(path)
    return done


def remove_shortcuts() -> list[Path]:
    removed = []
    for path in shortcut_paths():
        if path.exists():
            path.unlink()
            removed.append(path)
    return removed


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if "--rimuovi" in sys.argv:
        for p in remove_shortcuts():
            print(f"Collegamento rimosso: {p}")
        return
    for p in create_shortcuts():
        print(f"Collegamento creato: {p}")
    print(f"Icona: {ICON}")


if __name__ == "__main__":
    main()
