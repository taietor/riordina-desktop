"""Avvio di Riordina Desktop senza finestra del terminale (doppio clic o collegamento)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from riordina_gui import main  # noqa: E402

main()
