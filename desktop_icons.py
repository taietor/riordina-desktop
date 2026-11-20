"""
desktop_icons.py - legge e rimette la posizione delle icone sul Desktop di Windows.

Il Desktop e' una ListView (SysListView32) dentro explorer.exe: per leggerne nomi e posizioni si usa
un piccolo buffer nella memoria di explorer (VirtualAllocEx), come fanno i programmi tipo "DesktopOK".
Solo libreria standard (ctypes). Se qualcosa non va, le funzioni ritornano None/0 senza errori.
"""
from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes as wt

LVM_FIRST = 0x1000
LVM_GETITEMCOUNT = LVM_FIRST + 4
LVM_GETITEMPOSITION = LVM_FIRST + 16
LVM_SETITEMPOSITION32 = LVM_FIRST + 49
LVM_GETITEMTEXTW = LVM_FIRST + 115
LVS_AUTOARRANGE = 0x0100
GWL_STYLE = -16
PROCESS_ACCESS = 0x0008 | 0x0010 | 0x0020 | 0x0400  # VM_OPERATION | VM_READ | VM_WRITE | QUERY_INFORMATION
MEM_COMMIT_RESERVE, MEM_RELEASE, PAGE_READWRITE = 0x3000, 0x8000, 0x04
BUF_SIZE = 4096
TEXT_OFFSET, POINT_OFFSET, TEXT_CHARS = 256, 3072, 260

if os.name == "nt":
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]
    user32.FindWindowW.restype = wt.HWND
    user32.FindWindowExW.argtypes = [wt.HWND, wt.HWND, wt.LPCWSTR, wt.LPCWSTR]
    user32.FindWindowExW.restype = wt.HWND
    user32.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
    user32.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.InvalidateRect.argtypes = [wt.HWND, ctypes.c_void_p, wt.BOOL]
    kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    kernel32.OpenProcess.restype = wt.HANDLE
    kernel32.VirtualAllocEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wt.DWORD, wt.DWORD]
    kernel32.VirtualAllocEx.restype = ctypes.c_void_p
    kernel32.VirtualFreeEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wt.DWORD]
    kernel32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                           ctypes.POINTER(ctypes.c_size_t)]
    kernel32.WriteProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                            ctypes.POINTER(ctypes.c_size_t)]
    kernel32.CloseHandle.argtypes = [wt.HANDLE]


class LVITEMW(ctypes.Structure):
    _fields_ = [("mask", wt.UINT), ("iItem", ctypes.c_int), ("iSubItem", ctypes.c_int),
                ("state", wt.UINT), ("stateMask", wt.UINT), ("pszText", ctypes.c_void_p),
                ("cchTextMax", ctypes.c_int), ("iImage", ctypes.c_int), ("lParam", wt.LPARAM),
                ("iIndent", ctypes.c_int), ("iGroupId", ctypes.c_int), ("cColumns", wt.UINT),
                ("puColumns", ctypes.c_void_p), ("piColFmt", ctypes.c_void_p), ("iGroup", ctypes.c_int)]


def _find_listview():
    """La ListView del Desktop: sta sotto Progman o, con lo sfondo a presentazione, sotto un WorkerW."""
    progman = user32.FindWindowW("Progman", None)
    parents = [progman]
    h = None
    while True:  # WorkerW figli di Progman (Windows 11 24H2+) e WorkerW di primo livello
        h = user32.FindWindowExW(progman, h, "WorkerW", None)
        if not h:
            break
        parents.append(h)
    h = None
    while True:
        h = user32.FindWindowExW(None, h, "WorkerW", None)
        if not h:
            break
        parents.append(h)
    for parent in parents:
        if not parent:
            continue
        defview = user32.FindWindowExW(parent, None, "SHELLDLL_DefView", None)
        if defview:
            lv = user32.FindWindowExW(defview, None, "SysListView32", None)
            if lv:
                return lv
    return None


class _Explorer:
    """Buffer nella memoria di explorer.exe, chiuso automaticamente."""

    def __init__(self, lv):
        self.lv = lv
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(lv, ctypes.byref(pid))
        self.proc = kernel32.OpenProcess(PROCESS_ACCESS, False, pid.value)
        if not self.proc:
            raise OSError("explorer non accessibile")
        self.mem = kernel32.VirtualAllocEx(self.proc, None, BUF_SIZE, MEM_COMMIT_RESERVE, PAGE_READWRITE)
        if not self.mem:
            kernel32.CloseHandle(self.proc)
            raise OSError("memoria non allocata")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        kernel32.VirtualFreeEx(self.proc, self.mem, 0, MEM_RELEASE)
        kernel32.CloseHandle(self.proc)

    def write(self, offset, obj):
        n = ctypes.c_size_t()
        return kernel32.WriteProcessMemory(self.proc, self.mem + offset, ctypes.byref(obj), ctypes.sizeof(obj), ctypes.byref(n))

    def read(self, offset, obj):
        n = ctypes.c_size_t()
        return kernel32.ReadProcessMemory(self.proc, self.mem + offset, ctypes.byref(obj), ctypes.sizeof(obj), ctypes.byref(n))

    def count(self) -> int:
        return int(user32.SendMessageW(self.lv, LVM_GETITEMCOUNT, 0, 0))

    def name(self, i: int) -> str:
        item = LVITEMW(iSubItem=0, pszText=self.mem + TEXT_OFFSET, cchTextMax=TEXT_CHARS)
        self.write(0, item)
        length = user32.SendMessageW(self.lv, LVM_GETITEMTEXTW, i, self.mem)
        buf = ctypes.create_unicode_buffer(TEXT_CHARS)
        self.read(TEXT_OFFSET, buf)
        return buf.value[:length] if length >= 0 else buf.value

    def position(self, i: int) -> tuple[int, int] | None:
        pt = wt.POINT()
        if not user32.SendMessageW(self.lv, LVM_GETITEMPOSITION, i, self.mem + POINT_OFFSET):
            return None
        self.read(POINT_OFFSET, pt)
        return pt.x, pt.y

    def set_position(self, i: int, x: int, y: int) -> bool:
        pt = wt.POINT(x, y)
        self.write(POINT_OFFSET, pt)
        return bool(user32.SendMessageW(self.lv, LVM_SETITEMPOSITION32, i, self.mem + POINT_OFFSET))


def auto_arrange_on() -> bool:
    """Con "Disponi icone automaticamente" attivo Windows ignora le posizioni salvate."""
    if os.name != "nt":
        return False
    lv = _find_listview()
    return bool(lv) and bool(user32.GetWindowLongW(lv, GWL_STYLE) & LVS_AUTOARRANGE)


def get_positions() -> dict[str, list[int]] | None:
    """{nome mostrato sul Desktop: [x, y]} oppure None se non si riesce a leggere."""
    if os.name != "nt":
        return None
    try:
        lv = _find_listview()
        if not lv:
            return None
        out = {}
        with _Explorer(lv) as ex:
            for i in range(ex.count()):
                name, pos = ex.name(i), ex.position(i)
                if name and pos and name not in out:
                    out[name] = list(pos)
        return out
    except Exception:
        return None


def set_positions(positions: dict[str, list[int]], wait_for: float = 4.0) -> int:
    """Rimette le icone nelle posizioni salvate. Aspetta un attimo che Explorer mostri i file
    appena rimessi sul Desktop. Ritorna quante icone sono state posizionate."""
    if os.name != "nt" or not positions:
        return 0
    try:
        lv = _find_listview()
        if not lv:
            return 0
        deadline = time.time() + wait_for
        with _Explorer(lv) as ex:
            while True:
                names = {ex.name(i): i for i in range(ex.count())}
                missing = [n for n in positions if n not in names]
                if not missing or time.time() > deadline:
                    break
                time.sleep(0.4)
            done = 0
            for name, (x, y) in positions.items():
                i = names.get(name)
                if i is not None and ex.set_position(i, x, y):
                    done += 1
        user32.InvalidateRect(lv, None, True)
        return done
    except Exception:
        return 0


if __name__ == "__main__":  # prova: stampa le posizioni (sola lettura)
    pos = get_positions()
    print("disposizione automatica:", auto_arrange_on())
    print(f"{len(pos or {})} icone lette")
    for n, p in list((pos or {}).items())[:10]:
        print(f"  {p}  {n}")
