"""Prova il motore su una cartella temporanea: classificazione, spostamento e annullamento.

    python tests/test_core.py
"""
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import riordina_core as core  # noqa: E402


def make_fake_desktop(base: Path) -> None:
    (base / "Fattura luglio.txt").write_text("Fattura n.12 importo totale IVA imponibile", encoding="utf-8")
    (base / "Luca.txt").write_text("Luca, grazie di tutto!", encoding="utf-8")
    (base / "vuoto.txt").write_text("")
    (base / "Screenshot 2026.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (base / "setup_app.exe").write_bytes(b"MZ")
    (base / "Gioco.url").write_text("[InternetShortcut]\nURL=steam://rungameid/1\n")
    (base / "Gioco copia.url").write_text("[InternetShortcut]\nURL=steam://rungameid/1\n")
    (base / "Sito.url").write_text("[InternetShortcut]\nURL=https://example.com\n")
    (base / "progetto").mkdir()
    (base / "progetto.zip").write_bytes(b"PK")
    (base / "Documenti").mkdir()
    (base / "Documenti" / "Fattura luglio.txt").write_text("gia' presente")


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="riordina_test_"))
    try:
        base = tmp / "desktop"
        base.mkdir()
        core.LOG_DIR = tmp / "registro"  # non toccare il registro vero
        make_fake_desktop(base)

        items, tips = core.analyze(base, dict(core.DEFAULT_CONFIG, include_public=False))
        cat = {it.name: it.final_category for it in items}
        assert cat["Luca.txt"] == "Documenti/Lettere e Messaggi", cat
        assert cat["Fattura luglio.txt"] == "Documenti/Fatture e Pagamenti", cat
        assert cat["Screenshot 2026.png"] == "Immagini/Screenshot", cat
        assert cat["Gioco.url"] == "Giochi", cat
        assert "Documenti" not in cat, "le cartelle già ordinate non vanno riproposte"
        titles = " | ".join(t.title for t in tips)
        assert "Collegamento doppio" in titles and "Archivi già estratti" in titles, titles

        next(it for it in items if it.name == "Sito.url").override = core.KEEP
        before = sorted(p.relative_to(base).as_posix() for p in base.rglob("*"))
        moves, errors, log = core.apply_moves(items, base, single_folder=False, docs_to_documents=False)
        assert not errors and log, errors
        assert (base / "Documenti" / "Fatture e Pagamenti" / "Fattura luglio.txt").exists()
        assert (base / "Documenti" / "Fattura luglio.txt").read_text() == "gia' presente"
        assert (base / "Sito.url").exists(), "gli elementi fissati restano sul Desktop"

        ok, skipped, _ = core.undo_last()
        after = sorted(p.relative_to(base).as_posix() for p in base.rglob("*"))
        assert (ok, skipped) == (len(moves), 0)
        assert before == after, set(before) ^ set(after)
        assert core.last_log() is None
        print(f"OK: {len(items)} elementi classificati, {len(moves)} spostati e rimessi a posto.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
