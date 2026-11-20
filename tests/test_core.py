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

        # torna indietro di piu' passi: istantanea -> due riordini -> ritorno all'istantanea
        core.save_snapshot(base, "prova")
        snap = core.list_points()[-1]
        assert snap.kind == "istantanea" and "Luca.txt" in snap.before
        for names in (["Luca.txt"], ["setup_app.exe", "vuoto.txt"]):
            its, _ = core.analyze(base, dict(core.DEFAULT_CONFIG, include_public=False))
            for it in its:
                it.selected = it.name in names
            core.apply_moves(its, base, single_folder=False, docs_to_documents=False)
        assert not (base / "Luca.txt").exists() and not (base / "vuoto.txt").exists()
        assert len(core.to_undo_for(snap)) == 2
        res = core.restore_to(snap)
        assert res["undone"] == 2 and res["ok"] == 3 and not res["missing"], res
        assert sorted(p.relative_to(base).as_posix() for p in base.rglob("*")) == before
        assert core.to_undo_for(snap) == []
        print(f"OK: {len(items)} elementi classificati, {len(moves)} spostati e rimessi a posto; "
              f"ritorno a un istante con 2 riordini annullati.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
