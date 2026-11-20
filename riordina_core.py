"""
riordina_core.py - motore di "Riordina Desktop".

Analizza una cartella (di default il Desktop), propone dove mettere ogni
elemento, genera consigli e sposta i file con possibilita' di annullare.
Usa solo la libreria standard di Python (pypdf e Pillow sono opzionali).

Regole di sicurezza:
- non cancella mai nulla in modo definitivo: al massimo sposta nel Cestino
  (e solo se lo chiedi tu da un consiglio);
- ogni riordino viene registrato e si puo' annullare.
"""
from __future__ import annotations

import ctypes
import html
import json
import os
import re
import shutil
import stat
import sys
import time
import uuid
import zipfile
import zlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

try:
    from pypdf import PdfReader  # opzionale: lettura PDF migliore
except ImportError:
    PdfReader = None

APP_NAME = "Riordina Desktop"
__version__ = "1.0.0"
FROZEN = getattr(sys, "frozen", False)  # True dentro l'exe di PyInstaller
APP_DIR = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "RiordinaDesktop"
LOG_DIR = DATA_DIR / "registro"
CONFIG_FILE = DATA_DIR / "impostazioni.json"
SINGLE_FOLDER_NAME = "Desktop Ordinato"


# ============================================================ cartelle Windows
def known_folder(guid: str) -> Path | None:
    """Percorso di una cartella speciale di Windows (gestisce OneDrive, ecc.)."""
    if os.name != "nt":
        return None
    try:
        class GUID(ctypes.Structure):
            _fields_ = [("d1", ctypes.c_uint32), ("d2", ctypes.c_uint16),
                        ("d3", ctypes.c_uint16), ("d4", ctypes.c_ubyte * 8)]
        g = GUID()
        ctypes.memmove(ctypes.byref(g), uuid.UUID(guid).bytes_le, 16)
        p = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(p)) == 0:
            value = p.value
            ctypes.windll.ole32.CoTaskMemFree(p)
            return Path(value)
    except Exception:
        pass
    return None


DESKTOP = known_folder("B4BFCC3A-DB2C-424C-B029-7FE99A87C641") or Path.home() / "Desktop"
DOCUMENTS = known_folder("FDD39AD0-238F-46AF-ADB4-6C85480369C7") or Path.home() / "Documents"
PUBLIC_DESKTOP = known_folder("C4AA340D-F20F-4863-AFEF-F87EF2E6BA25")


# ============================================================ categorie
# Le categorie sono percorsi relativi con "/", es. "Programmi/Sviluppo".
TOP_ICONS = {
    "Giochi": "🎮", "Programmi": "🧩", "Documenti": "📄", "Siti e App Web": "🌐",
    "Immagini": "🖼", "Video e Audio": "🎬", "Archivi": "🧳", "Installer": "📦",
    "Script e Codice": "💻", "Cartelle": "📁", "Collegamenti a cartelle": "📂",
    "Archivio vecchi file": "🗃", "Altro": "🗂",
}
KEEP = "__KEEP__"  # categoria speciale: resta sul Desktop

DOC_CATEGORIES = {
    "Lavoro - CV e Candidature": ["curriculum", "cv", "esperienza lavorativa", "competenze", "resume",
                                  "lettera di presentazione", "candidatura", "skills", "work experience"],
    "Salute": ["referto", "visita", "medico", "medic", "medica", "prescrizione", "ricetta", "analisi del sangue",
               "asl", "paziente", "terapia", "sanitario", "certificato medico"],
    "Fatture e Pagamenti": ["fattura", "invoice", "ricevuta", "receipt", "pagamento", "imponibile",
                            "iva", "importo", "bolletta", "scadenza", "totale da pagare", "saldo"],
    "Banca e Tasse": ["estratto conto", "iban", "bonifico", "mutuo", "banca", "investimento", "f24",
                      "dichiarazione dei redditi", "isee", "730", "tasse", "cud", "busta paga"],
    "Contratti e Assicurazioni": ["contratto", "accordo", "clausola", "firmato", "procura", "nda",
                                  "termini e condizioni", "tribunale", "legale", "assicurazione",
                                  "polizza", "sinistro", "assicurato", "garanzia"],
    "Documenti Personali": ["carta d'identita", "carta d'identità", "passaporto", "codice fiscale",
                            "patente", "residenza", "anagrafe", "permesso di soggiorno"],
    "Lettere e Messaggi": ["lettera", "gentile", "egregio", "spett", "spettabile", "distinti saluti",
                           "cordiali saluti", "in fede", "oggetto:", "reclamo", "caro", "cara"],
    "Studio e Formazione": ["universita", "università", "corso", "lezione", "esame", "tesi", "dispensa",
                            "studente", "capitolo", "attestato", "scuola", "compito"],
    "Progetti e Preventivi": ["preventivo", "offerta", "progetto", "cliente", "quotation", "proposta",
                              "capitolato", "milestone"],
    "Report e Presentazioni": ["report", "relazione", "presentazione", "analisi", "risultati",
                               "slide", "kpi", "riepilogo", "conclusioni"],
    "Manuali e Guide": ["manuale", "guida", "istruzioni", "tutorial", "how to", "installazione",
                        "documentazione", "user guide"],
    "Viaggi": ["biglietto", "prenotazione", "volo", "hotel", "booking", "itinerario", "boarding"],
}

# Collegamenti ai programmi: parole chiave (cercate come parole intere nel nome
# del collegamento e nel nome dell'eseguibile di destinazione).
APP_RULES = [
    ("Giochi/Launcher e Strumenti", [
        "steam", "epic games", "epic games launcher", "ubisoft connect", "uplay", "paradox launcher",
        "gog galaxy", "battle.net", "ea app", "ea", "origin", "xbox", "rockstar games launcher",
        "riot client", "gamesir", "cheat engine", "playnite", "heroic", "itch", "amazon games",
        "tmodloader", "mumu", "bluestacks", "ldplayer", "retroarch", "ryujinx", "yuzu", "citron",
        "dolphin", "pcsx2", "rpcs3", "cemu"]),
    ("Programmi/Sviluppo", [
        "visual studio", "visual studio code", "vs code", "vscode", "cursor", "github desktop", "github",
        "git bash", "gitkraken", "dbeaver", "heidisql", "docker", "docker desktop", "postman", "pycharm",
        "intellij", "webstorm", "android studio", "node.js", "python", "idle", "anaconda", "jupyter",
        "sublime text", "notepad++", "wsl", "terminal", "windows terminal", "putty", "winscp", "filezilla",
        "mysql", "pgadmin", "mongodb compass", "unity", "unity hub", "unreal", "godot", "insomnia",
        "claude", "deneris"]),
    ("Programmi/Grafica e Media", [
        "blender", "photoshop", "illustrator", "premiere", "after effects", "davinci resolve", "resolve",
        "gimp", "krita", "inkscape", "obs", "obs studio", "audacity", "vlc", "spotify", "figma", "canva",
        "capcut", "handbrake", "paint.net", "lightroom", "fl studio", "ableton", "wallpaper engine",
        "medal", "streamlabs", "cinema 4d", "maxon", "zbrush", "substance"]),
    ("Programmi/Comunicazione", [
        "discord", "telegram", "whatsapp", "teams", "microsoft teams", "zoom", "slack", "skype",
        "signal", "thunderbird", "outlook"]),
    ("Programmi/Internet", [
        "chrome", "google chrome", "brave", "firefox", "edge", "microsoft edge", "opera", "opera gx",
        "vivaldi", "tor browser", "free download manager", "qbittorrent", "utorrent", "jdownloader"]),
    ("Programmi/Ufficio", [
        "word", "excel", "powerpoint", "libreoffice", "openoffice", "onenote", "notion", "obsidian",
        "acrobat", "adobe acrobat", "onlyoffice", "wps office"]),
    ("Programmi/Utilità e Sistema", [
        "tailscale", "nvidia", "nvidia app", "geforce experience", "amd", "radeon", "razer", "synapse",
        "logitech", "g hub", "corsair", "icue", "precision center", "evnia", "msi afterburner",
        "afterburner", "cpu-z", "gpu-z", "hwinfo", "hwmonitor", "ccleaner", "7-zip", "winrar",
        "anydesk", "teamviewer", "vpn", "nordvpn", "protonvpn", "driver", "benchmark", "heaven",
        "superposition", "3dmark", "surround", "realtek", "rufus", "everything", "powertoys",
        "control panel", "pannello di controllo", "crystaldiskinfo", "revo uninstaller"]),
]

GAME_SCHEMES = ("steam://", "uplay://", "com.epicgames.launcher://", "origin://", "origin2://",
                "battlenet://", "goggalaxy://", "eaapp://", "riotclient://", "xbox://", "ms-xbl",
                "heroic://", "playnite://", "itch://")
GAME_PATH_HINTS = ("steamapps", "\\epic games\\", "ubisoft game launcher\\games", "\\gog games\\",
                   "gog galaxy\\games", "\\riot games\\", "\\ea games\\", "\\xboxgames\\",
                   "\\rockstar games\\", "\\games\\")
WEBAPP_EXES = ("msedge_proxy.exe", "chrome_proxy.exe", "brave_proxy.exe", "opera_proxy.exe")

EXT_GROUPS = {
    "Immagini": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".heic", ".heif", ".svg",
                 ".tif", ".tiff", ".ico", ".raw", ".cr2", ".nef", ".psd", ".avif"},
    "Video e Audio": {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".webm", ".flv", ".m4v",
                      ".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".wma", ".opus"},
    "Archivi": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso", ".img", ".cab"},
    "Installer": {".exe", ".msi", ".msix", ".msixbundle", ".appx", ".appxbundle"},
    "Script e Codice": {".py", ".pyw", ".ipynb", ".js", ".ts", ".jsx", ".tsx", ".html", ".htm",
                        ".css", ".json", ".xml", ".yml", ".yaml", ".toml", ".bat", ".cmd", ".ps1",
                        ".sh", ".vbs", ".ahk", ".java", ".c", ".cpp", ".h", ".cs", ".go", ".rs",
                        ".php", ".rb", ".sql", ".lua", ".reg", ".ini", ".cfg", ".log"},
    "Giochi/ROM": {".nsp", ".xci", ".nca", ".nro", ".gba", ".gbc", ".gb", ".nes", ".sfc", ".smc",
                   ".n64", ".z64", ".nds", ".3ds", ".cia", ".wbfs", ".rvz", ".chd", ".cso"},
}
DOC_EXT = {".pdf", ".docx", ".doc", ".odt", ".rtf", ".txt", ".md", ".pptx", ".ppt", ".odp",
           ".xlsx", ".xls", ".ods", ".csv", ".pages", ".numbers", ".key", ".epub"}
READABLE_DOC_EXT = {".pdf", ".docx", ".odt", ".odp", ".ods", ".pptx", ".xlsx", ".txt", ".md", ".csv", ".rtf"}
SCRIPT_TARGET_EXT = {".bat", ".cmd", ".ps1", ".py", ".pyw", ".vbs", ".ahk", ".js"}
TEXT_PREVIEW_EXT = {".txt", ".md", ".csv", ".log", ".ini", ".cfg", ".json", ".xml", ".yml", ".yaml",
                    ".toml", ".py", ".pyw", ".js", ".ts", ".html", ".htm", ".css", ".bat", ".cmd",
                    ".ps1", ".sh", ".vbs", ".ahk", ".sql", ".reg", ".c", ".cpp", ".h", ".cs", ".java"}
SKIP_NAMES = {"desktop.ini", "thumbs.db", ".ds_store"}
EMULATION_HINTS = ("rom", "roms", "switch", "yuzu", "ryujinx", "citron", "suyu", "sudachi",
                   "emulat", "retroarch", "dolphin", "pcsx2", "rpcs3", "cemu", "ppsspp", "firmware", "keys")
STOPWORDS = set("""che con per una uno gli del della delle dei degli nel nella sono come anche
alla alle dal dalla piu più non the and for with that this from are was will have has
you your not all can their about which when also into more than other these questo questa
sono essere stato fatto molto tutto tutti dopo prima dove quando""".split())


# ============================================================ modello dati
@dataclass
class Item:
    path: Path
    is_dir: bool
    size: int
    mtime: float
    public: bool = False          # dal Desktop "Pubblico" (di tutti gli utenti)
    kind: str = ""                # descrizione leggibile del tipo
    target: str = ""              # destinazione di .lnk / URL di .url
    args: str = ""
    text: str = ""                # testo estratto (documenti)
    note: str = ""
    category: str = ""            # proposta automatica
    reason: str = ""
    override: str | None = None   # scelta manuale dell'utente
    selected: bool = True

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def ext(self) -> str:
        return "" if self.is_dir else self.path.suffix.lower()

    @property
    def final_category(self) -> str:
        return self.override if self.override is not None else self.category

    @property
    def moves(self) -> bool:
        return self.selected and self.final_category not in ("", KEEP)


@dataclass
class Tip:
    icon: str
    title: str
    detail: str
    items: list = field(default_factory=list)
    action: str | None = None      # "trash" | "keep" | "archive" | "option:<nome>" | None
    action_label: str = ""
    severity: int = 1              # 0 info, 1 consiglio, 2 importante


# ============================================================ utilita'
def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n} B"


def _kw_in(kw: str, text: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", text) is not None


def normalize_name(s: str) -> str:
    s = s.lower()
    s = re.sub(r"\s*-\s*(collegamento|shortcut|copia|copy)\b.*$", "", s)
    s = re.sub(r"[®™©’'`´]", "", s)
    s = re.sub(r"[^a-z0-9àèéìòù]+", " ", s)
    return " ".join(s.split())


def safe_folder_name(name: str) -> str:
    return re.sub(r'[<>:"\\|?*]', "", name).strip(" .")


def is_hidden_or_system(p: Path) -> bool:
    try:
        attrs = p.stat().st_file_attributes  # solo Windows
        return bool(attrs & (stat.FILE_ATTRIBUTE_HIDDEN | stat.FILE_ATTRIBUTE_SYSTEM))
    except (AttributeError, OSError):
        return p.name.startswith(".")


def managed_top_folders() -> set[str]:
    names = {safe_folder_name(k) for k in TOP_ICONS} | {SINGLE_FOLDER_NAME}
    return {n.lower() for n in names}


# ============================================================ collegamenti
def parse_lnk(p: Path) -> tuple[str, str]:
    """Legge un file .lnk di Windows e ritorna (destinazione, argomenti)."""
    try:
        data = p.read_bytes()
    except OSError:
        return "", ""
    if len(data) < 76 or data[:4] != b"\x4c\x00\x00\x00":
        return "", ""
    u16 = lambda o: int.from_bytes(data[o:o + 2], "little")
    u32 = lambda o: int.from_bytes(data[o:o + 4], "little")

    def cstr(o, wide):
        if wide:
            end = o
            while end + 1 < len(data) and data[end:end + 2] != b"\x00\x00":
                end += 2
            return data[o:end].decode("utf-16-le", "ignore")
        end = data.find(b"\x00", o)
        return data[o:end if end >= 0 else len(data)].decode("mbcs" if os.name == "nt" else "latin-1", "ignore")

    try:
        flags = u32(20)
        pos = 76
        if flags & 0x01:  # HasLinkTargetIDList
            pos += 2 + u16(pos)
        target = ""
        if flags & 0x02:  # HasLinkInfo
            start = pos
            size, hdr, li_flags = u32(start), u32(start + 4), u32(start + 8)
            if li_flags & 0x01:
                if hdr >= 0x24 and u32(start + 28):
                    target = cstr(start + u32(start + 28), True)
                else:
                    target = cstr(start + u32(start + 16), False)
                suffix_off = u32(start + 24)
                if hdr >= 0x24 and u32(start + 32):
                    suffix = cstr(start + u32(start + 32), True)
                else:
                    suffix = cstr(start + suffix_off, False) if suffix_off else ""
                if suffix:
                    target = target.rstrip("\\") + "\\" + suffix
            pos = start + size
        wide = bool(flags & 0x80)
        strings = {}
        for bit in (0x04, 0x08, 0x10, 0x20, 0x40):  # nome, percorso rel., cartella, argomenti, icona
            if flags & bit:
                n = u16(pos)
                pos += 2
                raw = data[pos:pos + (2 * n if wide else n)]
                pos += 2 * n if wide else n
                strings[bit] = raw.decode("utf-16-le" if wide else "latin-1", "ignore")
        if not target and 0x08 in strings:
            target = str((p.parent / strings[0x08]).resolve())
        if not target and flags & 0x200:  # HasExpString: percorso con %variabili%
            m = re.search(rb"(?:[A-Za-z]:|%[A-Za-z]+%)\\[^\x00]{3,260}?\.exe", data)
            if m:
                target = os.path.expandvars(m.group().decode("latin-1"))
        return target, strings.get(0x20, "")
    except Exception:
        return "", ""


def parse_url_file(p: Path) -> str:
    try:
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.strip().upper().startswith("URL="):
                return line.strip()[4:]
    except OSError:
        pass
    return ""


def shortcut_is_broken(item: Item) -> bool:
    t = item.target
    if item.ext != ".lnk" or not t or t.startswith("\\\\") or not re.match(r"^[A-Za-z]:\\", t):
        return False
    if not Path(t[:3]).exists():  # disco esterno scollegato: non lo considero rotto
        return False
    return not Path(t).exists()


# ============================================================ lettura testo
def _xml_text(xml: str) -> str:
    xml = re.sub(r"</(w:p|a:p|text:p|text:h)>", "\n", xml)
    return html.unescape(re.sub(r"<[^>]+>", " ", xml))


def _pdf_text_fallback(p: Path) -> str:
    """Estrazione grezza del testo da PDF senza librerie esterne."""
    try:
        raw = p.read_bytes()[:6_000_000]
    except OSError:
        return ""
    chunks = []
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", raw, re.S):
        body = m.group(1)
        try:
            body = zlib.decompress(body)
        except Exception:
            pass
        for s in re.findall(rb"\((.*?)(?<!\\)\)\s*'?(?:Tj|TJ|')|\[(.*?)\]\s*TJ", body, re.S):
            part = s[0] or s[1]
            if s[1]:
                part = b"".join(re.findall(rb"\((.*?)(?<!\\)\)", s[1], re.S))
            chunks.append(part.replace(rb"\(", b"(").replace(rb"\)", b")").decode("latin-1", "ignore"))
        if sum(len(c) for c in chunks) > 30000:
            break
    text = " ".join(chunks)
    letters = sum(ch.isalpha() for ch in text)
    return text if text and letters / max(len(text), 1) > 0.5 else ""


def read_text(p: Path, limit: int = 30000) -> tuple[str, str]:
    """Ritorna (testo, nota). Non solleva mai eccezioni."""
    ext = p.suffix.lower()
    try:
        if ext == ".pdf":
            if PdfReader is not None:
                r = PdfReader(str(p))
                if r.is_encrypted:
                    return "", "PDF protetto da password"
                text = " ".join((pg.extract_text() or "") for pg in r.pages[:8])
            else:
                text = _pdf_text_fallback(p)
            if not text.strip():
                return "", "PDF senza testo leggibile (scansione?): classificato dal nome"
            return text[:limit], ""
        if ext in (".docx", ".odt", ".odp", ".ods", ".pptx", ".xlsx"):
            with zipfile.ZipFile(p) as z:
                names = z.namelist()
                if ext == ".docx":
                    parts = ["word/document.xml"]
                elif ext in (".odt", ".odp", ".ods"):
                    parts = ["content.xml"]
                elif ext == ".pptx":
                    parts = sorted((n for n in names if re.match(r"ppt/slides/slide\d+\.xml", n)),
                                   key=lambda n: int(re.findall(r"\d+", n)[-1]))
                else:
                    parts = ["xl/sharedStrings.xml"]
                text = " ".join(_xml_text(z.read(n).decode("utf8", "ignore")) for n in parts if n in names)
                return re.sub(r"[ \t]+", " ", text)[:limit], ""
        if ext in (".txt", ".md", ".csv", ".rtf"):
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                text = f.read(limit)
            if ext == ".rtf":
                text = re.sub(r"\\[a-z]+-?\d* ?|[{}]", " ", text)
            return text, ""
    except Exception as e:
        return "", f"non leggibile ({type(e).__name__})"
    return "", ""


def preview_text(item: Item, limit: int = 2500) -> str:
    """Testo da mostrare nel riquadro anteprima."""
    if item.text:
        return item.text[:limit].strip()
    if item.ext in TEXT_PREVIEW_EXT:
        try:
            with open(item.path, "r", encoding="utf-8", errors="replace") as f:
                return f.read(limit)
        except OSError:
            return ""
    return ""


# ============================================================ scansione
def scan(root: Path, include_public: bool = True, include_folders: bool = False,
         progress=None) -> list[Item]:
    """Elenca gli elementi da valutare (non entra nelle sottocartelle)."""
    sources = [(root, False)]
    if include_public and PUBLIC_DESKTOP and root.resolve() == DESKTOP.resolve() and PUBLIC_DESKTOP.exists():
        sources.append((PUBLIC_DESKTOP, True))
    managed = managed_top_folders()
    items: list[Item] = []
    for base, public in sources:
        try:
            entries = list(base.iterdir())
        except OSError:
            continue
        for p in entries:
            low = p.name.lower()
            if low in SKIP_NAMES or p.name.startswith("~$") or is_hidden_or_system(p):
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            is_dir = p.is_dir()
            if is_dir:
                if not include_folders or public or low in managed:
                    continue
                if APP_DIR == p.resolve() or APP_DIR.is_relative_to(p.resolve()):
                    continue  # non spostare la cartella di questo programma
            items.append(Item(path=p, is_dir=is_dir, size=0 if is_dir else st.st_size,
                              mtime=st.st_mtime, public=public))
    return items


def folder_stats(p: Path, max_entries: int = 20000) -> tuple[int, int]:
    """(numero file, dimensione totale) con un limite per non bloccare."""
    count = total = 0
    try:
        for dirpath, _, files in os.walk(p):
            for f in files:
                count += 1
                try:
                    total += os.path.getsize(os.path.join(dirpath, f))
                except OSError:
                    pass
                if count >= max_entries:
                    return count, total
    except OSError:
        pass
    return count, total


# ============================================================ classificazione
def classify_shortcut(item: Item) -> tuple[str, str]:
    name = item.path.stem.lower()
    target_low = item.target.lower()
    exe = Path(item.target).name.lower() if item.target and not target_low.startswith(("http", "steam")) else ""
    haystack = f"{name} {Path(exe).stem}"

    if re.search(r"riordina[ _-]?(desktop|installa)", target_low + " " + item.args.lower()):
        return KEEP, "è il collegamento a questo programma"
    if item.ext == ".lnk" and (exe in WEBAPP_EXES or "--app-id" in item.args or "--app=" in item.args):
        return "Siti e App Web", "app web installata dal browser"

    for cat, kws in APP_RULES:
        for kw in kws:
            if _kw_in(kw, haystack):
                return cat, f"riconosciuto: “{kw}”"

    if item.ext == ".lnk":
        if Path(exe).suffix in SCRIPT_TARGET_EXT or re.search(r"\.(bat|cmd|ps1|py|vbs|ahk)\b", name):
            return "Script e Codice", "collegamento a uno script"
        if item.target and Path(item.target).is_dir():
            return "Collegamenti a cartelle", "collegamento a una cartella"

    if target_low.startswith(GAME_SCHEMES):
        store = target_low.split("://")[0].replace("com.epicgames.launcher", "epic")
        return "Giochi", f"gioco ({store.capitalize()})"
    if any(h in target_low for h in GAME_PATH_HINTS):
        return "Giochi", "installato in una cartella di giochi"
    if target_low.startswith(("http://", "https://")):
        return "Siti e App Web", "link a un sito"
    if item.ext == ".url":
        return "Siti e App Web", "collegamento internet"
    return "Programmi/Altri programmi", "collegamento a un programma"


def score_doc(name: str, text: str) -> dict[str, int]:
    name, text = name.lower(), text.lower()
    out = {}
    for cat, kws in DOC_CATEGORIES.items():
        s = 0
        for kw in kws:
            if len(kw) <= 3 or kw in ("caro", "cara", "spett"):
                pat = rf"(?<![a-zà-ù0-9]){re.escape(kw)}(?![a-zà-ù0-9])"
                s += min(len(re.findall(pat, text)), 5) + 6 * len(re.findall(pat, name))
            else:
                s += min(text.count(kw), 5) + 6 * name.count(kw)
        out[cat] = s
    return out


def looks_like_personal_letter(item: Item) -> bool:
    """Testo che inizia rivolgendosi a qualcuno: “Marco, ...”, “Caro Luca, ...”."""
    start = item.text.lstrip()[:60].lower()
    stem = item.path.stem.strip().lower()
    if re.match(r"^(car[oaie]|gentil[ei]|ciao|egregi[oa]|spett\w*)\b[^,\n]{0,40},", start):
        return True
    return bool(stem) and len(stem.split()) <= 2 and re.match(rf"^{re.escape(stem)}\s*[,!]", start) is not None


def classify_documents(docs: list[Item]) -> None:
    """Classifica i documenti per contenuto (parole chiave nel testo e nel nome)."""
    for it in docs:
        if looks_like_personal_letter(it):
            it.category, it.reason = "Documenti/Lettere e Messaggi", "inizia rivolgendosi a una persona"
            continue
        scores = score_doc(it.path.stem, it.text)
        cat, s = max(scores.items(), key=lambda kv: kv[1])
        if s >= 3:
            it.category, it.reason = f"Documenti/{cat}", f"parole chiave: {cat.lower()} (punteggio {s})"
        elif it.ext in (".txt", ".md"):
            it.category, it.reason = "Documenti/Appunti e Note", "nota di testo"
        else:
            it.category, it.reason = "Documenti/Altri documenti", "contenuto non riconosciuto"


def classify_folder(item: Item) -> tuple[str, str]:
    low = item.name.lower()
    if any(h in low for h in EMULATION_HINTS):
        return "Giochi/Emulazione", "cartella legata a emulatori/ROM"
    for cat, kws in APP_RULES:
        if cat.startswith("Programmi") and any(_kw_in(kw, low) for kw in kws):
            return cat, "cartella di un programma"
    return "Cartelle", "cartella"


def classify(items: list[Item], read_contents: bool = True, progress=None) -> None:
    docs = []
    for i, it in enumerate(items, 1):
        if progress and i % 5 == 0:
            progress(i, len(items), it.name)
        ext = it.ext
        if it.is_dir:
            it.kind = "Cartella"
            it.category, it.reason = classify_folder(it)
        elif ext == ".lnk":
            it.kind = "Collegamento"
            it.target, it.args = parse_lnk(it.path)
            it.category, it.reason = classify_shortcut(it)
        elif ext == ".url":
            it.kind = "Link internet"
            it.target = parse_url_file(it.path)
            it.category, it.reason = classify_shortcut(it)
        elif ext in DOC_EXT:
            it.kind = f"Documento {ext[1:].upper()}"
            if read_contents and ext in READABLE_DOC_EXT:
                it.text, it.note = read_text(it.path)
            docs.append(it)
        else:
            it.kind = f"File {ext[1:].upper()}" if ext else "File"
            for group, exts in EXT_GROUPS.items():
                if ext in exts:
                    it.category, it.reason = group, "tipo di file"
                    break
            else:
                it.category, it.reason = "Altro", "tipo di file non comune"
            low = it.path.stem.lower()
            if it.category == "Immagini" and re.search(r"screen|schermata|cattura|snip|capture", low):
                it.category, it.reason = "Immagini/Screenshot", "sembra uno screenshot"
            if it.category == "Script e Codice":
                it.kind = f"Script {ext[1:].upper()}"
    classify_documents(docs)


# ============================================================ consigli
def build_tips(items: list[Item], root: Path, include_folders: bool, include_public: bool,
               old_months: int = 12) -> list[Tip]:
    tips: list[Tip] = []
    now = time.time()
    shortcuts = [it for it in items if it.ext in (".lnk", ".url")]

    # 1. collegamenti doppi (stessa destinazione o stesso nome)
    target_key = lambda x: (x.target + " " + x.args).strip().lower()
    by_target, by_name = defaultdict(list), defaultdict(list)
    for it in shortcuts:
        if it.target:
            by_target[target_key(it)].append(it)
        by_name[normalize_name(it.path.stem)].append(it)
    for g in by_target.values():
        if len(g) >= 2:
            keep = min(g, key=lambda x: (x.public, len(x.name), -x.mtime))
            tips.append(Tip("📑", f"Collegamento doppio: “{keep.path.stem}”",
                            f"{len(g)} collegamenti aprono esattamente la stessa cosa. "
                            f"Tieni “{keep.name}” e manda gli altri nel Cestino.",
                            [x for x in g if x is not keep], "trash", "Sposta i doppioni nel Cestino", 2))
    for g in by_name.values():
        targets = {target_key(x) for x in g}
        if len(g) >= 2 and len(targets) >= 2:
            stores = sorted({x.target.split("://")[0].capitalize() if "://" in x.target else "programma" for x in g})
            tips.append(Tip("🔁", f"Stesso nome, destinazioni diverse: “{g[0].path.stem}”",
                            f"{len(g)} collegamenti con nome quasi uguale aprono cose diverse "
                            f"({', '.join(stores)}). Forse hai lo stesso gioco/programma installato due "
                            "volte: se ne usi solo uno, puoi disinstallare l'altro e liberare spazio.",
                            g, None, "", 1))

    # 2. collegamenti rotti
    broken = [it for it in shortcuts if shortcut_is_broken(it)]
    if broken:
        tips.append(Tip("💔", f"{len(broken)} collegamenti non funzionano più",
                        "Puntano a programmi o file che non esistono più (probabilmente disinstallati).",
                        broken, "trash", "Sposta nel Cestino", 2))

    # 3. zip gia' estratti
    names_on_desktop = {p.name.lower() for p in root.iterdir()} if root.exists() else set()
    extracted = [it for it in items if it.ext in (".zip", ".rar", ".7z")
                 and it.path.stem.lower() in names_on_desktop]
    if extracted:
        tips.append(Tip("🧳", "Archivi già estratti",
                        "Accanto a questi archivi c'è già una cartella con lo stesso nome: "
                        "se il contenuto è a posto, l'archivio non serve più.",
                        extracted, "trash", "Sposta gli archivi nel Cestino", 1))

    # 4. installer
    installers = [it for it in items if it.ext in (".exe", ".msi", ".msix", ".appx")]
    if installers:
        likely = [it for it in installers if re.search(r"setup|install|installer|update|driver", it.name.lower())]
        tips.append(Tip("📦", f"{len(installers)} file di installazione sul Desktop",
                        "Dopo aver installato un programma il file di installazione non serve più: "
                        "puoi riscaricarlo quando vuoi. " + (f"{len(likely)} hanno proprio “setup/installer” nel nome." if likely else ""),
                        likely or installers, "trash", "Sposta nel Cestino", 1))

    # 5. file vuoti
    empty = [it for it in items if not it.is_dir and it.size == 0 and it.ext not in (".lnk", ".url")]
    if empty:
        tips.append(Tip("🫙", f"{len(empty)} file vuoti (0 byte)",
                        "Non contengono nulla: probabilmente creati per errore.",
                        empty, "trash", "Sposta nel Cestino", 1))

    # 6. file vecchi
    if old_months:
        limit = now - old_months * 30 * 86400
        old = [it for it in items if not it.is_dir and it.ext not in (".lnk", ".url") and it.mtime < limit]
        if old:
            tips.append(Tip("🗃", f"{len(old)} file non modificati da oltre {old_months} mesi",
                            "Puoi spostarli in “Archivio vecchi file”, divisi per anno, così restano "
                            "conservati ma non ti intralciano.",
                            old, "archive", "Metti in Archivio vecchi file", 1))

    # 7. file grandi
    big = [it for it in items if it.size > 500 * 1024 ** 2]
    if big:
        tot = human_size(sum(it.size for it in big))
        tips.append(Tip("🐘", f"{len(big)} file molto grandi ({tot})",
                        "Il Desktop non è il posto ideale per file enormi: valuta di spostarli su un "
                        "altro disco o in Video/Download.", big, None, "", 1))

    # 8. cartelle non incluse
    if not include_folders:
        managed = managed_top_folders()
        folders = [p for p in root.iterdir() if p.is_dir() and not is_hidden_or_system(p)
                   and p.name.lower() not in managed] if root.exists() else []
        if folders:
            tips.append(Tip("📁", f"{len(folders)} cartelle sparse sul Desktop",
                            "Per sicurezza le cartelle non vengono spostate. Se vuoi, attiva l'opzione per "
                            "includerle (es. emulatori/ROM → Giochi/Emulazione).",
                            [Item(path=p, is_dir=True, size=0, mtime=0) for p in folders],
                            "option:include_folders", "Includi le cartelle", 0))

    # 9. Desktop pubblico
    pub = [it for it in items if it.public]
    if pub:
        tips.append(Tip("🔐", f"{len(pub)} collegamenti sono nel Desktop di tutti gli utenti",
                        "Li vedi sul Desktop ma stanno in una cartella di sistema: per spostarli Windows "
                        "potrebbe chiedere i permessi di amministratore (pulsante in basso).",
                        pub, None, "", 0))

    # 10. consigli generali
    n_short = len(shortcuts)
    if n_short > 12:
        games = sum(1 for it in shortcuts if it.final_category.startswith("Giochi"))
        tips.append(Tip("📌", "Lascia sul Desktop solo i preferiti",
                        f"Hai {n_short} collegamenti ({games} giochi). Un buon trucco: tieni sul Desktop i "
                        "3–6 che usi ogni giorno (tasto destro → “Lascia sul Desktop”) e metti il resto "
                        "nelle cartelle. Puoi anche aggiungerli alla barra delle applicazioni o a Start.",
                        [], None, "", 0))
    tips.append(Tip("💡", "Tieni il Desktop in ordine nel tempo",
                    "Riapri questo programma una volta al mese: in un minuto rimetti tutto a posto. "
                    "I download finiscono in “Download”, non sul Desktop: salva lì e sposta solo ciò che serve.",
                    [], None, "", 0))
    tips.sort(key=lambda t: -t.severity)
    return tips


# ============================================================ destinazioni e spostamenti
def destination_dir(item: Item, root: Path, single_folder: bool, docs_to_documents: bool) -> Path:
    cat = item.final_category
    parts = [safe_folder_name(x) for x in cat.split("/") if x]
    if docs_to_documents and parts and parts[0] == "Documenti":
        return DOCUMENTS.joinpath(*parts[1:]) if len(parts) > 1 else DOCUMENTS
    base = root / SINGLE_FOLDER_NAME if single_folder else root
    return base.joinpath(*parts)


def free_path(dest: Path) -> Path:
    if not dest.exists():
        return dest
    i = 2
    while True:
        c = dest.with_name(f"{dest.stem} ({i}){dest.suffix}") if not dest.is_dir() else dest.with_name(f"{dest.name} ({i})")
        if not c.exists():
            return c
        i += 1


def apply_moves(items: list[Item], root: Path, single_folder: bool, docs_to_documents: bool,
                progress=None) -> tuple[list[dict], list[tuple[str, str]], Path | None]:
    moves, errors, created = [], [], []
    todo = [it for it in items if it.moves]
    for i, it in enumerate(todo, 1):
        if progress:
            progress(i, len(todo), it.name)
        folder = destination_dir(it, root, single_folder, docs_to_documents)
        try:
            # crea le cartelle mancanti ricordandole per l'annullamento
            missing = []
            f = folder
            while not f.exists():
                missing.append(f)
                f = f.parent
            folder.mkdir(parents=True, exist_ok=True)
            created.extend(str(m) for m in reversed(missing))
            if it.path.parent.resolve() == folder.resolve():
                continue
            dest = free_path(folder / it.name)
            shutil.move(str(it.path), str(dest))
            moves.append({"da": str(it.path), "a": str(dest)})
        except PermissionError:
            errors.append((it.name, "permesso negato" + (" (Desktop pubblico: serve amministratore)" if it.public else "")))
        except Exception as e:
            errors.append((it.name, f"{type(e).__name__}: {e}"))
    log = None
    if moves:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log = LOG_DIR / f"riordino_{datetime.now():%Y%m%d_%H%M%S}.json"
        log.write_text(json.dumps({"quando": datetime.now().isoformat(timespec="seconds"),
                                   "cartella": str(root), "spostamenti": moves,
                                   "cartelle_create": created}, ensure_ascii=False, indent=1),
                       encoding="utf-8")
    return moves, errors, log


def last_log() -> Path | None:
    logs = sorted(LOG_DIR.glob("riordino_*.json")) if LOG_DIR.exists() else []
    logs = [l for l in logs if not l.name.endswith(".annullato.json")]
    return logs[-1] if logs else None


def undo_last() -> tuple[int, int, str]:
    log = last_log()
    if not log:
        return 0, 0, ""
    data = json.loads(log.read_text(encoding="utf-8"))
    ok = skipped = 0
    for m in reversed(data["spostamenti"]):
        src, dst = Path(m["da"]), Path(m["a"])
        try:
            if dst.exists() and not src.exists():
                src.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(dst), str(src))
                ok += 1
            else:
                skipped += 1
        except Exception:
            skipped += 1
    # rimuove solo le cartelle create dal riordino e rimaste vuote (dalla piu' profonda)
    for d in sorted(set(data.get("cartelle_create", [])), key=lambda s: -len(Path(s).parts)):
        try:
            Path(d).rmdir()
        except OSError:
            pass
    log.rename(log.with_name(log.stem + ".annullato.json"))
    return ok, skipped, data.get("quando", "")


def send_to_recycle_bin(paths: list[Path]) -> tuple[int, list[str]]:
    """Sposta nel Cestino (recuperabile). Ritorna (numero ok, errori)."""
    ok, errors = 0, []
    if os.name != "nt":
        return 0, ["Cestino supportato solo su Windows"]
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR),
                    ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_ushort),
                    ("fAnyOperationsAborted", wintypes.BOOL), ("hNameMappings", ctypes.c_void_p),
                    ("lpszProgressTitle", wintypes.LPCWSTR)]
    FO_DELETE, FOF_SILENT, FOF_NOCONFIRMATION, FOF_ALLOWUNDO, FOF_NOERRORUI = 3, 4, 16, 64, 1024
    for p in paths:
        if not p.exists():
            continue
        op = SHFILEOPSTRUCTW(None, FO_DELETE, str(p) + "\0", None,
                             FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI, False, None, None)
        res = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        if res == 0 and not op.fAnyOperationsAborted and not p.exists():
            ok += 1
        else:
            errors.append(f"{p.name} (codice {res})")
    return ok, errors


# ============================================================ impostazioni
DEFAULT_CONFIG = {
    "root": "", "include_public": True, "include_folders": False, "single_folder": False,
    "docs_to_documents": False, "read_contents": True, "old_months": 12,
    "keep": [], "overrides": {},
}


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    try:
        cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass
    return cfg


def save_config(cfg: dict) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def analyze(root: Path, cfg: dict, progress=None) -> tuple[list[Item], list[Tip]]:
    """Scansione completa + classificazione + preferenze utente + consigli."""
    items = scan(root, cfg["include_public"], cfg["include_folders"])
    classify(items, cfg["read_contents"], progress)
    keep, overrides = set(cfg.get("keep", [])), cfg.get("overrides", {})
    for it in items:
        key = str(it.path)
        if key in keep:
            it.override = KEEP
        elif key in overrides:
            it.override = overrides[key]
    tips = build_tips(items, root, cfg["include_folders"], cfg["include_public"], cfg.get("old_months", 12))
    return items, tips


if __name__ == "__main__":  # anteprima veloce da riga di comando
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else DESKTOP
    its, tps = analyze(root, load_config())
    by = defaultdict(list)
    for it in its:
        by[it.final_category].append(it)
    for cat in sorted(by):
        print(f"[{cat}] ({len(by[cat])})")
        for it in sorted(by[cat], key=lambda x: x.name.lower()):
            print(f"    {it.name:55s} {it.reason}{'  | ' + it.note if it.note else ''}")
    print("\nCONSIGLI:")
    for t in tps:
        print(f" {t.icon} {t.title}  [{len(t.items)}]")
