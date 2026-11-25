# Europa

Desktop app for aluminum workshops (Windows): quotes with materials,
a visual designs catalog (windows, doors, dimensions), customers,
and professional PDF export with VAT — everything offline in one app.

🌐 **Landing page:** [`docs/index.html`](docs/index.html) — self-contained,
no dependencies (publish it with GitHub Pages: Settings → Pages → `main` → `/docs`).

> 🇬🇷 Σύντομα ελληνικά: οδηγίες βήμα-βήμα για Windows στο [docs/INSTALL_EL.md](docs/INSTALL_EL.md).

## Features

- **Dashboard** — monthly/yearly revenue (incl. VAT), quotes per month,
  average quote, last-6-months revenue bars, quick actions, searchable history.
- **Visual Design Picker (v1.2.0)** — quick-select from preset Alumil & Europa designs
  with CAD-style technical drawings, instant search (Greek accent-insensitive), and category filters.
- **New quote on one screen** — customizable lines (Design | Width | Height | Location |
  Qty | Price), live totals, a product-only offer discount (labor excluded) with automatic VAT recalculation,
  duplicate row (📋), detailed specs editor (⚙️), one big Save+PDF button.
- **Designs catalog** — code, name, category, dimensions, photo, series, RAL color, per-design
  bill of materials; built-in Alumil/Europa presets generator.
- **Materials & customers** — simple lists, auto-registration from quotes.
- **Company profile + logo** — shown in the app and embedded in every PDF.
- **Professional PDF (Reference Layout)** — logo, company info, CAD schematic elevations
  (sliding, casement opening triangles, roller shutter hatching, flyscreens), series / color / dimensions
  table, a priced offer summary with discount / net value / VAT / total with VAT, detailed model
  illustrations and specifications without repeated prices, footer on every page.
- **Automatic updates** — checks GitHub Releases on startup and installs a new
  version in one click (SHA-256 verified, silent upgrade, automatic restart).
- **100% local** — SQLite database in `%APPDATA%\Europa`, no cloud, no accounts.

## Requirements

- Windows 10/11
- Python 3.11+ (only for running from source; the `.exe` needs nothing)

## Install (recommended)

Download `Setup_Europa_X.Y.Z.exe` from
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
python -m PyInstaller --onefile --windowed --name Europa app.py
```

The executable lands in `dist/`. The database (`europa.db`), images (`Sxedia/`)
and PDFs (`PDF_Prosfores/`) live in the per-user data folder, not next to the exe
(see [Data & privacy](#data--privacy)). Releases are built by GitHub Actions from
the `v*` tag; the app version is read from `app.py` and baked into the installer.
On first launch Windows SmartScreen may warn because the binary is unsigned →
*More info → Run anyway*.

## Project structure

```
Europa/
├── app.py              # the whole app (UI + SQLite + PDF)
├── updater.py          # GitHub Releases update check + verified installer
├── requirements.txt
├── RUN_APP.bat         # source launcher for Windows
├── LICENSE             # MIT
├── Europa.spec         # PyInstaller build
├── installer.iss       # Inno Setup installer
├── tools/              # one-off catalog/test scripts (not used at runtime)
├── docs/
│   ├── INSTALL_EL.md   # βήμα-βήμα εγκατάσταση (ελληνικά)
│   ├── TERMS_EL.md     # όροι χρήσης (ελληνικά, εμφανίζονται και στην εφαρμογή)
│   └── PRIVACY_EL.md   # απόρρητο (ελληνικά)
└── ...local runtime files (git-ignored: europa.db, logo.png, Sxedia/, PDF_Prosfores/)
```

## Data & privacy

All data stays on your machine, in a per-user folder:

- **Windows:** `%APPDATA%\Europa\`
- **Linux:** `~/.local/share/Europa/`
- **macOS:** `~/Library/Application Support/Europa/`

It contains `europa.db`, `Sxedia/`, `PDF_Prosfores/` and `logo.png`. On first
launch, data from older versions (AluminaOffers folder or next to the exe) is copied there once;
the old files are left untouched. Because the folder is outside the install
directory, updating or uninstalling the app never deletes quotes. Back it up by
copying that folder. Set `EUROPA_DATA_DIR` to use a different location.
Nothing is uploaded anywhere. See [docs/PRIVACY_EL.md](docs/PRIVACY_EL.md).

## Updates

On startup (at most once every 24 h) the app asks the GitHub Releases API for the
latest version. If a newer one exists, a modern dialog offers **Ενημέρωση τώρα**
and the sidebar keeps a reminder card. The update downloads the official
installer, verifies its SHA-256 against the release's `SHA256SUMS.txt`, runs it
silently and restarts the app. Offline or rate-limited checks fail silently and
never block the app. Portable/source runs open the release page instead of
self-installing.

To preview the prompt without publishing a release, open **Settings → Ενημερώσεις →
Προεπισκόπηση**, or start the app with `EUROPA_FAKE_UPDATE=1`. It shows the real dialog and sidebar card, but nothing
is downloaded or installed. `EUROPA_NO_UPDATE_CHECK=1` disables the automatic
check entirely.

## License

MIT — see [LICENSE](LICENSE) (accepted during setup; Greek terms in [`docs/TERMS_EL.md`](docs/TERMS_EL.md)).
