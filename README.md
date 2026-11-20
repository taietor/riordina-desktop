# Riordina Desktop

Programma Windows con finestra per mettere in ordine il Desktop (o qualsiasi cartella) in cartelle
ben organizzate, con anteprima, consigli e annullamento. Tutto in locale, solo libreria standard di Python.

![icona](riordina.ico)

## Avvio
- Collegamento **Riordina Desktop** sul Desktop o nel menu Start.
- Oppure: `pythonw riordina_desktop.pyw`
- Per (ri)creare icona e collegamenti: `python strumenti/collegamento.py`
  (`--rimuovi` per toglierli). Va rifatto se sposti la cartella del progetto.

## Come funziona
1. All'avvio analizza il Desktop (anche quello "pubblico" di tutti gli utenti) e propone una struttura:
   🎮 Giochi, 🧩 Programmi › Sviluppo / Internet / Utilità…, 📄 Documenti › Lavoro / Lettere / Salute…,
   🌐 Siti e App Web, 🖼 Immagini, 📦 Installer, 💻 Script e Codice…
2. **Anteprima**: albero della nuova struttura con caselle di spunta; clic su un elemento per vedere
   dettagli e anteprima (testo, immagini, destinazione dei collegamenti). Tasto destro per cambiare cartella,
   lasciarlo sul Desktop 📌 o rinominare una cartella. Le scelte vengono ricordate.
3. **Consigli**: collegamenti doppi o rotti, stesso gioco su due piattaforme, zip già estratti,
   installer, file vuoti, vecchi o molto grandi, cartelle sparse.
4. **Riordina ora** sposta i file; **Annulla ultimo riordino** rimette tutto com'era.

Come classifica:
- collegamenti `.lnk` letti direttamente (eseguibile + argomenti), `.url` dallo schema (`steam://`, `uplay://`…);
- programmi riconosciuti per nome/eseguibile (`APP_RULES` in `riordina_core.py`);
- documenti letti nel contenuto (PDF, DOCX, ODT, PPTX, XLSX, TXT…) e classificati per parole chiave;
  le lettere personali si riconoscono dal saluto iniziale ("Marco, …").

## Sicurezza
- Non cancella mai nulla: sposta soltanto. Il Cestino si usa solo se lo scegli tu da un consiglio.
- Le cartelle non vengono spostate a meno di attivarlo nelle Opzioni; la cartella del programma mai.
- I collegamenti del Desktop pubblico richiedono "Riapri come amministratore".
- Registro dei riordini e impostazioni: `%LOCALAPPDATA%\RiordinaDesktop`.

## Struttura
| File | Cosa fa |
|---|---|
| `riordina_desktop.pyw` | interfaccia grafica (tkinter) |
| `riordina_core.py` | motore: scansione, regole, consigli, spostamenti, annulla. `python riordina_core.py` stampa solo l'anteprima |
| `strumenti/collegamento.py` | disegna `riordina.ico` e crea i collegamenti Desktop/Start |
| `tests/test_core.py` | prova spostamento + annullamento su una cartella temporanea |

Facoltativi: `pip install pypdf` (legge meglio i PDF), `pip install pillow` (anteprima JPG/WEBP).

## Test
```
python tests/test_core.py
```
