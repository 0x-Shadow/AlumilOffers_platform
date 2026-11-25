#!/usr/bin/env python3
"""
Import all 26 catalog products (from the Offers/ PDFs) into Europa.

Reads catalog_data_part1..4.py, replaces the designs table in the app's
database, and installs the product drawings into the app's Sxedia folder.
Uses the same per-user data folder as the application itself.

Usage from the project root, with the app's environment:
    python tools/import_catalog.py

WARNING: this replaces the whole designs catalog.
"""
import os, shutil, sqlite3, sys

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS_DIR)
sys.path.insert(0, ROOT)
sys.path.insert(0, TOOLS_DIR)

import app as appmod  # resolves the same data folder / DB as the app
DB = appmod.DB
IMG_DIR = appmod.IMG_DIR
os.makedirs(IMG_DIR, exist_ok=True)

from catalog_data_part1 import CATALOG_1_8
from catalog_data_part2 import CATALOG_9_16
from catalog_data_part3 import CATALOG_17_24
from catalog_data_part4 import CATALOG_25_26

ALL_PRODUCTS = CATALOG_1_8 + CATALOG_9_16 + CATALOG_17_24 + CATALOG_25_26


def install_image(name):
    """Copy a product drawing into the app data folder (accepts .png/.jpg)."""
    stem = os.path.splitext(name)[0]
    for candidate in (name, stem + ".png", stem + ".jpg"):
        src = os.path.join(ROOT, "Sxedia", candidate)
        if os.path.isfile(src):
            dest = os.path.join(IMG_DIR, candidate)
            if not os.path.exists(dest):
                shutil.copy2(src, dest)
            return candidate
    print(f"  WARNING: image missing: {name}")
    return name


print(f"Total products to import: {len(ALL_PRODUCTS)}")
print(f"Target database: {DB}")

appmod.init_db()
c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row

# Clear existing catalog designs (comment out to keep existing rows)
c.execute("DELETE FROM designs")
print("Cleared existing designs table.")

inserted = 0
skipped = 0
for p in ALL_PRODUCTS:
    code = p["code"]
    if c.execute("SELECT 1 FROM designs WHERE code=?", (code,)).fetchone():
        skipped += 1
        continue
    img_name = install_image(p["image"])
    c.execute(
        """INSERT INTO designs(code,name,category,series,color,width,height,location,price,descr,image,materials_json,use_count)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,'[]',0)""",
        (code, p["name"], p["category"], p["series"], p["color"],
         p["width"], p["height"], p["location"], p["price"],
         p["descr"], img_name),
    )
    inserted += 1

c.commit()
c.close()
print(f"Inserted: {inserted}, Skipped (already exist): {skipped}")
print("Done. Check the app catalog tab.")
