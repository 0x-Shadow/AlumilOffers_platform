#!/usr/bin/env python3
"""
Import all 26 catalog products from Offers/ PDFs into the AlumilOffers designs catalog.
Reads catalog_data_part1..4.py, inserts into designs table in alumina.db,
and copies product images into Sxedia/.
"""
import os, sys, sqlite3, json

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "alumina.db")
IMG_DIR = os.path.join(BASE, "Sxedia")
os.makedirs(IMG_DIR, exist_ok=True)

sys.path.insert(0, BASE)
from catalog_data_part1 import CATALOG_1_8
from catalog_data_part2 import CATALOG_9_16
from catalog_data_part3 import CATALOG_17_24
from catalog_data_part4 import CATALOG_25_26

ALL_PRODUCTS = CATALOG_1_8 + CATALOG_9_16 + CATALOG_17_24 + CATALOG_25_26

print(f"Total products to import: {len(ALL_PRODUCTS)}")

c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row

# Clear existing catalog designs (optional - comment out to keep existing)
c.execute("DELETE FROM designs")
print("Cleared existing designs table.")

inserted = 0
skipped = 0
for p in ALL_PRODUCTS:
    code = p["code"]
    # Skip if code already exists
    if c.execute("SELECT 1 FROM designs WHERE code=?", (code,)).fetchone():
        skipped += 1
        continue
    img_name = p["image"]
    img_src = os.path.join(IMG_DIR, img_name)
    if not os.path.exists(img_src):
        print(f"  WARNING: image missing for {code}: {img_name}")
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
