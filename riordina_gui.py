"""
Riordina Desktop - interfaccia grafica.

Avvio:  collegamento "Riordina Desktop" (Desktop o menu Start), pythonw riordina_desktop.pyw,
        oppure l'eseguibile Riordina-Installa.exe (vedi installa.py).
Collegamenti e icona:  python strumenti/collegamento.py
Nessun file viene toccato finche' non premi "Riordina ora", e ogni riordino si puo' annullare.
"""
from __future__ import annotations

import ctypes
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

sys.path.insert(0, str(Path(__file__).resolve().parent))
import riordina_core as core  # noqa: E402

try:
    from PIL import Image, ImageTk  # opzionale: anteprima JPG/WEBP/...
except ImportError:
    Image = ImageTk = None

# ------------------------------------------------------------------ stile
BG, CARD, BORDER = "#f3f4fa", "#ffffff", "#e2e4ef"
TEXT, MUTED = "#1d2033", "#6b7086"
ACCENT, ACCENT_DARK, ACCENT_SOFT = "#5b54e8", "#4740c9", "#ecebff"
HEADER, HEADER2 = "#1c1d3a", "#2d2f5c"
GREEN, ORANGE, RED = "#16a36b", "#e58a17", "#dc4646"
FONT = "Segoe UI"
F, FB, FS = (FONT, 10), (FONT, 10, "bold"), (FONT, 9)
KEEP_LABEL = "📌 Resta sul Desktop"
ON, OFF, MIXED = "☑", "☐", "◩"

TOP_ORDER = ["Giochi", "Programmi", "Siti e App Web", "Documenti", "Immagini", "Video e Audio",
             "Script e Codice", "Archivi", "Installer", "Collegamenti a cartelle", "Cartelle",
             "Archivio vecchi file", "Altro"]


def item_icon(it: core.Item) -> str:
    c = it.final_category
    if it.is_dir:
        return "📁"
    if it.ext in (".lnk", ".url"):
        if c.startswith("Giochi"):
            return "🎮"
        if c.startswith("Siti"):
            return "🌐"
        return "🔗"
    top = c.split("/")[0]
    return {"Documenti": "📄", "Immagini": "🖼", "Video e Audio": "🎬", "Archivi": "🧳",
            "Installer": "📦", "Script e Codice": "💻"}.get(top, "📄")


def all_known_categories(items) -> list[str]:
    cats = {f"Documenti/{c}" for c in core.DOC_CATEGORIES}
    cats |= {"Documenti/Appunti e Note", "Documenti/Altri documenti", "Programmi/Altri programmi",
             "Giochi", "Giochi/Emulazione", "Immagini/Screenshot", "Siti e App Web", "Cartelle",
             "Collegamenti a cartelle", "Altro"}
    cats |= {c for c, _ in core.APP_RULES} | set(core.EXT_GROUPS)
    cats |= {it.final_category for it in items if it.final_category not in ("", core.KEEP)}
    return sorted(cats, key=lambda c: (TOP_ORDER.index(c.split("/")[0]) if c.split("/")[0] in TOP_ORDER else 99, c))


# ------------------------------------------------------------------ app
class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.cfg = core.load_config()
        r = self.cfg.get("root")
        self.root_dir = Path(r) if r and Path(r).is_dir() else core.DESKTOP
        self.items: list[core.Item] = []
        self.tips: list[core.Tip] = []
        self.q: queue.Queue = queue.Queue()
        self.busy = False
        self.open_nodes: set[str] | None = None
        self._img = None
        self.cat_values: list[str] = []

        root.title(core.APP_NAME)
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        w, h = min(int(sw * 0.86), 1700), min(int(sh * 0.86), 1100)
        root.geometry(f"{w}x{h}+{(sw - w) // 2}+{max(0, (sh - h) // 2 - 20)}")
        root.minsize(min(1000, sw - 40), min(640, sh - 80))
        root.configure(bg=BG)
        self._style()
        self._build()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(100, self._poll)
        self.analyze()

    # -------------------------------------------------------------- stile ttk
    def _style(self):
        st = ttk.Style(self.root)
        st.theme_use("clam")
        st.configure(".", font=F, background=BG, foreground=TEXT, bordercolor=BORDER)
        st.configure("TFrame", background=BG)
        st.configure("Card.TFrame", background=CARD)
        st.configure("TLabel", background=BG, foreground=TEXT)
        st.configure("Card.TLabel", background=CARD)
        st.configure("Muted.TLabel", background=BG, foreground=MUTED, font=FS)
        st.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT,
                     rowheight=30, borderwidth=0, font=F)
        st.configure("Treeview.Heading", font=FS, background=BG, foreground=MUTED, relief="flat",
                     padding=(6, 6))
        st.map("Treeview", background=[("selected", ACCENT_SOFT)], foreground=[("selected", TEXT)])
        st.map("Treeview.Heading", background=[("active", BG)])
        st.configure("TButton", padding=(12, 6), background="#eef0f8", lightcolor="#eef0f8",
                     darkcolor="#eef0f8", bordercolor="#d6d9e8", relief="flat", borderwidth=1)
        st.map("TButton", background=[("active", ACCENT_SOFT), ("disabled", BG)],
               lightcolor=[("active", ACCENT_SOFT)], darkcolor=[("active", ACCENT_SOFT)],
               bordercolor=[("active", ACCENT)], foreground=[("disabled", "#a3a6b8")])
        st.configure("Tool.TButton", padding=(10, 4), font=FS)
        st.configure("TCheckbutton", indicatorbackground=CARD, indicatorforeground=ACCENT)
        st.configure("TRadiobutton", indicatorbackground=CARD, indicatorforeground=ACCENT)
        st.configure("Accent.TButton", background=ACCENT, foreground="white", font=FB, lightcolor=ACCENT,
                     darkcolor=ACCENT, bordercolor=ACCENT, padding=(18, 9), borderwidth=0)
        st.map("Accent.TButton", background=[("active", ACCENT_DARK), ("disabled", "#b9b6f0")],
               lightcolor=[("active", ACCENT_DARK), ("disabled", "#b9b6f0")],
               darkcolor=[("active", ACCENT_DARK), ("disabled", "#b9b6f0")],
               bordercolor=[("active", ACCENT_DARK), ("disabled", "#b9b6f0")],
               foreground=[("disabled", "#f2f2ff")])
        st.configure("Header.TButton", background=HEADER2, foreground="white", padding=(14, 7), borderwidth=0,
                     lightcolor=HEADER2, darkcolor=HEADER2, bordercolor=HEADER2)
        st.map("Header.TButton", background=[("active", "#3c3f78"), ("disabled", HEADER2)],
               lightcolor=[("active", "#3c3f78")], darkcolor=[("active", "#3c3f78")],
               bordercolor=[("active", "#3c3f78")], foreground=[("disabled", "#8d8fbf")])
        st.configure("Danger.TButton", foreground=RED)
        st.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 0, 0, 0))
        st.configure("TNotebook.Tab", padding=(18, 8), font=FB, background=BG, foreground=MUTED, borderwidth=0)
        st.map("TNotebook.Tab", background=[("selected", CARD)], foreground=[("selected", ACCENT)])
        st.configure("TCheckbutton", background=CARD, font=F)
        st.configure("TRadiobutton", background=CARD, font=F)
        st.map("TCheckbutton", background=[("active", CARD)])
        st.map("TRadiobutton", background=[("active", CARD)])
        st.configure("Horizontal.TProgressbar", troughcolor=BORDER, background=ACCENT, borderwidth=0, thickness=6)
        st.configure("TCombobox", padding=5)
        st.configure("TEntry", padding=5)

    # -------------------------------------------------------------- layout
    def _build(self):
        # intestazione
        head = tk.Frame(self.root, bg=HEADER, height=78)
        head.pack(fill="x")
        left = tk.Frame(head, bg=HEADER)
        left.pack(side="left", padx=22, pady=12)
        tk.Label(left, text="✨ Riordina Desktop", bg=HEADER, fg="white", font=(FONT, 17, "bold")).pack(anchor="w")
        self.lbl_path = tk.Label(left, text="", bg=HEADER, fg="#a9abd6", font=FS)
        self.lbl_path.pack(anchor="w")
        right = tk.Frame(head, bg=HEADER)
        right.pack(side="right", padx=18)
        self.btn_rescan = ttk.Button(right, text="🔄  Analizza di nuovo", style="Header.TButton", command=self.analyze)
        self.btn_rescan.pack(side="right", padx=4)
        ttk.Button(right, text="📂  Cambia cartella…", style="Header.TButton", command=self.choose_folder).pack(side="right", padx=4)
        self.btn_desktop = ttk.Button(right, text="🖥  Desktop", style="Header.TButton", command=self.back_to_desktop)

        # schede riepilogo
        stats = tk.Frame(self.root, bg=BG)
        stats.pack(fill="x", padx=18, pady=(14, 4))
        self.stat_labels = {}
        for key, caption, color in [("before", "icone sul Desktop ora", TEXT),
                                    ("after", "icone dopo il riordino", GREEN),
                                    ("moves", "elementi da spostare", ACCENT),
                                    ("tips", "consigli per te", ORANGE)]:
            card = tk.Frame(stats, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
            card.pack(side="left", fill="x", expand=True, padx=5)
            num = tk.Label(card, text="–", bg=CARD, fg=color, font=(FONT, 22, "bold"))
            num.pack(anchor="w", padx=16, pady=(10, 0))
            tk.Label(card, text=caption, bg=CARD, fg=MUTED, font=FS).pack(anchor="w", padx=16, pady=(0, 10))
            self.stat_labels[key] = num

        # barra in basso
        foot = tk.Frame(self.root, bg=BG)
        foot.pack(side="bottom", fill="x", padx=22, pady=12)
        self.status = tk.Label(foot, text="", bg=BG, fg=MUTED, font=F, anchor="w", justify="left")
        self.status.pack(side="left", fill="x", expand=True)
        self.progress = ttk.Progressbar(foot, mode="determinate", length=180)
        self.btn_apply = ttk.Button(foot, text="✨  Riordina ora", style="Accent.TButton", command=self.apply)
        self.btn_apply.pack(side="right", padx=(8, 0))
        self.btn_undo = ttk.Button(foot, text="↩  Annulla ultimo riordino", command=self.undo)
        self.btn_undo.pack(side="right", padx=4)
        self.btn_admin = ttk.Button(foot, text="🛡  Riapri come amministratore", command=self.relaunch_admin)

        # schede
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=22, pady=(10, 0))
        self.tab_preview = ttk.Frame(self.nb, style="Card.TFrame")
        self.tab_tips = ttk.Frame(self.nb, style="Card.TFrame")
        self.tab_opts = ttk.Frame(self.nb, style="Card.TFrame")
        self.nb.add(self.tab_preview, text="🗂  Anteprima")
        self.nb.add(self.tab_tips, text="💡  Consigli")
        self.nb.add(self.tab_opts, text="⚙  Opzioni")
        self._build_preview()
        self._build_tips()
        self._build_options()

    # ---------------------------------------------------- scheda anteprima
    def _build_preview(self):
        pw = ttk.PanedWindow(self.tab_preview, orient="horizontal")
        pw.pack(fill="both", expand=True, padx=1, pady=1)

        left = ttk.Frame(pw, style="Card.TFrame")
        bar = ttk.Frame(left, style="Card.TFrame")
        bar.pack(fill="x", padx=12, pady=(12, 6))
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *_: self.refresh_tree())
        ent = ttk.Entry(bar, textvariable=self.search, width=24)
        ent.pack(side="left")
        ttk.Label(bar, text="🔎 cerca", style="Card.TLabel", foreground=MUTED).pack(side="left", padx=(6, 14))
        ttk.Button(bar, text="Tutto", style="Tool.TButton", width=7, command=lambda: self.set_all(True)).pack(side="left", padx=2)
        ttk.Button(bar, text="Niente", style="Tool.TButton", width=8, command=lambda: self.set_all(False)).pack(side="left", padx=2)
        ttk.Button(bar, text="Espandi", style="Tool.TButton", width=9, command=lambda: self.expand_all(True)).pack(side="left", padx=(12, 2))
        ttk.Button(bar, text="Comprimi", style="Tool.TButton", width=10, command=lambda: self.expand_all(False)).pack(side="left", padx=2)
        self.lbl_dest = ttk.Label(left, text="", style="Card.TLabel", foreground=MUTED, font=FS)
        self.lbl_dest.pack(fill="x", padx=14)

        tree_wrap = ttk.Frame(left, style="Card.TFrame")
        tree_wrap.pack(fill="both", expand=True, padx=12, pady=(6, 12))
        self.tree = ttk.Treeview(tree_wrap, columns=("sel", "kind", "size", "why"), selectmode="extended")
        self.tree.heading("#0", text="Struttura proposta", anchor="w")
        self.tree.heading("sel", text="Sposta")
        self.tree.heading("kind", text="Tipo", anchor="w")
        self.tree.heading("size", text="Dim.", anchor="e")
        self.tree.heading("why", text="Perché", anchor="w")
        self.tree.column("#0", width=340, minwidth=200)
        self.tree.column("sel", width=70, anchor="center", stretch=False)
        self.tree.column("kind", width=130, stretch=False)
        self.tree.column("size", width=70, anchor="e", stretch=False)
        self.tree.column("why", width=220, minwidth=120)
        self.tree.tag_configure("folder", font=FB)
        self.tree.tag_configure("top", font=(FONT, 10, "bold"), foreground=ACCENT)
        self.tree.tag_configure("keep", foreground=ORANGE)
        self.tree.tag_configure("off", foreground="#a3a6b8")
        sb = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Button-1>", self.on_tree_click, add=True)
        self.tree.bind("<space>", lambda e: self.toggle_selected())
        self.tree.bind("<Double-1>", self.on_double)
        self.tree.bind("<Button-3>", self.on_right_click)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.show_details())
        self.tree.bind("<<TreeviewOpen>>", lambda e: self._remember_open())
        self.tree.bind("<<TreeviewClose>>", lambda e: self.root.after(1, self._remember_open))
        pw.add(left, weight=3)

        # dettagli
        right = tk.Frame(pw, bg=CARD, highlightbackground=BORDER, highlightthickness=0)
        inner = tk.Frame(right, bg=CARD)
        inner.pack(fill="both", expand=True, padx=18, pady=16)
        self.d_title = tk.Label(inner, text="Seleziona un elemento", bg=CARD, fg=TEXT, font=(FONT, 13, "bold"),
                                anchor="w", justify="left", wraplength=360)
        self.d_title.pack(fill="x")
        self.d_meta = tk.Label(inner, text="Clicca su un file o su una cartella per vedere i dettagli e l'anteprima.",
                               bg=CARD, fg=MUTED, font=FS, anchor="w", justify="left", wraplength=360)
        self.d_meta.pack(fill="x", pady=(4, 10))

        self.d_move_frame = tk.Frame(inner, bg=CARD)
        tk.Label(self.d_move_frame, text="Andrà in:", bg=CARD, fg=TEXT, font=FB).pack(anchor="w")
        self.d_combo = ttk.Combobox(self.d_move_frame, width=40)
        self.d_combo.pack(fill="x", pady=(3, 2))
        self.d_combo.bind("<<ComboboxSelected>>", lambda e: self.change_category_from_combo())
        self.d_combo.bind("<Return>", lambda e: self.change_category_from_combo())
        self.d_hint = tk.Label(self.d_move_frame, text="Scegli dall'elenco o scrivi un nome nuovo (es. “Giochi/Strategici”) e premi Invio.",
                               bg=CARD, fg=MUTED, font=(FONT, 8), anchor="w", justify="left", wraplength=360)
        self.d_hint.pack(fill="x")
        self.d_final = tk.Label(self.d_move_frame, text="", bg=CARD, fg=MUTED, font=(FONT, 8), anchor="w",
                                justify="left", wraplength=360)
        self.d_final.pack(fill="x", pady=(4, 0))

        self.d_btns = tk.Frame(inner, bg=CARD)
        self.b_keep = ttk.Button(self.d_btns, text="📌 Lascia sul Desktop", command=self.toggle_keep)
        self.b_keep.pack(side="left")
        self.b_open = ttk.Button(self.d_btns, text="Apri", command=self.open_selected)
        self.b_open.pack(side="left", padx=4)
        self.b_reveal = ttk.Button(self.d_btns, text="Esplora file", command=self.reveal_selected)
        self.b_reveal.pack(side="left")
        self.b_rename = ttk.Button(self.d_btns, text="✏ Rinomina cartella", command=self.rename_folder)

        self.d_prev_lbl = tk.Label(inner, text="ANTEPRIMA", bg=CARD, fg=MUTED, font=(FONT, 8, "bold"), anchor="w")
        self.d_img = tk.Label(inner, bg="#f7f7fb")
        self.d_text = tk.Text(inner, height=12, wrap="word", bg="#f7f7fb", fg=TEXT, relief="flat",
                              font=(FONT, 9), padx=10, pady=8, borderwidth=0, highlightthickness=0)
        def rewrap(e):
            wl = max(220, e.width - 40)
            for lbl in (self.d_title, self.d_meta, self.d_final, self.d_hint):
                lbl.configure(wraplength=wl)
        right.bind("<Configure>", rewrap)
        pw.add(right, weight=2)

    # ---------------------------------------------------- scheda consigli
    def _build_tips(self):
        wrap = ttk.Frame(self.tab_tips, style="Card.TFrame")
        wrap.pack(fill="both", expand=True)
        self.tips_canvas = tk.Canvas(wrap, bg=CARD, highlightthickness=0)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.tips_canvas.yview)
        self.tips_inner = tk.Frame(self.tips_canvas, bg=CARD)
        self.tips_inner.bind("<Configure>", lambda e: self.tips_canvas.configure(scrollregion=self.tips_canvas.bbox("all")))
        win = self.tips_canvas.create_window((0, 0), window=self.tips_inner, anchor="nw")
        self.tips_canvas.bind("<Configure>", lambda e: self.tips_canvas.itemconfigure(win, width=e.width))
        self.tips_canvas.configure(yscrollcommand=sb.set)
        self.tips_canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def wheel(e):
            self.tips_canvas.yview_scroll(int(-e.delta / 120), "units")
        self.tips_canvas.bind("<Enter>", lambda e: self.tips_canvas.bind_all("<MouseWheel>", wheel))
        self.tips_canvas.bind("<Leave>", lambda e: self.tips_canvas.unbind_all("<MouseWheel>"))

    def render_tips(self):
        for w in self.tips_inner.winfo_children():
            w.destroy()
        colors = {2: RED, 1: ORANGE, 0: ACCENT}
        tk.Label(self.tips_inner, text="Cosa ti consiglio di fare", bg=CARD, fg=TEXT,
                 font=(FONT, 14, "bold")).pack(anchor="w", padx=22, pady=(18, 2))
        tk.Label(self.tips_inner, text="Nessuna azione parte da sola: decidi tu cosa applicare. "
                 "“Cestino” significa che puoi sempre recuperare i file dal Cestino di Windows.",
                 bg=CARD, fg=MUTED, font=FS).pack(anchor="w", padx=22, pady=(0, 10))
        for tip in self.tips:
            card = tk.Frame(self.tips_inner, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
            card.pack(fill="x", padx=20, pady=6)
            tk.Frame(card, bg=colors.get(tip.severity, ACCENT), width=5).pack(side="left", fill="y")
            tk.Label(card, text=tip.icon, bg=CARD, font=(FONT, 20), width=2).pack(side="left", padx=(12, 6), anchor="n", pady=8)
            body = tk.Frame(card, bg=CARD)
            body.pack(side="left", fill="both", expand=True, pady=10, padx=(0, 14))
            tk.Label(body, text=tip.title, bg=CARD, fg=TEXT, font=(FONT, 11, "bold"), anchor="w",
                     justify="left").pack(fill="x")
            tk.Label(body, text=tip.detail, bg=CARD, fg=MUTED, font=FS, anchor="w", justify="left",
                     wraplength=900).pack(fill="x", pady=(2, 4))
            if tip.items:
                names = [it.name for it in tip.items[:8]]
                more = f"   … e altri {len(tip.items) - 8}" if len(tip.items) > 8 else ""
                tk.Label(body, text="•  " + "\n•  ".join(names) + more, bg=CARD, fg=TEXT, font=FS,
                         anchor="w", justify="left").pack(fill="x")
            btns = tk.Frame(body, bg=CARD)
            btns.pack(fill="x", pady=(6, 0))
            if tip.action:
                ttk.Button(btns, text=tip.action_label, command=lambda t=tip: self.do_tip(t)).pack(side="left")
            shown = [it for it in tip.items if it in self.items]
            if shown:
                ttk.Button(btns, text="Mostra nell'anteprima",
                           command=lambda s=shown: self.show_in_tree(s)).pack(side="left", padx=6)
        self.tips_canvas.yview_moveto(0)

    # ---------------------------------------------------- scheda opzioni
    def _build_options(self):
        f = tk.Frame(self.tab_opts, bg=CARD)
        f.pack(fill="both", expand=True, padx=26, pady=20)
        self.v_single = tk.BooleanVar(value=self.cfg["single_folder"])
        self.v_docs = tk.BooleanVar(value=self.cfg["docs_to_documents"])
        self.v_public = tk.BooleanVar(value=self.cfg["include_public"])
        self.v_folders = tk.BooleanVar(value=self.cfg["include_folders"])
        self.v_read = tk.BooleanVar(value=self.cfg["read_contents"])
        self.v_old = tk.IntVar(value=self.cfg.get("old_months", 12))

        def section(title):
            tk.Label(f, text=title, bg=CARD, fg=TEXT, font=(FONT, 11, "bold")).pack(anchor="w", pady=(12, 4))

        def hint(text):
            tk.Label(f, text=text, bg=CARD, fg=MUTED, font=FS, justify="left", anchor="w").pack(anchor="w", padx=26)

        section("Dove creare le cartelle")
        ttk.Radiobutton(f, text="Direttamente sul Desktop (es. Desktop\\Giochi, Desktop\\Programmi…)",
                        variable=self.v_single, value=False, command=self.on_layout_option).pack(anchor="w")
        ttk.Radiobutton(f, text=f"Tutto dentro un'unica cartella “{core.SINGLE_FOLDER_NAME}” (Desktop quasi vuoto)",
                        variable=self.v_single, value=True, command=self.on_layout_option).pack(anchor="w")
        ttk.Checkbutton(f, text="Sposta i documenti nella cartella Documenti di Windows",
                        variable=self.v_docs, command=self.on_layout_option).pack(anchor="w", pady=(6, 0))
        hint(f"Documenti: {core.DOCUMENTS}")

        section("Cosa analizzare")
        ttk.Checkbutton(f, text="Leggi il contenuto dei documenti per capire di cosa parlano (PDF, Word, ODT, TXT…)",
                        variable=self.v_read, command=self.on_scan_option).pack(anchor="w")
        ttk.Checkbutton(f, text="Includi i collegamenti del Desktop di tutti gli utenti (Desktop pubblico)",
                        variable=self.v_public, command=self.on_scan_option).pack(anchor="w")
        ttk.Checkbutton(f, text="Includi anche le cartelle che hai sul Desktop",
                        variable=self.v_folders, command=self.on_scan_option).pack(anchor="w")
        hint("La cartella di questo programma non viene mai spostata.")
        row = tk.Frame(f, bg=CARD)
        row.pack(anchor="w", pady=(6, 0))
        tk.Label(row, text="Considera “vecchi” i file non modificati da", bg=CARD, font=F).pack(side="left")
        sp = ttk.Spinbox(row, from_=0, to=120, width=4, textvariable=self.v_old, command=self.on_scan_option)
        sp.pack(side="left", padx=6)
        sp.bind("<Return>", lambda e: self.on_scan_option())
        tk.Label(row, text="mesi  (0 = non segnalarli)", bg=CARD, font=F).pack(side="left")

        section("Le tue scelte")
        hint("Le scelte manuali (“Lascia sul Desktop”, cambio cartella) vengono ricordate per le prossime volte.")
        row2 = tk.Frame(f, bg=CARD)
        row2.pack(anchor="w", pady=6)
        ttk.Button(row2, text="Dimentica le mie scelte manuali", command=self.reset_choices).pack(side="left")
        ttk.Button(row2, text="Apri cartella del registro riordini", command=self.open_logs).pack(side="left", padx=6)
        lib = "pypdf ✓" if core.PdfReader else "pypdf non installato (lettura PDF base). Per leggere meglio i PDF:  pip install pypdf"
        hint(f"Lettura PDF: {lib}")

    # -------------------------------------------------------------- analisi
    def set_busy(self, busy: bool, text: str = ""):
        self.busy = busy
        state = "disabled" if busy else "normal"
        for b in (self.btn_apply, self.btn_undo, self.btn_rescan):
            b.configure(state=state)
        if busy:
            self.progress["value"] = 0
            self.progress.pack(side="right", padx=10, before=self.btn_undo) if not self.progress.winfo_ismapped() else None
            self.status.configure(text=text)
        else:
            self.progress.pack_forget()
            self.update_buttons()

    def analyze(self):
        if self.busy:
            return
        self.cfg.update(include_public=self.v_public.get(), include_folders=self.v_folders.get(),
                        read_contents=self.v_read.get(), old_months=self._old_months())
        self.lbl_path.configure(text=f"Cartella analizzata: {self.root_dir}")
        if self.root_dir.resolve() != core.DESKTOP.resolve():
            self.btn_desktop.pack(side="right", padx=4)
        else:
            self.btn_desktop.pack_forget()
        self.set_busy(True, "Analizzo i file… (leggo anche il contenuto dei documenti)")
        cfg, root_dir = dict(self.cfg), self.root_dir

        def work():
            try:
                res = core.analyze(root_dir, cfg, progress=lambda i, n, name: self.q.put(("progress", i, n, name)))
                self.q.put(("analyzed", res))
            except Exception as e:
                self.q.put(("error", f"Errore durante l'analisi: {e}"))
        threading.Thread(target=work, daemon=True).start()

    def _poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "progress":
                    _, i, n, name = msg
                    self.progress["maximum"] = max(n, 1)
                    self.progress["value"] = i
                    self.status.configure(text=f"{i}/{n} · {name}")
                elif kind == "analyzed":
                    self.items, self.tips = msg[1]
                    self.open_nodes = None
                    self.set_busy(False)
                    self.refresh_all()
                elif kind == "applied":
                    self.set_busy(False)
                    self.after_apply(*msg[1:])
                elif kind == "undone":
                    self.set_busy(False)
                    ok, skipped, when = msg[1]
                    messagebox.showinfo(core.APP_NAME, f"Annullato il riordino del {when.replace('T', ' alle ')}.\n\n"
                                        f"{ok} elementi rimessi al loro posto" + (f", {skipped} saltati." if skipped else "."))
                    self.analyze()
                elif kind == "error":
                    self.set_busy(False)
                    messagebox.showerror(core.APP_NAME, msg[1])
        except queue.Empty:
            pass
        self.root.after(80, self._poll)

    def _old_months(self) -> int:
        try:
            return max(0, int(self.v_old.get()))
        except (tk.TclError, ValueError):
            return 12

    # -------------------------------------------------------------- refresh
    def refresh_all(self):
        self.tips = core.build_tips(self.items, self.root_dir, self.cfg["include_folders"],
                                    self.cfg["include_public"], self.cfg.get("old_months", 12)) if self.items else self.tips
        self.cat_values = [KEEP_LABEL] + all_known_categories(self.items)
        self.d_combo.configure(values=self.cat_values)
        self.refresh_tree()
        self.render_tips()
        self.nb.tab(1, text=f"💡  Consigli ({sum(1 for t in self.tips if t.severity > 0)})")
        self.show_details()

    def dest_base_text(self) -> str:
        base = self.root_dir / core.SINGLE_FOLDER_NAME if self.cfg["single_folder"] else self.root_dir
        txt = f"Le cartelle verranno create in:  {base}"
        if self.cfg["docs_to_documents"]:
            txt += f"   ·   documenti in:  {core.DOCUMENTS}"
        return txt

    def update_stats(self):
        moving = [it for it in self.items if it.moves]
        loose_dirs = 0
        managed_existing = set()
        if self.root_dir.exists():
            managed = core.managed_top_folders()
            for p in self.root_dir.iterdir():
                if p.is_dir() and not core.is_hidden_or_system(p):
                    if p.name.lower() in managed:
                        managed_existing.add(p.name.lower())
                    elif not self.cfg["include_folders"]:
                        loose_dirs += 1
        tops = set(managed_existing)
        for it in moving:
            d = core.destination_dir(it, self.root_dir, self.cfg["single_folder"], self.cfg["docs_to_documents"])
            try:
                rel = d.relative_to(self.root_dir)
                tops.add(rel.parts[0].lower())
            except ValueError:
                pass  # finisce fuori dal Desktop (Documenti)
        before = len(self.items) + loose_dirs + len(managed_existing)
        after = len(self.items) - len(moving) + loose_dirs + len(tops)
        self.stat_labels["before"].configure(text=str(before))
        self.stat_labels["after"].configure(text=str(after))
        self.stat_labels["moves"].configure(text=str(len(moving)))
        self.stat_labels["tips"].configure(text=str(sum(1 for t in self.tips if t.severity > 0)))
        n_folders = len({it.final_category for it in moving})
        if not self.busy:
            self.status.configure(text=f"{len(moving)} elementi verranno spostati in {n_folders} cartelle · "
                                       f"{len(self.items) - len(moving)} restano dove sono.  "
                                       "Nulla viene cancellato e puoi sempre annullare.")
        self.btn_apply.configure(text=f"✨  Riordina ora ({len(moving)})")

    def update_buttons(self):
        if self.busy:
            return
        self.btn_undo.configure(state="normal" if core.last_log() else "disabled")
        self.btn_apply.configure(state="normal" if any(it.moves for it in self.items) else "disabled")
        needs_admin = any(it.public and it.moves for it in self.items) and not core.is_admin()
        if needs_admin and not self.btn_admin.winfo_ismapped():
            self.btn_admin.pack(side="right", padx=4, before=self.btn_undo)
        elif not needs_admin:
            self.btn_admin.pack_forget()

    def _remember_open(self):
        self.open_nodes = {iid for iid in self._all_nodes() if iid.startswith("c:") and self.tree.item(iid, "open")}

    def _all_nodes(self, parent=""):
        for iid in self.tree.get_children(parent):
            yield iid
            yield from self._all_nodes(iid)

    def refresh_tree(self):
        sel = self.tree.selection()
        y = self.tree.yview()[0]
        if self.tree.get_children():
            self._remember_open()
        self.tree.delete(*self.tree.get_children())
        self.lbl_dest.configure(text=self.dest_base_text())
        flt = self.search.get().strip().lower()
        by_cat = defaultdict(list)
        for idx, it in enumerate(self.items):
            if flt and flt not in it.name.lower() and flt not in it.final_category.lower():
                continue
            by_cat[it.final_category or "Altro"].append(idx)

        def top_key(cat):
            if cat == core.KEEP:
                return (-1, "")
            top = cat.split("/")[0]
            return (TOP_ORDER.index(top) if top in TOP_ORDER else 50, cat.lower())

        def ensure(path: str) -> str:
            iid = "c:" + path
            if self.tree.exists(iid):
                return iid
            parent = ensure(path.rsplit("/", 1)[0]) if "/" in path else ""
            name = path.rsplit("/", 1)[-1]
            if path == core.KEEP:
                text, tags = KEEP_LABEL, ("top", "keep")
            elif not parent:
                text, tags = f"{core.TOP_ICONS.get(name, '📁')}  {name}", ("top",)
            else:
                text, tags = f"📁  {name}", ("folder",)
            is_open = (self.open_nodes is None and not parent) or bool(flt) or \
                      (self.open_nodes is not None and iid in self.open_nodes)
            self.tree.insert(parent, "end", iid=iid, text=text, open=is_open, tags=tags)
            return iid

        for cat in sorted(by_cat, key=top_key):
            node = ensure(cat)
            for idx in sorted(by_cat[cat], key=lambda i: self.items[i].name.lower()):
                it = self.items[idx]
                tags = ()
                if cat == core.KEEP:
                    tags = ("keep",)
                elif not it.selected:
                    tags = ("off",)
                size = "" if it.is_dir or it.ext in (".lnk", ".url") else core.human_size(it.size)
                kind = it.kind + (" (pubblico)" if it.public else "")
                mark = "–" if cat == core.KEEP else (ON if it.selected else OFF)
                self.tree.insert(node, "end", iid=f"i:{idx}", text=f"{item_icon(it)}  {it.name}",
                                 values=(mark, kind, size, it.reason), tags=tags)
        # conteggi e caselle delle cartelle
        for iid in list(self._all_nodes()):
            if iid.startswith("c:"):
                leaves = self._leaves(iid)
                n_on = sum(1 for i in leaves if self.items[i].moves)
                if iid == "c:" + core.KEEP:
                    mark = "–"
                else:
                    mark = ON if n_on == len(leaves) else OFF if n_on == 0 else MIXED
                self.tree.item(iid, values=(mark, f"{len(leaves)} elemento" if len(leaves) == 1 else f"{len(leaves)} elementi", "", ""))
        for s in sel:
            if self.tree.exists(s):
                self.tree.selection_add(s)
        self.tree.yview_moveto(y)
        self.update_stats()
        self.update_buttons()

    def _leaves(self, iid) -> list[int]:
        if iid.startswith("i:"):
            return [int(iid[2:])]
        out = []
        for c in self.tree.get_children(iid):
            out.extend(self._leaves(c))
        return out

    # -------------------------------------------------------------- interazioni albero
    def on_tree_click(self, e):
        iid = self.tree.identify_row(e.y)
        if iid and self.tree.identify_column(e.x) == "#1":
            self.toggle([iid])
            return "break"

    def on_double(self, e):
        iid = self.tree.identify_row(e.y)
        if iid.startswith("i:") and self.tree.identify_column(e.x) != "#1":
            self.open_selected()
            return "break"

    def toggle_selected(self):
        self.toggle(list(self.tree.selection()))
        return "break"

    def toggle(self, iids):
        idxs = [i for iid in iids for i in self._leaves(iid)]
        idxs = [i for i in idxs if self.items[i].final_category != core.KEEP]
        if not idxs:
            return
        new = not all(self.items[i].selected for i in idxs)
        for i in idxs:
            self.items[i].selected = new
        self.refresh_tree()

    def set_all(self, value: bool):
        for it in self.items:
            it.selected = value
        self.refresh_tree()

    def expand_all(self, open_: bool):
        for iid in self._all_nodes():
            if iid.startswith("c:"):
                self.tree.item(iid, open=open_)
        self._remember_open()

    def selected_items(self) -> list[core.Item]:
        idxs = []
        for iid in self.tree.selection():
            idxs.extend(self._leaves(iid))
        return [self.items[i] for i in dict.fromkeys(idxs)]

    def show_in_tree(self, items):
        self.nb.select(0)
        self.search.set("")
        ids = [f"i:{self.items.index(it)}" for it in items if it in self.items]
        for iid in ids:
            parent = self.tree.parent(iid)
            while parent:
                self.tree.item(parent, open=True)
                parent = self.tree.parent(parent)
        self.tree.selection_set(ids)
        if ids:
            self.tree.see(ids[0])
        self._remember_open()

    def on_right_click(self, e):
        iid = self.tree.identify_row(e.y)
        if not iid:
            return
        if iid not in self.tree.selection():
            self.tree.selection_set(iid)
        items = self.selected_items()
        m = tk.Menu(self.root, tearoff=0, font=F)
        m.add_command(label="Includi / escludi dal riordino   (Spazio)", command=self.toggle_selected)
        m.add_command(label="📌 Lascia sul Desktop / togli", command=self.toggle_keep)
        sub = tk.Menu(m, tearoff=0, font=F)
        by_top = defaultdict(list)
        for c in all_known_categories(self.items):
            by_top[c.split("/")[0]].append(c)
        for top in sorted(by_top, key=lambda t: TOP_ORDER.index(t) if t in TOP_ORDER else 50):
            cats = by_top[top]
            if len(cats) == 1:
                sub.add_command(label=f"{core.TOP_ICONS.get(top, '📁')} {cats[0]}",
                                command=lambda c=cats[0]: self.set_category(items, c))
            else:
                s2 = tk.Menu(sub, tearoff=0, font=F)
                for c in cats:
                    s2.add_command(label=c, command=lambda c=c: self.set_category(items, c))
                sub.add_cascade(label=f"{core.TOP_ICONS.get(top, '📁')} {top}", menu=s2)
        sub.add_separator()
        sub.add_command(label="Nuova cartella…", command=lambda: self.new_category(items))
        m.add_cascade(label="Sposta in", menu=sub)
        if iid.startswith("c:") and iid != "c:" + core.KEEP:
            m.add_command(label="✏ Rinomina questa cartella…", command=self.rename_folder)
        m.add_separator()
        if len(items) == 1:
            m.add_command(label="Apri", command=self.open_selected)
            m.add_command(label="Mostra in Esplora file", command=self.reveal_selected)
        m.add_command(label="🗑 Sposta nel Cestino…", command=lambda: self.trash(items))
        m.tk_popup(e.x_root, e.y_root)

    # -------------------------------------------------------------- modifiche categoria
    def set_category(self, items, cat: str | None):
        """cat: categoria, core.KEEP, oppure None per tornare alla proposta automatica."""
        keep = set(self.cfg.get("keep", []))
        ov = self.cfg.setdefault("overrides", {})
        for it in items:
            key = str(it.path)
            keep.discard(key)
            ov.pop(key, None)
            if cat is None or cat == it.category:
                it.override = None
            else:
                it.override = cat
                if cat == core.KEEP:
                    keep.add(key)
                else:
                    ov[key] = cat
                    it.selected = True
        self.cfg["keep"] = sorted(keep)
        core.save_config(self.cfg)
        self.refresh_all()
        ids = [f"i:{self.items.index(it)}" for it in items if it in self.items]
        if ids:
            self.tree.selection_set(ids)
            self.tree.see(ids[0])

    def toggle_keep(self):
        items = self.selected_items()
        if not items:
            return
        if all(it.final_category == core.KEEP for it in items):
            self.set_category(items, None)
        else:
            self.set_category(items, core.KEEP)

    def change_category_from_combo(self):
        items = self.selected_items()
        val = self.d_combo.get().strip().strip("/")
        if not items or not val:
            return
        cat = core.KEEP if val == KEEP_LABEL else "/".join(core.safe_folder_name(p) for p in val.split("/") if p.strip())
        if cat:
            self.set_category(items, cat)

    def new_category(self, items):
        name = simpledialog.askstring(core.APP_NAME, "Nome della nuova cartella\n(usa / per le sottocartelle, es. Giochi/Strategici):",
                                      parent=self.root)
        if name and name.strip("/ "):
            self.set_category(items, "/".join(core.safe_folder_name(p) for p in name.split("/") if p.strip()))

    def rename_folder(self):
        sel = [s for s in self.tree.selection() if s.startswith("c:")]
        if not sel or sel[0] == "c:" + core.KEEP:
            return
        old = sel[0][2:]
        new = simpledialog.askstring(core.APP_NAME, f"Nuovo nome per “{old}”:", initialvalue=old, parent=self.root)
        if not new or not new.strip("/ ") or new == old:
            return
        new = "/".join(core.safe_folder_name(p) for p in new.split("/") if p.strip())
        ov = self.cfg.setdefault("overrides", {})
        for it in self.items:
            c = it.final_category
            if c == old or c.startswith(old + "/"):
                it.override = new + c[len(old):]
                ov[str(it.path)] = it.override
        core.save_config(self.cfg)
        self.open_nodes = (self.open_nodes or set()) | {"c:" + new}
        self.refresh_all()

    def reset_choices(self):
        if not messagebox.askyesno(core.APP_NAME, "Dimentico tutte le scelte manuali (elementi fissati sul Desktop e "
                                   "cartelle cambiate a mano)?"):
            return
        self.cfg["keep"], self.cfg["overrides"] = [], {}
        core.save_config(self.cfg)
        for it in self.items:
            it.override = None
        self.refresh_all()

    # -------------------------------------------------------------- dettagli
    def show_details(self):
        sel = self.tree.selection()
        for w in (self.d_move_frame, self.d_btns, self.d_prev_lbl, self.d_img, self.d_text, self.b_rename):
            w.pack_forget()
        self._img = None
        if not sel:
            self.d_title.configure(text="Seleziona un elemento")
            self.d_meta.configure(text="Clicca su un file o su una cartella per vedere i dettagli e l'anteprima.\n\n"
                                       "Suggerimenti:\n• clic sulla colonna “Sposta” (o Spazio) per includere/escludere\n"
                                       "• tasto destro per spostare in un'altra cartella o lasciarlo sul Desktop\n"
                                       "• doppio clic per aprire il file")
            return
        if len(sel) > 1 or sel[0].startswith("c:"):
            items = self.selected_items()
            if len(sel) == 1:
                cat = sel[0][2:]
                title = KEEP_LABEL if cat == core.KEEP else cat.replace("/", "  ›  ")
                where = "" if cat == core.KEEP else "\nPercorso: " + str(self._dest_for_cat(cat))
            else:
                title, where = f"{len(items)} elementi selezionati", ""
            tot = sum(it.size for it in items)
            self.d_title.configure(text=title)
            self.d_meta.configure(text=f"{len(items)} elementi · {core.human_size(tot)}{where}")
            self.d_combo.set("")
            self.d_final.configure(text="Cambiando la cartella qui sotto sposti tutti gli elementi selezionati.")
            self.d_move_frame.pack(fill="x", pady=(0, 10))
            self.d_btns.pack(fill="x", pady=(0, 12))
            self.b_open.configure(state="disabled")
            self.b_reveal.configure(state="disabled")
            if len(sel) == 1 and sel[0] != "c:" + core.KEEP:
                self.b_rename.pack(side="left", padx=4)
            self.b_keep.configure(text="📌 Lascia sul Desktop")
            names = "\n".join(f"{item_icon(it)}  {it.name}" for it in items[:40])
            self._show_text(names + (f"\n… e altri {len(items) - 40}" if len(items) > 40 else ""))
            return

        it = self.items[int(sel[0][2:])]
        self.b_open.configure(state="normal")
        self.b_reveal.configure(state="normal")
        self.d_title.configure(text=f"{item_icon(it)}  {it.name}")
        meta = [it.kind + ("  ·  Desktop pubblico" if it.public else "")]
        if not it.is_dir and it.ext not in (".lnk", ".url"):
            meta.append(f"Dimensione: {core.human_size(it.size)}")
        if it.mtime:
            meta.append("Modificato: " + datetime.fromtimestamp(it.mtime).strftime("%d/%m/%Y %H:%M"))
        meta.append(f"Perché: {it.reason}" + (" (scelta tua)" if it.override is not None else ""))
        if it.note:
            meta.append(f"Nota: {it.note}")
        self.d_meta.configure(text="\n".join(meta))
        self.d_combo.set(KEEP_LABEL if it.final_category == core.KEEP else it.final_category)
        if it.final_category == core.KEEP:
            self.d_final.configure(text="Resterà sul Desktop.")
        elif not it.selected:
            self.d_final.configure(text="Escluso dal riordino (clic su ☐ per includerlo).")
        else:
            dest = core.destination_dir(it, self.root_dir, self.cfg["single_folder"], self.cfg["docs_to_documents"])
            self.d_final.configure(text=f"→ {dest / it.name}")
        self.d_move_frame.pack(fill="x", pady=(0, 10))
        self.b_keep.configure(text="↩ Rimetti nel riordino" if it.final_category == core.KEEP else "📌 Lascia sul Desktop")
        self.d_btns.pack(fill="x", pady=(0, 12))
        self._preview(it)

    def _dest_for_cat(self, cat):
        fake = core.Item(path=Path("x"), is_dir=False, size=0, mtime=0, category=cat)
        return core.destination_dir(fake, self.root_dir, self.cfg["single_folder"], self.cfg["docs_to_documents"])

    def _show_text(self, text):
        self.d_prev_lbl.pack(fill="x")
        self.d_text.configure(state="normal")
        self.d_text.delete("1.0", "end")
        self.d_text.insert("1.0", text)
        self.d_text.configure(state="disabled")
        self.d_text.pack(fill="both", expand=True, pady=(4, 0))

    def _preview(self, it: core.Item):
        if it.ext in (".png", ".gif", ".jpg", ".jpeg", ".bmp", ".webp") and it.size < 40 * 1024 ** 2:
            try:
                if Image is not None:
                    im = Image.open(it.path)
                    im.thumbnail((380, 300))
                    self._img = ImageTk.PhotoImage(im)
                elif it.ext in (".png", ".gif"):
                    img = tk.PhotoImage(file=str(it.path))
                    f = max(1, -(-img.width() // 380), -(-img.height() // 300))
                    self._img = img.subsample(f, f)
                if self._img is not None:
                    self.d_prev_lbl.pack(fill="x")
                    self.d_img.configure(image=self._img)
                    self.d_img.pack(fill="x", pady=(4, 0), ipady=6)
                    return
            except Exception:
                pass
        if it.ext in (".lnk", ".url"):
            lines = [f"Apre:  {it.target or '(destinazione non leggibile)'}"]
            if it.args.strip():
                lines.append(f"Argomenti:  {it.args.strip()}")
            if core.shortcut_is_broken(it):
                lines.append("\n⚠ La destinazione non esiste più: questo collegamento è rotto.")
            self._show_text("\n".join(lines))
            return
        if it.is_dir:
            n, size = core.folder_stats(it.path)
            try:
                names = sorted(p.name for p in it.path.iterdir())[:30]
            except OSError:
                names = []
            self._show_text(f"{n} file · {core.human_size(size)}\n\nContenuto:\n" + "\n".join(names))
            return
        txt = core.preview_text(it)
        if txt.strip():
            self._show_text(txt)
        elif it.ext in core.EXT_GROUPS["Immagini"]:
            self._show_text("Anteprima non disponibile per questo formato (installa Pillow:  pip install pillow).")
        else:
            self._show_text("Nessuna anteprima disponibile. Usa “Apri” per vederlo.")

    # -------------------------------------------------------------- azioni file
    def open_selected(self):
        items = self.selected_items()
        if len(items) == 1:
            try:
                os.startfile(str(items[0].path))
            except OSError as e:
                messagebox.showerror(core.APP_NAME, f"Non riesco ad aprirlo: {e}")

    def reveal_selected(self):
        items = self.selected_items()
        if len(items) == 1:
            subprocess.Popen(["explorer", "/select,", str(items[0].path)])

    def trash(self, items):
        items = [it for it in items if it.path.exists()]
        if not items:
            return
        names = "\n".join(f"•  {it.name}" for it in items[:15]) + (f"\n… e altri {len(items) - 15}" if len(items) > 15 else "")
        if not messagebox.askyesno(core.APP_NAME, f"Spostare nel Cestino questi {len(items)} elementi?\n\n{names}\n\n"
                                   "Potrai recuperarli dal Cestino di Windows."):
            return
        ok, errors = core.send_to_recycle_bin([it.path for it in items])
        msg = f"{ok} elementi spostati nel Cestino."
        if errors:
            msg += "\n\nNon spostati:\n" + "\n".join(errors[:10])
            if any(it.public for it in items) and not core.is_admin():
                msg += "\n\nAlcuni sono nel Desktop pubblico: riapri il programma come amministratore."
        messagebox.showinfo(core.APP_NAME, msg)
        self.analyze()

    def do_tip(self, tip: core.Tip):
        if tip.action == "trash":
            self.trash(tip.items)
        elif tip.action == "archive":
            for it in tip.items:
                year = datetime.fromtimestamp(it.mtime).year
                it.override = f"Archivio vecchi file/{year}"
                it.selected = True
                self.cfg.setdefault("overrides", {})[str(it.path)] = it.override
            core.save_config(self.cfg)
            self.refresh_all()
            self.show_in_tree(tip.items)
            messagebox.showinfo(core.APP_NAME, "Fatto: nell'anteprima ora li trovi in “Archivio vecchi file”.\n"
                                               "Premi “Riordina ora” per spostarli davvero.")
        elif tip.action and tip.action.startswith("option:"):
            if tip.action == "option:include_folders":
                self.v_folders.set(True)
                self.on_scan_option()

    # -------------------------------------------------------------- opzioni
    def on_layout_option(self):
        self.cfg.update(single_folder=self.v_single.get(), docs_to_documents=self.v_docs.get())
        core.save_config(self.cfg)
        self.refresh_tree()
        self.show_details()

    def on_scan_option(self):
        self.cfg.update(include_public=self.v_public.get(), include_folders=self.v_folders.get(),
                        read_contents=self.v_read.get(), old_months=self._old_months())
        core.save_config(self.cfg)
        self.analyze()

    def choose_folder(self):
        d = filedialog.askdirectory(initialdir=str(self.root_dir), title="Scegli la cartella da riordinare")
        if d:
            self.root_dir = Path(d)
            self.cfg["root"] = "" if self.root_dir.resolve() == core.DESKTOP.resolve() else str(self.root_dir)
            core.save_config(self.cfg)
            self.analyze()

    def back_to_desktop(self):
        self.root_dir = core.DESKTOP
        self.cfg["root"] = ""
        core.save_config(self.cfg)
        self.analyze()

    def open_logs(self):
        core.LOG_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(str(core.LOG_DIR))

    # -------------------------------------------------------------- riordino
    def apply(self):
        moving = [it for it in self.items if it.moves]
        if not moving:
            return
        groups = defaultdict(int)
        for it in moving:
            groups[it.final_category] += 1
        lines = "\n".join(f"   {core.TOP_ICONS.get(c.split('/')[0], '📁')} {c.replace('/', ' › ')}  ({n})"
                          for c, n in sorted(groups.items())[:18])
        if len(groups) > 18:
            lines += f"\n   … e altre {len(groups) - 18} cartelle"
        warn = ""
        pub = sum(1 for it in moving if it.public)
        if pub and not core.is_admin():
            warn = (f"\n\n⚠ {pub} collegamenti sono nel Desktop pubblico: senza permessi di amministratore "
                    "Windows potrebbe non lasciarli spostare (gli altri verranno spostati comunque).")
        if not messagebox.askyesno(core.APP_NAME, f"Sposto {len(moving)} elementi in queste cartelle:\n\n{lines}\n\n"
                                   f"Non cancello nulla e puoi annullare in qualsiasi momento.{warn}\n\nProcedo?"):
            return
        self.set_busy(True, "Sto riordinando…")
        root_dir, single, docs = self.root_dir, self.cfg["single_folder"], self.cfg["docs_to_documents"]

        def work():
            try:
                res = core.apply_moves(self.items, root_dir, single, docs,
                                       progress=lambda i, n, name: self.q.put(("progress", i, n, name)))
                self.q.put(("applied", *res))
            except Exception as e:
                self.q.put(("error", f"Errore durante il riordino: {e}"))
        threading.Thread(target=work, daemon=True).start()

    def after_apply(self, moves, errors, log):
        folders = {str(Path(m["a"]).parent) for m in moves}
        msg = f"🎉 Fatto! {len(moves)} elementi spostati in {len(folders)} cartelle."
        if errors:
            msg += f"\n\n{len(errors)} non spostati:\n" + "\n".join(f"•  {n} – {e}" for n, e in errors[:12])
            if len(errors) > 12:
                msg += f"\n… e altri {len(errors) - 12}"
            if any("amministratore" in e for _, e in errors):
                msg += "\n\nPer quelli del Desktop pubblico usa “Riapri come amministratore”."
            else:
                msg += "\n\nDi solito succede se il file è aperto in un altro programma."
        msg += "\n\nSe qualcosa non ti piace: “Annulla ultimo riordino”."
        messagebox.showinfo(core.APP_NAME, msg)
        self.analyze()

    def undo(self):
        log = core.last_log()
        if not log:
            return
        if not messagebox.askyesno(core.APP_NAME, "Rimetto tutti i file dell'ultimo riordino dove erano prima?"):
            return
        self.set_busy(True, "Annullo l'ultimo riordino…")
        threading.Thread(target=lambda: self.q.put(("undone", core.undo_last())), daemon=True).start()

    def relaunch_admin(self):
        exe = Path(sys.executable)
        if getattr(sys, "frozen", False):  # versione .exe
            params = ""
            os.environ["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        else:
            pyw = exe.with_name("pythonw.exe")
            exe = pyw if pyw.exists() else exe
            params = f'"{Path(__file__).resolve().with_name("riordina_desktop.pyw")}"'
        r = ctypes.windll.shell32.ShellExecuteW(None, "runas", str(exe), params, None, 1)
        if r > 32:
            self.on_close()

    def on_close(self):
        core.save_config(self.cfg)
        self.root.destroy()


def main():
    if os.name == "nt":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("RiordinaDesktop")
        except Exception:
            pass
    root = tk.Tk()
    icon = Path(__file__).resolve().parent / "riordina.ico"
    if icon.exists():
        try:
            root.iconbitmap(default=str(icon))
        except tk.TclError:
            pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
