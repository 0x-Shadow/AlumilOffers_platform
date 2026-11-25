# tools/ — one-off maintenance scripts

These scripts are **not** used by the application at runtime. They rebuild the
catalog content and are run manually from the project root with the app's
Python environment.

| Script | What it does | When to run |
|---|---|---|
| `catalog_data_part1..4.py` | Parsed product data (26 products) from the `Offers/` PDF scans | Edit when catalog data changes |
| `import_catalog.py` | Replaces the `designs` table with those 26 products and installs their drawings | After editing catalog data |
| `draw_catalog_images.py` | Redraws the CAD-style product elevations into `Sxedia/` | When product drawings change |
| `generate_test_pdf.py` | Renders a sample quote PDF (smoke test for the PDF engine) | After PDF changes |

Run them with the same interpreter that runs the app:

```bash
# Linux / macOS
.venv/bin/python tools/generate_test_pdf.py

# Windows
.venv\Scripts\python tools\generate_test_pdf.py
```

`import_catalog.py` writes to the same per-user database the app uses
(`%APPDATA%\Europa\europa.db` on Windows) and **replaces the entire
designs catalog** — back up the database first if it contains custom designs.
