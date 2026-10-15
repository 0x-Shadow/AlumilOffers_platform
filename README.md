# AlumilOffers_platform

Desktop app for aluminum workshops (Windows): quotes with materials,
a visual designs catalog (windows, doors, dimensions), customers,
and professional PDF export with VAT — everything offline in one app.

🌐 **Landing page:** [`docs/index.html`](docs/index.html) — self-contained,
no dependencies (publish it with GitHub Pages: Settings → Pages → `main` → `/docs`).

> 🇬🇷 Σύντομα ελληνικά: οδηγίες βήμα-βήμα για Windows στο [docs/INSTALL_EL.md](docs/INSTALL_EL.md).

## Features

- **Dashboard** — monthly/yearly revenue (incl. VAT), quotes per month,
  average quote, last-6-months revenue bars, quick actions, searchable history.
- **New quote on one screen** — free-text lines (description | width | height |
  qty | price), live totals, optional design picker per line, one big Save+PDF button.
- **Designs catalog** — code, name, category, dimensions, photo, per-design
  bill of materials; bulk import a whole folder of photos at once.
- **Materials & customers** — simple lists, auto-registration from quotes.
- **Company profile + logo** — shown in the app and embedded in every PDF.
- **Professional PDF** — logo, company info, materials table, designs with
  images/dimensions/materials, net value / VAT / total with VAT, footer on every page.
- **100% local** — SQLite database next to the app, no cloud, no accounts.

## Requirements

- Windows 10/11
- Python 3.11+ (only for running from source; the `.exe` needs nothing)

## Install (recommended)

Download `Setup_AluminaOffers_X.Y.Z.exe` from
[Releases](https://github.com/0x-Shadow/AlumilOffers_platform/releases),
run it and follow the wizard (license, folder, shortcuts, uninstaller).
No Python needed.

## Quick start (from source)

```bat
pip install -r requirements.txt
python app.py
```

Or double-click `RUN_APP.bat`.

## Step-by-step Windows installation

Full guide (Greek): [docs/INSTALL_EL.md](docs/INSTALL_EL.md).

1. Install Python from [python.org](https://www.python.org/downloads/)
   (check **"Add python.exe to PATH"** during setup).
2. Download or `git clone` this repository.
3. Open a terminal in the project folder and run:
   `pip install -r requirements.txt`
4. Run `python app.py` (or `RUN_APP.bat`).

## Build the .exe

```bat
pip install pyinstaller
python -m PyInstaller --onefile --windowed --name AluminaOffers app.py
```

The executable lands in `dist/`. Keep it in the project folder —
the database (`alumina.db`), images (`Sxedia/`) and PDFs (`PDF_Prosfores/`)
live next to it. On first launch Windows SmartScreen may warn because the
binary is unsigned → *More info → Run anyway*.

## Project structure

```
AluminaOffers/
├── app.py              # the whole app (UI + SQLite + PDF)
├── requirements.txt
├── RUN_APP.bat         # source launcher for Windows
├── LICENSE             # MIT
├── docs/
│   ├── INSTALL_EL.md   # βήμα-βήμα εγκατάσταση (ελληνικά)
│   ├── TERMS_EL.md     # όροι χρήσης (ελληνικά, εμφανίζονται και στην εφαρμογή)
│   └── PRIVACY_EL.md   # απόρρητο (ελληνικά)
└── ...runtime files (git-ignored: alumina.db, logo.png, Sxedia/, PDF_Prosfores/)
```

## Data & privacy

All data stays on your machine (`alumina.db`, `Sxedia/`, `logo.png`).
Nothing is uploaded anywhere. See [docs/PRIVACY_EL.md](docs/PRIVACY_EL.md).

## License

MIT — see [LICENSE](LICENSE). The app also shows a short Greek
terms-of-use dialog on first launch (`docs/TERMS_EL.md`).
