# -*- coding: utf-8 -*-
"""
AluminaOffers v1.2.7 - Προσφορές Αλουμινάδων για Windows
Dashboard | Νέα Προσφορά (μία οθόνη) | Κατάλογος | Στοιχεία+Λογότυπο | PDF με ΦΠΑ
"""
__version__ = "1.2.9"
import os, sqlite3, json, shutil, re, html, sys, subprocess, unicodedata, urllib.parse
from datetime import datetime
from tkinter import messagebox, filedialog
import customtkinter as ctk
from PIL import Image as PILImage
# Hardening: cap decompressed pixels (decompression-bomb DoS) + cap file size on upload
try:
    PILImage.MAX_IMAGE_PIXELS = 50_000_000
except Exception:
    pass
MAX_UPLOAD_BYTES = 15 * 1024 * 1024

def esc(s):
    """Escape user text for ReportLab Paragraph (mini-HTML)."""
    return html.escape(str(s or ""), quote=False)

def safe_quote_number(s, fallback="prosfora"):
    s = str(s or "").strip() or fallback
    s = re.sub(r"[^A-Za-z0-9\u0370-\u03FF_\-]+", "_", s)[:40].strip("_") or fallback
    if s in (".", ".."):
        return fallback
    return s

def safe_img_name(name):
    """Containment: IMG_DIR/basename only, no traversal, no absolute escape."""
    if not name:
        return None
    b = os.path.basename(str(name))
    if b in ("", ".", "..") or b.startswith("."):
        return None
    if ".." in b:
        return None
    # allow only sane chars + known extensions
    if not re.fullmatch(r"[A-Za-z0-9\u0370-\u03FF_\- .()]+\.(jpg|jpeg|png|bmp|webp)", b, re.IGNORECASE):
        # timestamped names from store_image always match; anything else -> reject
        return None
    return b

def open_path_safe(path):
    """Cross-platform replacement for os.startfile (Windows-only, crashes elsewhere)."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa: S606 - local file, user-triggered
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        else:
            subprocess.run(["xdg-open", path], check=False)
    except Exception as e:
        try:
            messagebox.showwarning("Προσοχή", f"Δεν άνοιξε αυτόματα:\n{path}\n{e}")
        except Exception:
            pass

def open_folder_and_select(path):
    """Open containing folder and highlight file in OS file explorer."""
    try:
        p = os.path.abspath(path)
        if sys.platform.startswith("win"):
            subprocess.run(f'explorer /select,"{p}"', check=False)
        elif sys.platform == "darwin":
            subprocess.run(["open", "-R", p], check=False)
        else:
            folder = os.path.dirname(p)
            subprocess.run(["xdg-open", folder], check=False)
    except Exception as e:
        try:
            folder = os.path.dirname(os.path.abspath(path))
            open_path_safe(folder)
        except Exception:
            pass

def bind_scroll(widget, scrollable_frame, recursive=True):
    """Ensure mouse wheel scrolling works reliably across platforms (Linux & Windows)."""
    def _wheel(e):
        try:
            canvas = getattr(scrollable_frame, "_parent_canvas", None)
            if canvas:
                if sys.platform.startswith("win"):
                    canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
                elif e.num == 4:
                    canvas.yview_scroll(-2, "units")
                elif e.num == 5:
                    canvas.yview_scroll(2, "units")
        except Exception:
            pass
    try:
        widget.bind("<MouseWheel>", _wheel, add="+")
        widget.bind("<Button-4>", _wheel, add="+")
        widget.bind("<Button-5>", _wheel, add="+")
        if recursive:
            for child in widget.winfo_children():
                bind_scroll(child, scrollable_frame, recursive=True)
    except Exception:
        pass

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, HRFlowable, Image as RLImage,
                                KeepTogether, Flowable)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Στην εκτελέσιμη έκδοση (PyInstaller) το __file__ δείχνει στον προσωρινό
# φάκελο εξαγωγής (_MEI...), που διαγράφεται στο κλείσιμο → όλα τα δεδομένα
# θα χανότουν. Άρα όταν είναι frozen, βάσε έχει ο φάκελος του ίδιου του exe
# (δίπλα του: alumina.db, Sxedia/, PDF_Prosfores/, logo.png — όπως και το README).
# Σε εκτέλεση από πηγή αλλάζει τίποτα.
if getattr(sys, "frozen", False):
    BASE = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "alumina.db")
PDF_DIR = os.path.join(BASE, "PDF_Prosfores")
IMG_DIR = os.path.join(BASE, "Sxedia")
LOGO_FILE = os.path.join(BASE, "logo.png")
os.makedirs(PDF_DIR, exist_ok=True)
os.makedirs(IMG_DIR, exist_ok=True)

def _register_pdf_fonts():
    """Arial on Windows, Liberation/DejaVu/Noto elsewhere — Helvetica has no Greek."""
    pairs = [
        (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
        ("/usr/share/fonts/liberation/LiberationSans-Regular.ttf",
         "/usr/share/fonts/liberation/LiberationSans-Bold.ttf"),
        ("/usr/share/fonts/TTF/DejaVuSans.ttf",
         "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
        ("/usr/share/fonts/noto/NotoSans-Regular.ttf",
         "/usr/share/fonts/noto/NotoSans-Bold.ttf"),
    ]
    for regular, bold in pairs:
        if os.path.isfile(regular) and os.path.isfile(bold):
            try:
                pdfmetrics.registerFont(TTFont("Greek", regular))
                pdfmetrics.registerFont(TTFont("Greek-Bold", bold))
                return "Greek", "Greek-Bold"
            except Exception:
                continue
    return "Helvetica", "Helvetica-Bold"

FONT, FONTB = _register_pdf_fonts()

DEFAULT_FPA = 24.0
BLUE = colors.HexColor("#1a56db")
DARK = colors.HexColor("#1e293b")
LIGHT_BG = colors.HexColor("#eff6ff")

# ---- UI theme ----
NAVY = "#0b1f4b"
BLUEH = "#1a56db"
ACCENT = "#0ea5e9"
BG = "#eef2f7"
TXTD = "#0f172a"
TXTG = "#64748b"
GREEN = "#16a34a"
RED = "#ef4444"
CARD = "#ffffff"
ROWB = "#f8fafc"

CATEGORIES = ["Παράθυρο", "Πόρτα", "Συρόμενο", "Σταθερό",
              "Μπαλκονόπορτα", "Βιτρίνα", "Ντουλάπα", "Άλλο"]
GR_MONTHS = ["", "ΙΑΝ", "ΦΕΒ", "ΜΑΡ", "ΑΠΡ", "ΜΑΪ", "ΙΟΥΝ",
             "ΙΟΥΛ", "ΑΥΓ", "ΣΕΠ", "ΟΚΤ", "ΝΟΕ", "ΔΕΚ"]

# ================= DATABASE =================
def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def ensure_cad_thumbnail(filename, kind='sliding', shutter=False, screen=False, leaves=2, tilt=False):
    path = os.path.join(IMG_DIR, filename)
    if os.path.exists(path):
        return filename
    try:
        from PIL import ImageDraw
        im = PILImage.new('RGB', (260, 220), '#ffffff')
        draw = ImageDraw.Draw(im)
        fx0, fy0, fx1, fy1 = 20, 20, 240, 195
        shutter_h = 42 if shutter else 0
        if shutter:
            draw.rectangle([fx0, fy0, fx1, fy0 + shutter_h], outline='#475569', fill='#cbd5e1', width=2)
            for y in range(fy0 + 6, fy0 + shutter_h, 7):
                draw.line([(fx0 + 2, y), (fx1 - 2, y)], fill='#64748b', width=1)
            fy0 += shutter_h
        draw.rectangle([fx0, fy0, fx1, fy1], outline='#475569', fill='#e2e8f0', width=3)
        gx0, gy0, gx1, gy1 = fx0 + 8, fy0 + 8, fx1 - 8, fy1 - 8
        gw = gx1 - gx0
        gh = gy1 - gy0
        leaf_w = gw / max(1, leaves)
        for i in range(leaves):
            lx0 = int(gx0 + i * leaf_w)
            lx1 = int(gx0 + (i + 1) * leaf_w)
            draw.rectangle([lx0 + 2, gy0 + 2, lx1 - 2, gy1 - 2], outline='#475569',
                           fill='#ffffff' if not (screen and i == leaves - 1) else '#f1f5f9', width=2)
            if screen and i == leaves - 1:
                for x in range(lx0 + 6, lx1 - 4, 4):
                    draw.line([(x, gy0 + 4), (x, gy1 - 4)], fill='#94a3b8', width=1)
            cx = (lx0 + lx1) // 2
            cy = (gy0 + gy1) // 2
            if kind == 'sliding':
                if i == 0:
                    draw.polygon([(cx + 12, cy), (cx - 6, cy - 8), (cx - 6, cy + 8)], fill='#1e293b')
                else:
                    draw.polygon([(cx - 12, cy), (cx + 6, cy - 8), (cx + 6, cy + 8)], fill='#1e293b')
            elif kind == 'tilt' or tilt:
                draw.line([(lx0 + 6, gy0 + 6), (cx, gy1 - 6)], fill='#64748b', width=2)
                draw.line([(lx1 - 6, gy0 + 6), (cx, gy1 - 6)], fill='#64748b', width=2)
            elif kind == 'casement':
                if leaves == 1:
                    draw.line([(lx0 + 6, gy0 + 6), (lx1 - 6, cy)], fill='#64748b', width=2)
                    draw.line([(lx0 + 6, gy1 - 6), (lx1 - 6, cy)], fill='#64748b', width=2)
                    draw.rectangle([lx1 - 8, cy - 8, lx1 - 4, cy + 8], fill='#1e293b')
                elif i == 0:
                    draw.line([(lx0 + 6, gy0 + 6), (lx1 - 4, cy)], fill='#64748b', width=2)
                    draw.line([(lx0 + 6, gy1 - 6), (lx1 - 4, cy)], fill='#64748b', width=2)
                    draw.rectangle([lx1 - 8, cy - 10, lx1 - 4, cy + 10], fill='#1e293b')
                else:
                    draw.line([(lx1 - 6, gy0 + 6), (lx0 + 4, cy)], fill='#64748b', width=2)
                    draw.line([(lx1 - 6, gy1 - 6), (lx0 + 4, cy)], fill='#64748b', width=2)
                    draw.rectangle([lx0 + 4, cy - 10, lx0 + 8, cy + 10], fill='#1e293b')
            elif kind == 'fixed':
                draw.line([(lx0 + 4, gy0 + 4), (lx1 - 4, gy1 - 4)], fill='#cbd5e1', width=1)
                draw.line([(lx0 + 4, gy1 - 4), (lx1 - 4, gy0 + 4)], fill='#cbd5e1', width=1)
            elif kind == 'door':
                draw.line([(lx0 + 6, gy0 + 6), (lx1 - 6, cy)], fill='#64748b', width=2)
                draw.line([(lx0 + 6, gy1 - 6), (lx1 - 6, cy)], fill='#64748b', width=2)
                draw.rectangle([lx1 - 10, cy - 25, lx1 - 6, cy + 25], fill='#1e293b')
        draw.rectangle([fx0, fy0, fx1, fy1], outline='#334155', width=2)
        draw.text((130, 202), 'Τοποθέτηση', fill='#64748b', anchor='mm')
        im.save(path)
        return filename
    except Exception:
        return filename

def seed_default_designs(c):
    ensure_cad_thumbnail('thumb_s350_shutter_screen.png', kind='sliding', shutter=True, screen=True, leaves=2)
    ensure_cad_thumbnail('thumb_s350_screen.png', kind='sliding', shutter=False, screen=True, leaves=2)
    ensure_cad_thumbnail('thumb_m9660_transom.png', kind='tilt', shutter=False, screen=False, leaves=1)
    ensure_cad_thumbnail('thumb_m9660_casement_shutter.png', kind='casement', shutter=True, screen=False, leaves=2)
    ensure_cad_thumbnail('thumb_s350_simple.png', kind='sliding', shutter=False, screen=False, leaves=2)
    ensure_cad_thumbnail('thumb_m9660_single_casement.png', kind='casement', shutter=False, screen=False, leaves=1)
    ensure_cad_thumbnail('thumb_fixed.png', kind='fixed', shutter=False, screen=False, leaves=1)
    ensure_cad_thumbnail('thumb_door.png', kind='door', shutter=False, screen=False, leaves=1)

    presets = [
        ("Π-101", "ΔΙΦΥΛΛΟ ΕΠΑΛΛΗΛΟ ΜΕ ΣΙΤΑ (S398-S384-S490-S382-S463)", "Συρόμενο",
         "ALUMIL/S350 ALUTHERM", "ΑΝΘΡΑΚΙ RAL 8.85 (ΘΕΡΜΟ)", "330", "235", "1ος-ΓΩΝΙΑΚΟ", 3400.0,
         "ΕΝΕΡΓΕΙΑΚΟ ΚΟΥΦΩΜΑ ΣΥΡΟΜΕΝΟ ΕΠΑΛΛΗΛΟ ΤΗΣ ALUMIL\nΥΑΛΟΠΙΝΑΚΕΣ 4 ΕΠΟΧΩΝ 4mm Planistar Evo-Argon-5mm\nΡΟΛΟ ΑΛΟΥΜΙΝΙΟΥ ΒΑΡΕΩΣ ΤΥΠΟΥ ΗΛΕΚΤΡΙΚΟ ΜΕ ΦΥΛΑΡΑΚΙΑ ΜΕΓΑΛΗΣ ΔΙΑΤΡΗΣΗΣ ΓΙΑ ΑΕΡΙΣΜΟ-ΚΟΥΤΙ ΜΕ ΘΕΡΜΟΔΙΑΚΟΠΗ\nΚΛΕΙΔΑΡΙΕΣ ΑΣΦΑΛΕΙΑΣ 4 ΚΛΕΙΔΩΜΑΤΩΝ GU ΓΕΡΜΑΝΙΑΣ\nΡΑΟΥΛΑ ΠΟΛΑΠΛΑ ΕΝΙΣΧΥΜΕΝΑ ΤΕΦΛΟΝ\nΣΙΤΑ ΣΥΡΟΜΕΝΗ ΜΟΝΟΦΥΛΛΗ",
         "thumb_s350_shutter_screen.png"),
        ("Π-102", "ΔΙΦΥΛΛΟ ΕΠΑΛΛΗΛΟ ΜΕ ΣΙΤΑ (S398-S384-S490-S382-S463)", "Συρόμενο",
         "ALUMIL/S350 ALUTHERM", "ΑΝΘΡΑΚΙ RAL ΘΕΡΜΟ", "255", "75", "1ος-ΓΩΝΙΑΚΟ", 1300.0,
         "ΕΝΕΡΓΕΙΑΚΟ ΚΟΥΦΩΜΑ ΣΥΡΟΜΕΝΟ ΕΠΑΛΛΗΛΟ ΤΗΣ ALUMIL\nΥΑΛΟΠΙΝΑΚΕΣ 4 ΕΠΟΧΩΝ 4mm Planistar Evo-Argon-5mm\nΚΛΕΙΔΑΡΙΕΣ ΑΣΦΑΛΕΙΑΣ 2 ΚΛΕΙΔΩΜΑΤΩΝ GU ΓΕΡΜΑΝΙΑΣ\nΡΑΟΥΛΑ ΠΟΛΑΠΛΑ ΕΝΙΣΧΥΜΕΝΑ ΤΕΦΛΟΝ\nΣΙΤΑ ΣΥΡΟΜΕΝΗ ΜΟΝΟΦΥΛΛΗ",
         "thumb_s350_screen.png"),
        ("Π-103", "ΜΟΝΟΦΥΛΛΟ ΑΝΟΙΓΟΜΕΝΟ ΦΕΓΓΙΤΗΣ (19652, 19676, 11454)", "Παράθυρο",
         "ALUMIL/ALUMIL M9660", "ΑΝΘΡΑΚΙ RAL ΘΕΡΜΟ", "243", "75", "1ος-ΓΩΝΙΑΚΟ", 850.0,
         "ΕΝΕΡΓΕΙΑΚΟ ΚΟΥΦΩΜΑ ΑΝΟΙΓΟΜΕΝΟ ΦΕΓΓΙΤΗΣ ΤΗΣ ALUMIL\nΥΑΛΟΠΙΝΑΚΕΣ 4 ΕΠΟΧΩΝ 4mm Planistar Evo-Argon-5mm\nΣΙΤΑ ΣΤΑΘΕΡΗ ΕΞΩΤΕΡΙΚΑ\nΜΗΧΑΝΙΣΜΟΣ ΑΝΑΚΛΙΣΗΣ",
         "thumb_m9660_transom.png"),
        ("Π-104", "ΔΙΦΥΛΛΟ ΑΝΟΙΓΟΜΕΝΟ ΤΖΑΜΙ (19652-19670-19682-11451)", "Παράθυρο",
         "ALUMIL/ALUMIL M9660", "ΑΝΘΡΑΚΙ RAL ΘΕΡΜΟ", "195", "235", "ΙΣΟΓΕΙΟ", 1800.0,
         "ΕΝΕΡΓΕΙΑΚΟ ΚΟΥΦΩΜΑ ΔΙΦΥΛΛΟ ΑΝΟΙΓΟΜΕΝΟ ΤΗΣ ALUMIL\nΥΑΛΟΠΙΝΑΚΕΣ 4 ΕΠΟΧΩΝ 4mm Planistar Evo-Argon-3+3 TRIPLEX\nΡΟΛΟ ΑΛΟΥΜΙΝΙΟΥ ΒΑΡΕΩΣ ΤΥΠΟΥ ΗΛΕΚΤΡΙΚΟ ΜΕ ΦΥΛΑΡΑΚΙΑ ΜΕΓΑΛΗΣ ΔΙΑΤΡΗΣΗΣ ΓΙΑ ΑΕΡΙΣΜΟ-ΚΟΥΤΙ ΜΕ ΘΕΡΜΟΔΙΑΚΟΠΗ\nΗΛΕΚΤΡΙΚΗ ΣΙΤΑ ΚΑΘΕΤΗΣ ΚΙΝΗΣΗΣ\nΜΗΧΑΝΙΣΜΟΣ ΑΝΑΚΛΙΣΗΣ ΦΥΛΛΟΥ",
         "thumb_m9660_casement_shutter.png"),
        ("Π-105", "ΜΠΑΛΚΟΝΟΠΟΡΤΑ ΔΙΦΥΛΛΗ ΑΝΟΙΓΟΜΕΝΗ ΜΕ ΡΟΛΟ & ΣΙΤΑ", "Μπαλκονόπορτα",
         "ALUMIL/ALUMIL M9660", "ΑΝΘΡΑΚΙ RAL ΘΕΡΜΟ", "140", "220", "ΣΑΛΟΝΙ", 1650.0,
         "ΕΝΕΡΓΕΙΑΚΗ ΜΠΑΛΚΟΝΟΠΟΡΤΑ ΔΙΦΥΛΛΗ ΑΝΟΙΓΟΜΕΝΗ ΤΗΣ ALUMIL\nΥΑΛΟΠΙΝΑΚΕΣ 4 ΕΠΟΧΩΝ 4mm Planistar Evo-Argon-5mm\nΡΟΛΟ ΑΛΟΥΜΙΝΙΟΥ ΒΑΡΕΩΣ ΤΥΠΟΥ ΗΛΕΚΤΡΙΚΟ ΜΕ ΘΕΡΜΟΔΙΑΚΟΠΗ\nΣΙΤΑ ΠΛΙΣΕ ΟΡΙΖΟΝΤΙΑΣ ΚΙΝΗΣΗΣ\nΜΗΧΑΝΙΣΜΟΣ ΑΝΑΚΛΙΣΗΣ ΦΥΛΛΟΥ",
         "thumb_m9660_casement_shutter.png"),
        ("Π-106", "ΔΙΦΥΛΛΟ ΕΠΑΛΛΗΛΟ ΑΠΛΟ", "Συρόμενο",
         "ALUMIL/S350 ALUTHERM", "ΛΕΥΚΟ RAL 9010", "160", "140", "ΥΠΝΟΔΩΜΑΤΙΟ", 750.0,
         "ΕΝΕΡΓΕΙΑΚΟ ΚΟΥΦΩΜΑ ΣΥΡΟΜΕΝΟ ΕΠΑΛΛΗΛΟ ΤΗΣ ALUMIL\nΥΑΛΟΠΙΝΑΚΕΣ 4 ΕΠΟΧΩΝ 4mm Planistar Evo-Argon-5mm\nΚΛΕΙΔΑΡΙΕΣ ΑΣΦΑΛΕΙΑΣ 2 ΚΛΕΙΔΩΜΑΤΩΝ GU ΓΕΡΜΑΝΙΑΣ\nΡΑΟΥΛΑ ΠΟΛΑΠΛΑ ΕΝΙΣΧΥΜΕΝΑ ΤΕΦΛΟΝ",
         "thumb_s350_simple.png"),
        ("Π-107", "ΜΟΝΟΦΥΛΛΟ ΑΝΟΙΓΟΜΕΝΟ / ΑΝΑΚΛΙΝΟΜΕΝΟ ΠΑΡΑΘΥΡΟ", "Παράθυρο",
         "ALUMIL/ALUMIL M9660", "ΑΝΘΡΑΚΙ RAL ΘΕΡΜΟ", "80", "120", "ΚΟΥΖΙΝΑ", 480.0,
         "ΕΝΕΡΓΕΙΑΚΟ ΠΑΡΑΘΥΡΟ ΜΟΝΟΦΥΛΛΟ ΑΝΟΙΓΟΜΕΝΟ / ΑΝΑΚΛΙΝΟΜΕΝΟ\nΥΑΛΟΠΙΝΑΚΕΣ 4 ΕΠΟΧΩΝ 4mm Planistar Evo-Argon-5mm\nΣΙΤΑ ΚΑΘΕΤΗ ΜΕ ΕΛΑΤΗΡΙΟ\nΠΕΡΙΜΕΤΡΙΚΟΣ ΜΗΧΑΝΙΣΜΟΣ ΑΝΑΚΛΙΣΗΣ",
         "thumb_m9660_single_casement.png"),
        ("Π-108", "ΣΤΑΘΕΡΟ ΠΛΑΙΣΙΟ / ΒΙΤΡΙΝΑ", "Σταθερό",
         "ALUMIL/ALUMIL M9660", "ΑΝΘΡΑΚΙ RAL ΘΕΡΜΟ", "200", "150", "ΧΩΛ", 620.0,
         "ΕΝΕΡΓΕΙΑΚΟ ΣΤΑΘΕΡΟ ΠΛΑΙΣΙΟ ΤΗΣ ALUMIL\nΥΑΛΟΠΙΝΑΚΕΣ 4 ΕΠΟΧΩΝ 4mm Planistar Evo-Argon-3+3 TRIPLEX\nΥΨΗΛΗ ΘΕΡΜΟΜΟΝΩΣΗ & ΗΧΟΜΟΝΩΣΗ",
         "thumb_fixed.png"),
        ("Π-109", "ΠΟΡΤΑ ΕΙΣΟΔΟΥ ΑΛΟΥΜΙΝΙΟΥ", "Πόρτα",
         "ALUMIL/SMARTIA M11000", "ΑΝΘΡΑΚΙ RAL ΘΕΡΜΟ", "100", "220", "ΚΥΡΙΑ ΕΙΣΟΔΟΣ", 1450.0,
         "ΠΟΡΤΑ ΕΙΣΟΔΟΥ ΑΛΟΥΜΙΝΙΟΥ ΜΕ ΘΕΡΜΟΔΙΑΚΟΠΗ\nΠΑΝΕΛ ΑΛΟΥΜΙΝΙΟΥ ΒΑΡΕΩΣ ΤΥΠΟΥ INOX ΣΧΕΔΙΟ\nΚΛΕΙΔΑΡΙΑ ΑΣΦΑΛΕΙΑΣ 5 ΣΗΜΕΙΩΝ\nΜΕΝΤΕΣΕΔΕΣ ΒΑΡΕΩΣ ΤΥΠΟΥ 3D ΡΥΘΜΙΖΟΜΕΝΟΙ\nΠΟΜΟΛΟ ΜΠΑΡΑ INOX 80cm",
         "thumb_door.png"),
        ("Π-110", "ΔΙΦΥΛΛΟ ΕΠΑΛΛΗΛΟ EUROPA 5500 HYBRID", "Συρόμενο",
         "EUROPA 5500 HYBRID", "RAL 7016 ΑΝΘΡΑΚΙ", "180", "220", "1ος-ΠΡΟΣΟΨΗ", 1900.0,
         "ΕΝΕΡΓΕΙΑΚΟ ΚΟΥΦΩΜΑ ΣΥΡΟΜΕΝΟ EUROPA 5500 HYBRID\nΥΑΛΟΠΙΝΑΚΕΣ 4 ΕΠΟΧΩΝ 4mm Planistar Evo-Argon-5mm\nΡΟΛΟ ΑΛΟΥΜΙΝΙΟΥ ΕΠΙΚΑΘΗΜΕΝΟ ΜΕ ΜΟΤΕΡ SOMFY\nΣΙΤΑ ΣΥΡΟΜΕΝΗ ΕΝΙΣΧΥΜΕΝΗ\nΠΟΛΛΑΠΛΑ ΚΛΕΙΔΩΜΑΤΑ ΑΣΦΑΛΕΙΑΣ",
         "thumb_s350_shutter_screen.png"),
    ]
    for p in presets:
        c.execute("""INSERT INTO designs(code,name,category,series,color,width,height,location,price,descr,image)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?)""", p)

def init_db():
    c = db()
    c.execute("""CREATE TABLE IF NOT EXISTS materials(
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, unit TEXT, price REAL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS customers(
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, phone TEXT, email TEXT, address TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS designs(
        id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, name TEXT, category TEXT,
        width TEXT, height TEXT, descr TEXT, image TEXT, price REAL DEFAULT 0)""")
    dcols = [r[1] for r in c.execute("PRAGMA table_info(designs)").fetchall()]
    if "materials_json" not in dcols:
        c.execute("ALTER TABLE designs ADD COLUMN materials_json TEXT DEFAULT '[]'")
    if "series" not in dcols:
        c.execute("ALTER TABLE designs ADD COLUMN series TEXT DEFAULT ''")
    if "color" not in dcols:
        c.execute("ALTER TABLE designs ADD COLUMN color TEXT DEFAULT ''")
    if "location" not in dcols:
        c.execute("ALTER TABLE designs ADD COLUMN location TEXT DEFAULT ''")
    if "use_count" not in dcols:
        c.execute("ALTER TABLE designs ADD COLUMN use_count INTEGER DEFAULT 0")
        c.execute("UPDATE designs SET use_count = 10 - (id % 10) WHERE use_count IS NULL OR use_count = 0")
    c.execute("""CREATE TABLE IF NOT EXISTS quotes(
        id INTEGER PRIMARY KEY AUTOINCREMENT, number TEXT, date TEXT,
        customer_id INTEGER, customer_name TEXT, customer_info TEXT,
        items_json TEXT, subtotal REAL, vat_rate REAL, vat_amount REAL,
        total REAL, notes TEXT)""")
    cols = [r[1] for r in c.execute("PRAGMA table_info(quotes)").fetchall()]
    if "designs_json" not in cols:
        c.execute("ALTER TABLE quotes ADD COLUMN designs_json TEXT DEFAULT '[]'")
    if "include_labor" not in cols:
        c.execute("ALTER TABLE quotes ADD COLUMN include_labor INTEGER DEFAULT 0")
    if "labor_amount" not in cols:
        c.execute("ALTER TABLE quotes ADD COLUMN labor_amount REAL DEFAULT 0.0")
    if "labor_desc" not in cols:
        c.execute("ALTER TABLE quotes ADD COLUMN labor_desc TEXT DEFAULT ''")
    c.execute("""CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT)""")
    if not c.execute("SELECT 1 FROM settings WHERE key='company'").fetchone():
        c.execute("INSERT INTO settings VALUES('company', ?)", (json.dumps({
            "name": "Η Επωνυμία Σου ΙΚΕ",
            "address": "Οδός 12, Πόλη 12100",
            "phone": "210 0000000  •  697 0000000",
            "email": "info@example.gr",
            "afm": "", "doy": "",
            "notes": "Ισχύς προσφοράς: 30 ημέρες."
        }, ensure_ascii=False),))
    if c.execute("SELECT COUNT(*) c FROM materials").fetchone()["c"] == 0:
        demo = [
            ("Κουφώματα Αλουμινίου - Συρόμενο", "τ.μ.", 180.0),
            ("Κουφώματα Αλουμινίου - Ανοιγόμενο", "τ.μ.", 220.0),
            ("Πόρτα εισόδου αλουμινίου", "τεμ.", 650.0),
            ("Σίτα συρόμενη", "τεμ.", 45.0),
            ("Τζάμι διπλό Low-E 24mm", "τ.μ.", 65.0),
            ("Ρολό αλουμινίου + μοτέρ", "τεμ.", 320.0),
            ("Τοποθέτηση / Εργασία", "τεμ.", 80.0),
        ]
        c.executemany("INSERT INTO materials(name,unit,price) VALUES(?,?,?)", demo)
    if c.execute("SELECT COUNT(*) c FROM designs").fetchone()["c"] == 0:
        seed_default_designs(c)
    c.commit(); c.close()

def get_company():
    c = db()
    r = c.execute("SELECT value FROM settings WHERE key='company'").fetchone()
    c.close()
    return json.loads(r["value"]) if r else {}

def save_company(d):
    c = db()
    c.execute("INSERT OR REPLACE INTO settings VALUES('company',?)", (json.dumps(d, ensure_ascii=False),))
    c.commit(); c.close()

def get_logo():
    return LOGO_FILE if os.path.exists(LOGO_FILE) else None

def set_logo(src):
    if os.path.getsize(src) > MAX_UPLOAD_BYTES:
        raise ValueError("Η εικόνα είναι πολύ μεγάλη (όριο 15MB).")
    with PILImage.open(src) as im:
        im.load()  # force decode now, inside try in caller
        im = im.convert("RGB")
        im.thumbnail((600, 600))
        im.save(LOGO_FILE, "PNG")
    return LOGO_FILE

def img_path(name):
    if not name:
        return None
    b = safe_img_name(name)
    if not b:
        return None
    p = os.path.join(IMG_DIR, b)
    return p if os.path.exists(p) else None

def store_image(src):
    if os.path.getsize(src) > MAX_UPLOAD_BYTES:
        raise ValueError("Η εικόνα είναι πολύ μεγάλη (όριο 15MB).")
    # verify it really decodes as an image before copying (rejects polyglots early)
    with PILImage.open(src) as im:
        im.verify()
    ext = os.path.splitext(src)[1].lower() or ".jpg"
    if ext not in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
        ext = ".jpg"
    fname = datetime.now().strftime("%Y%m%d%H%M%S%f") + ext
    shutil.copy2(src, os.path.join(IMG_DIR, fname))
    return fname

def quote_stats():
    """Επιστρέφει στατιστικά για το dashboard."""
    c = db()
    rows = c.execute("SELECT date, total FROM quotes").fetchall()
    c.close()
    now = datetime.now()
    mkey = (now.year, now.month)
    n_total = len(rows)
    n_month = 0; rev_month = 0.0; rev_year = 0.0
    monthly = {}
    for r in rows:
        try:
            tot = float(r["total"] or 0)
        except Exception:
            tot = 0.0
        try:
            d = datetime.strptime(r["date"], "%d/%m/%Y")
        except Exception:
            continue
        if (d.year, d.month) == mkey:
            n_month += 1; rev_month += tot
        if d.year == now.year:
            rev_year += tot
        monthly[(d.year, d.month)] = monthly.get((d.year, d.month), 0.0) + tot
    avg = (sum(float(r["total"] or 0) for r in rows) / n_total) if n_total else 0.0
    bars = []
    y, m = now.year, now.month
    for _ in range(6):
        bars.append(((y, m), monthly.get((y, m), 0.0)))
        m -= 1
        if m == 0:
            m = 12; y -= 1
    bars.reverse()
    return {"n_total": n_total, "n_month": n_month, "rev_month": rev_month,
            "rev_year": rev_year, "avg": avg, "bars": bars}

# ================= PDF =================
def fmt(n):
    try: return f"{float(n):,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
    except: return "0,00 €"

def pdf_image(path, max_w=62*mm, max_h=52*mm):
    try:
        with PILImage.open(path) as im:
            w, h = im.size
        s = min(max_w / w, max_h / h)
        return RLImage(path, width=w*s, height=h*s)
    except Exception:
        return None

# ================= 2D ΣΧΗΜΑΤΙΚΑ (Π x Υ σε εκατοστά) =================
# Alumil-style elevation: thin gray frames, opening arrows, optional roller / σίτα.
GLASSC = colors.HexColor("#eef2f5")
GLASSDIM = colors.HexColor("#d9dee4")
FRAMEC = colors.HexColor("#9aa3ad")
FRAMEDK = colors.HexColor("#5b6570")
HANDLEC = colors.HexColor("#3f3f46")
ARROWC = colors.HexColor("#27272a")
HATCHC = colors.HexColor("#8b949e")
DIMC = colors.HexColor("#94a3b8")
CAPTIONC = colors.HexColor("#64748b")
HEADBAR = colors.HexColor("#4b5563")
PRICEGR = colors.HexColor("#15803d")

def _num(v):
    """'120' / '120,5' / 120 -> float, αλλιώς None."""
    try:
        s = str(v or "").strip().replace(",", ".")
        return float(s) if s else None
    except Exception:
        return None

def fold_el(text):
    """Lowercase Greek without accents, for matching συρόμενο / δίφυλλο / σίτα…"""
    try:
        s = unicodedata.normalize("NFD", str(text or "").lower())
        return "".join(ch for ch in s if not unicodedata.combining(ch))
    except Exception:
        return str(text or "").lower()

def dims_meters_txt(w, h):
    """Clean dimensions in cm: e.g. 160 × 220 εκ."""
    wn, hn = _num(w), _num(h)
    if wn is None or hn is None:
        ww = str(w or "").strip() or "-"
        hh = str(h or "").strip() or "-"
        return f"{ww} × {hh} εκ."
    if max(wn, hn) < 10 and max(wn, hn) > 0:
        wn, hn = wn * 100.0, hn * 100.0
    w_str = f"{wn:g}"
    h_str = f"{hn:g}"
    return f"{w_str} × {h_str} εκ."

def dims_cm_values(w, h):
    """Numeric (width, height) in cm, accepting cm or metre input."""
    wn, hn = _num(w), _num(h)
    if wn is None or hn is None or wn <= 0 or hn <= 0:
        return None, None
    if max(wn, hn) < 10:
        wn, hn = wn * 100.0, hn * 100.0
    return wn, hn

# Σειρά έχει σημασία: το "μπαλκονόπορτα" περιέχει το "πόρτα".
_CAT_HINTS = [("συρομεν", "Συρόμενο"), ("επαλληλ", "Συρόμενο"), ("μπαλκον", "Μπαλκονόπορτα"),
              ("βιτριν", "Βιτρίνα"), ("ντουλαπ", "Ντουλάπα"),
              ("σταθερ", "Σταθερό"), ("παραθυρ", "Παράθυρο"), ("φεγγιτ", "Παράθυρο"),
              ("πορτα", "Πόρτα"), ("κουφωμα", "Παράθυρο")]

def guess_category(text, fallback=""):
    """Κατηγορία από ελεύθερο κείμενο γραμμής (χωρίς τόνους), αλλιώς το υπάρχον."""
    if fallback and fallback != "Άλλο":
        return fallback
    s = fold_el(text)
    for key, cat in _CAT_HINTS:
        if key in s:
            return cat
    return fallback or ""

def resolved_category(d):
    """Κατηγορία που θα χρησιμοποιηθεί για το σχέδιο: η αποθηκευμένη, ή αν
    λείπει/είναι «Άλλο» αυτή που προκύπτει από το όνομα της γραμμής."""
    cat = str(d.get("category") or "").strip()
    if cat and cat != "Άλλο":
        return cat
    return guess_category(d.get("name", ""), "") or cat

class Schematic(Flowable):
    """Alumil-style 2D elevation: frame, sashes, opening arrows, roller, σίτα.
    Aspect ratio follows Π x Υ (cm). Extra caption under the drawing."""

    BOX_W = 62*mm
    BOX_H = 62*mm

    def __init__(self, w_cm, h_cm, category="", label=None, w_txt=None, h_txt=None,
                 name="", descr="", location="", show_labels=True):
        Flowable.__init__(self)
        self.w_cm = float(w_cm)
        self.h_cm = float(h_cm)
        self.cat = str(category or "").strip()
        self.name = str(name or "")
        self.descr = str(descr or "")
        self.location = str(location or "").strip()
        self.w_txt = str(w_txt) if w_txt is not None else f"{self.w_cm:g}"
        self.h_txt = str(h_txt) if h_txt is not None else f"{self.h_cm:g}"
        self.label = label or f"{self.w_txt} x {self.h_txt} εκ."
        self.feat = self._features()
        self.show_labels = show_labels
        if show_labels:
            self.pad_l = 8*mm
            self.pad_t = 6.5*mm
            self.pad_b = 7.5*mm
        else:
            self.pad_l = 2*mm
            self.pad_t = 2*mm
            self.pad_b = 2*mm
        shutter_h = 7.2*mm if self.feat["shutter"] else 0
        aw = self.BOX_W - self.pad_l - 3*mm
        ah = self.BOX_H - self.pad_t - self.pad_b - shutter_h
        s = min(aw / self.w_cm, ah / self.h_cm)
        self.iw = self.w_cm * s
        self.ih = self.h_cm * s
        # keep arrows readable on very wide/low transoms (φεγγίτες)
        min_ih = 20*mm
        if self.ih < min_ih and self.h_cm > 0:
            s2 = min_ih / self.h_cm
            if self.w_cm * s2 <= aw:
                self.iw = self.w_cm * s2
                self.ih = min_ih
            else:
                self.ih = min(min_ih, ah)
        self.shutter_h = shutter_h
        self.width = self.BOX_W
        self.height = min(self.BOX_H, self.pad_b + self.ih + self.shutter_h + self.pad_t)

    def wrap(self, aW=None, aH=None):
        return self.width, self.height

    def _features(self):
        blob = fold_el(" ".join([self.cat, self.name, self.descr]))
        name_b = fold_el(self.name)
        shutter = any(k in blob for k in ("ρολο", "ρολλ"))
        screen = "σιτα" in blob
        sliding = self.cat == "Συρόμενο" or any(k in blob for k in ("συρομεν", "επαλληλ"))
        tilt = "φεγγιτ" in blob
        door = self.cat in ("Πόρτα", "Μπαλκονόπορτα") or any(k in blob for k in ("πορτα", "μπαλκον"))
        leaf_src = name_b if any(k in name_b for k in ("φυλλ", "φυλο")) else blob
        if "τριφυλλ" in leaf_src:
            leaves = 3
        elif "μονοφυλλ" in leaf_src:
            leaves = 1
        elif "διφυλλ" in leaf_src:
            leaves = 2
        elif self.cat == "Σταθερό":
            leaves = 1
        elif self.cat in ("Συρόμενο", "Μπαλκονόπορτα", "Ντουλάπα"):
            leaves = 3 if self.w_cm > 200 else 2
        elif self.cat == "Βιτρίνα":
            leaves = 3 if self.w_cm > 180 else 2
        else:
            leaves = 2
        return {"shutter": shutter, "screen": screen, "sliding": sliding,
                "tilt": tilt, "door": door, "leaves": max(1, leaves)}

    def _arrow(self, c, x, y, direction, size):
        p = c.beginPath()
        s = size
        if direction == "R":
            p.moveTo(x, y)
            p.lineTo(x - s, y + s * 0.58)
            p.lineTo(x - s, y - s * 0.58)
        elif direction == "L":
            p.moveTo(x, y)
            p.lineTo(x + s, y + s * 0.58)
            p.lineTo(x + s, y - s * 0.58)
        elif direction == "U":
            p.moveTo(x, y)
            p.lineTo(x - s * 0.58, y - s)
            p.lineTo(x + s * 0.58, y - s)
        else:
            p.moveTo(x, y)
            p.lineTo(x - s * 0.58, y + s)
            p.lineTo(x + s * 0.58, y + s)
        p.close()
        c.setFillColor(ARROWC)
        c.drawPath(p, fill=1, stroke=0)

    def _hatch_v(self, c, x, y, w, h, step=1.15*mm):
        if w <= 0 or h <= 0:
            return
        c.saveState()
        p = c.beginPath()
        p.rect(x, y, w, h)
        c.clipPath(p, stroke=0, fill=0)
        c.setStrokeColor(HATCHC)
        c.setLineWidth(0.35)
        xx = x
        while xx <= x + w:
            c.line(xx, y, xx, y + h)
            xx += step
        c.restoreState()

    def _hatch_h(self, c, x, y, w, h, step=1.05*mm):
        if w <= 0 or h <= 0:
            return
        c.saveState()
        p = c.beginPath()
        p.rect(x, y, w, h)
        c.clipPath(p, stroke=0, fill=0)
        c.setStrokeColor(FRAMEDK)
        c.setLineWidth(0.4)
        yy = y + step * 0.6
        while yy < y + h:
            c.line(x, yy, x + w, yy)
            yy += step
        c.restoreState()

    def draw(self):
        c = self.canv
        f = self.feat
        n = f["leaves"]
        iw, ih = self.iw, self.ih
        x0 = self.pad_l + (self.BOX_W - self.pad_l - 3*mm - iw) / 2.0
        y0 = self.pad_b + 1*mm
        ft = max(1.1*mm, min(2.4*mm, min(iw, ih) / 12.0))
        mt = max(1.2*mm, ft * 0.85)

        # --- roller box sits on top of the frame ---
        if f["shutter"]:
            sh = self.shutter_h
            c.setFillColor(FRAMEC)
            c.setStrokeColor(FRAMEDK)
            c.setLineWidth(0.6)
            c.rect(x0, y0 + ih, iw, sh, stroke=1, fill=1)
            self._hatch_h(c, x0 + 0.5*mm, y0 + ih + 0.4*mm, iw - 1*mm, sh - 0.8*mm, 1.15*mm)
            # small motor box on the right
            mw = min(6*mm, iw * 0.14)
            c.setFillColor(colors.HexColor("#7b848d"))
            c.rect(x0 + iw - mw, y0 + ih, mw, sh, stroke=1, fill=1)

        # outer frame
        c.setFillColor(FRAMEC)
        c.setStrokeColor(FRAMEDK)
        c.setLineWidth(0.7)
        c.setLineJoin(1)
        c.rect(x0, y0, iw, ih, stroke=1, fill=1)

        gx, gy = x0 + ft, y0 + ft
        gw, gh = max(0.0, iw - 2 * ft), max(0.0, ih - 2 * ft)
        c.setFillColor(GLASSC)
        c.rect(gx, gy, gw, gh, stroke=0, fill=1)

        # sash rectangles
        leaf_w = gw / float(n) if n else gw
        for i in range(n):
            lx = gx + i * leaf_w
            # inner rebate
            c.setStrokeColor(FRAMEDK)
            c.setFillColor(FRAMEC)
            c.setLineWidth(0.5)
            if i > 0:
                c.rect(lx - mt / 2.0, gy, mt, gh, stroke=0, fill=1)
            inset = max(0.7*mm, ft * 0.45)
            c.setFillColor(GLASSDIM if (f["screen"] and i == n - 1) else GLASSC)
            c.rect(lx + inset, gy + inset, max(0, leaf_w - 2 * inset), max(0, gh - 2 * inset),
                   stroke=0, fill=1)
            c.setStrokeColor(FRAMEDK)
            c.rect(lx + inset * 0.3, gy + inset * 0.3,
                   max(0, leaf_w - 0.6 * inset), max(0, gh - 0.6 * inset), stroke=1, fill=0)

            glass_x = lx + inset
            glass_y = gy + inset
            glass_w = max(0, leaf_w - 2 * inset)
            glass_h = max(0, gh - 2 * inset)

            if f["screen"] and i == n - 1:
                self._hatch_v(c, glass_x, glass_y, glass_w, glass_h, 0.95*mm)

            # opening indicators
            if glass_w > 4*mm and glass_h > 6*mm and self.cat != "Σταθερό":
                az = min(4.2*mm, glass_w * 0.28, glass_h * 0.18)
                cy = glass_y + glass_h * 0.52
                is_transom = f["tilt"] or (n == 1 and ("φεγγιτ" in fold_el(self.name) or "φεγγιτ" in fold_el(self.descr)))
                if is_transom:
                    # Transom / Tilt triangle opening lines (DIN/ISO architectural symbol, exactly as in Item 3)
                    c.saveState()
                    c.setStrokeColor(colors.HexColor("#334155"))
                    c.setLineWidth(0.65)
                    p = c.beginPath()
                    p.moveTo(glass_x + 1.2*mm, glass_y + glass_h - 1.2*mm)
                    p.lineTo(glass_x + glass_w * 0.5, glass_y + 1.2*mm)
                    p.lineTo(glass_x + glass_w - 1.2*mm, glass_y + glass_h - 1.2*mm)
                    c.drawPath(p, fill=0, stroke=1)
                    # small latch
                    c.setFillColor(HANDLEC)
                    c.rect(glass_x + glass_w * 0.5 - 1.2*mm, glass_y + 0.8*mm, 2.4*mm, 0.9*mm, stroke=0, fill=1)
                    c.restoreState()
                elif f["sliding"] or self.cat == "Συρόμενο":
                    if n == 1:
                        self._arrow(c, glass_x + glass_w * 0.72, cy, "R", az)
                    elif i == 0:
                        self._arrow(c, glass_x + glass_w * 0.72, cy, "R", az)
                    elif i == n - 1:
                        self._arrow(c, glass_x + glass_w * 0.28, cy, "L", az)
                    else:
                        self._arrow(c, glass_x + glass_w * 0.35, cy, "L", az * 0.8)
                        self._arrow(c, glass_x + glass_w * 0.65, cy, "R", az * 0.8)
                else:
                    # Casement opening lines (triangular lines from hinges to handle, exactly as in Item 4)
                    c.saveState()
                    c.setStrokeColor(colors.HexColor("#334155"))
                    c.setLineWidth(0.65)
                    p = c.beginPath()
                    if n == 1:
                        p.moveTo(glass_x + 1*mm, glass_y + 1*mm)
                        p.lineTo(glass_x + glass_w - 1*mm, cy)
                        p.lineTo(glass_x + 1*mm, glass_y + glass_h - 1*mm)
                    elif i == 0:
                        # left leaf hinges on left, handle on right meeting stile
                        p.moveTo(glass_x + 1*mm, glass_y + 1*mm)
                        p.lineTo(glass_x + glass_w - 0.5*mm, cy)
                        p.lineTo(glass_x + 1*mm, glass_y + glass_h - 1*mm)
                        # handle on meeting stile
                        c.setFillColor(HANDLEC)
                        c.rect(glass_x + glass_w - 1.2*mm, cy - 2.5*mm, 1.0*mm, 5.0*mm, stroke=0, fill=1)
                    else:
                        # right leaf hinges on right, handle on left meeting stile
                        p.moveTo(glass_x + glass_w - 1*mm, glass_y + 1*mm)
                        p.lineTo(glass_x + 0.5*mm, cy)
                        p.lineTo(glass_x + glass_w - 1*mm, glass_y + glass_h - 1*mm)
                        # handle on meeting stile
                        c.setFillColor(HANDLEC)
                        c.rect(glass_x + 0.2*mm, cy - 2.5*mm, 1.0*mm, 5.0*mm, stroke=0, fill=1)
                    c.drawPath(p, fill=0, stroke=1)
                    c.restoreState()

        if self.cat in ("Βιτρίνα", "Ντουλάπα") and gw > 0 and gh > 3 * mt:
            c.setFillColor(FRAMEC)
            by = (gy + gh / 2.0 - mt / 2.0) if self.cat == "Βιτρίνα" else (gy + gh * 0.80)
            c.rect(gx, by, gw, mt, stroke=0, fill=1)

        if f["door"] and gw > 5*mm and gh > 6*mm:
            c.setFillColor(HANDLEC)
            hw = max(0.7*mm, mt * 0.5)
            hx = x0 + iw - ft - max(2.2*mm, gw * 0.10)
            c.rect(hx, gy + gh * 0.42, hw, min(11*mm, gh * 0.22), stroke=0, fill=1)

        c.setStrokeColor(FRAMEDK)
        c.setLineWidth(0.85)
        c.rect(x0, y0, iw, ih, stroke=1, fill=0)

        if not self.show_labels:
            return

        # dimensions (small, outside)
        c.setStrokeColor(DIMC)
        c.setLineWidth(0.45)
        c.setFillColor(DIMC)
        top_y = y0 + ih + (self.shutter_h if f["shutter"] else 0) + 2.2*mm
        if top_y + 3*mm < self.BOX_H:
            c.line(x0, top_y, x0 + iw, top_y)
            for xx in (x0, x0 + iw):
                c.line(xx, top_y - 0.9*mm, xx, top_y + 0.9*mm)
            c.setFont(FONT, 6.5)
            c.drawCentredString(x0 + iw / 2.0, top_y + 1.2*mm, self.w_txt)
        lx = x0 - 2.3*mm
        c.line(lx, y0, lx, y0 + ih)
        for yy in (y0, y0 + ih):
            c.line(lx - 0.9*mm, yy, lx + 0.9*mm, yy)
        c.saveState()
        c.setFont(FONT, 6.5)
        c.translate(lx - 1.5*mm, y0 + ih / 2.0)
        c.rotate(90)
        c.drawCentredString(0, 0, self.h_txt)
        c.restoreState()

        cap = self.location
        if cap:
            cap = f"Τοποθέτηση: {cap}"
        else:
            cap = self.label
        c.setFont(FONT, 6.5)
        c.setFillColor(CAPTIONC)
        c.drawCentredString(self.BOX_W / 2.0, 1.6*mm, cap[:42])

class ScaledFlowable(Flowable):
    """Draw another flowable scaled down to fit a maximum box (PDF thumbnails)."""

    def __init__(self, flowable, max_w, max_h):
        Flowable.__init__(self)
        self.flowable = flowable
        self.max_w = max_w
        self.max_h = max_h
        self.scale = 1.0
        self.width = 0
        self.height = 0

    def wrap(self, aW=None, aH=None):
        w, h = self.flowable.wrap(aW, aH)
        if w > 0 and h > 0:
            self.scale = min(self.max_w / w, self.max_h / h)
        self.width = w * self.scale
        self.height = h * self.scale
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.saveState()
        c.scale(self.scale, self.scale)
        self.flowable.drawOn(c, 0, 0)
        c.restoreState()

class DimensionedBox(Flowable):
    """Image/schematic with architectural width/height dimension arrows and cm labels."""

    def __init__(self, content, w_cm, h_cm, box_w, box_h, label_font=5.8):
        Flowable.__init__(self)
        self.content = content
        self.w_cm = w_cm
        self.h_cm = h_cm
        self.width = box_w
        self.height = box_h
        self.label_font = label_font

    def wrap(self, aW=None, aH=None):
        return self.width, self.height

    @staticmethod
    def _arrow_h(c, x, y, direction):
        s = 1.15*mm
        p = c.beginPath()
        p.moveTo(x, y)
        p.lineTo(x - direction * s, y + s * 0.55)
        p.lineTo(x - direction * s, y - s * 0.55)
        p.close()
        c.drawPath(p, fill=1, stroke=0)

    @staticmethod
    def _arrow_v(c, x, y, direction):
        s = 1.15*mm
        p = c.beginPath()
        p.moveTo(x, y)
        p.lineTo(x - s * 0.55, y - direction * s)
        p.lineTo(x + s * 0.55, y - direction * s)
        p.close()
        c.drawPath(p, fill=1, stroke=0)

    def draw(self):
        c = self.canv
        ml = 7.5*mm
        mt = 5.5*mm
        mr = 1.0*mm
        mb = 1.0*mm
        cw = max(1.0, self.width - ml - mr)
        ch = max(1.0, self.height - mt - mb)
        cx, cy = ml, mb

        if self.content is not None:
            cw_c, ch_c = self.content.wrap(cw, ch)
            ox = cx + (cw - cw_c) / 2.0
            oy = cy + (ch - ch_c) / 2.0
            c.saveState()
            self.content.drawOn(c, ox, oy)
            c.restoreState()
            left, bottom, right, top = ox, oy, ox + cw_c, oy + ch_c
        else:
            left, bottom, right, top = cx, cy, cx + cw, cy + ch

        dimc = colors.HexColor("#475569")
        c.setStrokeColor(dimc)
        c.setFillColor(dimc)
        c.setLineWidth(0.45)

        # Width dimension above the frame.
        hy = top + 2.0*mm
        c.line(left, hy, right, hy)
        c.line(left, top, left, hy + 0.8*mm)
        c.line(right, top, right, hy + 0.8*mm)
        self._arrow_h(c, left, hy, -1)
        self._arrow_h(c, right, hy, 1)
        c.setFont(FONT, self.label_font)
        c.drawCentredString((left + right) / 2.0, hy + 1.0*mm, f"{self.w_cm:g} εκ.")

        # Height dimension left of the frame.
        vx = left - 2.2*mm
        c.line(vx, bottom, vx, top)
        c.line(left, bottom, vx - 0.8*mm, bottom)
        c.line(left, top, vx - 0.8*mm, top)
        self._arrow_v(c, vx, bottom, -1)
        self._arrow_v(c, vx, top, 1)
        c.saveState()
        c.translate(vx - 1.5*mm, (bottom + top) / 2.0)
        c.rotate(90)
        c.drawCentredString(0, 0, f"{self.h_cm:g} εκ.")
        c.restoreState()

def schematic_for(d, show_labels=True):
    """Schematic αν η γραμμή έχει αριθμητικές διαστάσεις, αλλιώς None."""
    w = _num(d.get("width"))
    h = _num(d.get("height"))
    if not w or not h or w <= 0 or h <= 0:
        return None
    try:
        k = min(1.0, 20000.0 / max(w, h))
        wt = str(d.get("width") or "").strip()[:12]
        ht = str(d.get("height") or "").strip()[:12]
        return Schematic(
            w * k, h * k, resolved_category(d),
            w_txt=wt, h_txt=ht,
            name=d.get("name", "") or "",
            descr=d.get("descr", "") or "",
            location=d.get("location", "") or "",
            show_labels=show_labels,
        )
    except Exception:
        return None

def _footer(canvas, doc):
    canvas.saveState()
    try:
        comp = get_company()
        line = f"{comp.get('name','')}  •  {comp.get('phone','')}  •  {comp.get('email','')}"
        canvas.setFont(FONT, 7.5)
        canvas.setFillColor(colors.HexColor("#94a3b8"))
        canvas.drawString(18*mm, 12*mm, line[:130])
        canvas.drawRightString(A4[0]-18*mm, 12*mm, f"Σελίδα {doc.page}")
        canvas.setStrokeColor(colors.HexColor("#e2e8f0"))
        canvas.setLineWidth(0.6)
        canvas.line(18*mm, 14.2*mm, A4[0]-18*mm, 14.2*mm)
    except Exception:
        pass
    canvas.restoreState()

def make_pdf(q, filepath):
    comp = get_company()
    items = json.loads(q["items_json"]) if isinstance(q.get("items_json"), str) else (q.get("items_json") or [])
    dj = q.get("designs_json", "[]")
    designs = json.loads(dj) if isinstance(dj, str) else (dj or [])
    doc = SimpleDocTemplate(filepath, pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm, topMargin=14*mm, bottomMargin=16*mm,
        title="Προσφορά")
    st_title = ParagraphStyle('t', fontName=FONTB, fontSize=20, textColor=BLUE, leading=24)
    st_h = ParagraphStyle('h', fontName=FONTB, fontSize=11, textColor=BLUE, leading=14)
    st_n = ParagraphStyle('n', fontName=FONT, fontSize=9.5, textColor=DARK, leading=13)
    st_small = ParagraphStyle('s', fontName=FONT, fontSize=8.5, textColor=colors.grey, leading=11)
    st_cell = ParagraphStyle('c', fontName=FONT, fontSize=9, leading=12)
    st_cell_small = ParagraphStyle('cs', fontName=FONT, fontSize=7.5, leading=10, textColor=DARK)
    st_cellb = ParagraphStyle('cb', fontName=FONTB, fontSize=9, leading=12)
    st_cellh = ParagraphStyle('ch', fontName=FONTB, fontSize=9, leading=12, textColor=colors.white)
    st_right = ParagraphStyle('r', fontName=FONT, fontSize=10, leading=14, alignment=2)
    st_total = ParagraphStyle('rt', fontName=FONTB, fontSize=13, leading=16, alignment=2, textColor=colors.white)
    st_d = ParagraphStyle('d', fontName=FONT, fontSize=9, leading=12, textColor=DARK)
    st_cardh = ParagraphStyle('cardh', fontName=FONTB, fontSize=9, leading=12, textColor=colors.white)
    st_th2 = ParagraphStyle('th2', fontName=FONTB, fontSize=7.5, leading=10, textColor=colors.HexColor("#334155"))
    st_td2 = ParagraphStyle('td2', fontName=FONT, fontSize=8, leading=11, textColor=DARK)
    st_spec = ParagraphStyle('spec', fontName=FONT, fontSize=7.5, leading=10, textColor=colors.HexColor("#1e293b"))
    st_price = ParagraphStyle('pr', fontName=FONTB, fontSize=14, leading=18, alignment=2, textColor=PRICEGR)
    st_cell_c = ParagraphStyle('cc', parent=st_cell, alignment=1)
    st_cell_r = ParagraphStyle('cr', parent=st_cell, alignment=2)
    st_cellb_r = ParagraphStyle('cbr', parent=st_cellb, alignment=2, textColor=PRICEGR)

    story = []
    logo = get_logo()
    head_info = (f"<font size=20 color=\"#1a56db\"><b>{esc(comp.get('name',''))}</b></font><br/>"
        f"{esc(comp.get('address',''))} &nbsp;&nbsp;|&nbsp;&nbsp; Τηλ: {esc(comp.get('phone',''))}<br/>"
        f"Email: {esc(comp.get('email',''))} &nbsp;&nbsp;|&nbsp;&nbsp; ΑΦΜ: {esc(comp.get('afm',''))} &nbsp;&nbsp; ΔΟΥ: {esc(comp.get('doy',''))}")
    if logo:
        lim = pdf_image(logo, max_w=38*mm, max_h=26*mm)
        ht = Table([[lim, Paragraph(head_info, st_small)]], colWidths=[42*mm, 128*mm])
        ht.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]))
        story.append(ht)
    else:
        story.append(Paragraph(esc(comp.get("name", "")), st_title))
        story.append(Paragraph(
            f"{esc(comp.get('address',''))} &nbsp;&nbsp;|&nbsp;&nbsp; Τηλ: {esc(comp.get('phone',''))}<br/>"
            f"Email: {esc(comp.get('email',''))} &nbsp;&nbsp;|&nbsp;&nbsp; ΑΦΜ: {esc(comp.get('afm',''))} &nbsp;&nbsp; ΔΟΥ: {esc(comp.get('doy',''))}", st_small))
    story.append(HRFlowable(width="100%", thickness=1.2, color=BLUE, spaceAfter=8, spaceBefore=4))

    include_labor = bool(q.get("include_labor"))
    labor_amt = float(q.get("labor_amount") or 0)
    labor_desc = str(q.get("labor_desc") or "").strip() or "Εργασία & Τοποθέτηση κουφωμάτων"
    subtotal_val = float(q.get("subtotal") or 0)

    offer_type_txt = "ΚΟΥΦΩΜΑΤΑ & ΤΟΠΟΘΕΤΗΣΗ" if (include_labor and labor_amt > 0) else "ΚΟΥΦΩΜΑΤΑ & ΥΛΙΚΑ"
    cust_left = (f"<font size=8 color='#64748b'><b>ΣΤΟΙΧΕΙΑ ΠΕΛΑΤΗ:</b></font><br/>"
                 f"<font size=11 color='#0f172a'><b>{esc(q['customer_name'])}</b></font><br/>"
                 f"<font size=9 color='#334155'>{esc(q.get('customer_info',''))}</font>")
    meta_right = (f"<font size=9 color='#0f172a'>"
                  f"<b>ΗΜΕΡΟΜΗΝΙΑ:</b> {esc(q['date'])}<br/>"
                  f"<b>ΕΙΔΟΣ:</b> <font color='#1a56db'><b>{offer_type_txt}</b></font>"
                  f"</font>")
    cust = Table([[Paragraph(cust_left, st_n), Paragraph(meta_right, ParagraphStyle('mr', fontName=FONT, fontSize=9, leading=13, alignment=2))]],
                 colWidths=[108*mm, 66*mm])
    cust.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), LIGHT_BG),
        ('ROUNDEDCORNERS', [6, 6, 6, 6]),
        ('BOX', (0, 0), (-1, -1), 0.6, colors.HexColor("#cbd5e1")),
        ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10), ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(cust)
    story.append(Spacer(1, 8))

    # Separate items: if designs exist, filter out items that are already shown as design cards
    design_names = {str(d.get("name") or "").strip().lower() for d in designs}
    design_codes = {str(d.get("code") or "").strip().lower() for d in designs if str(d.get("code") or "").strip()}
    
    loose_items = []
    if designs:
        for it in items:
            it_name = str(it.get("name") or "").strip()
            it_lower = it_name.lower()
            is_des = any(c and c in it_lower for c in design_codes) or any(n and n in it_lower for n in design_names if n != "κούφωμα")
            if not is_des and not it_name.startswith("📐"):
                loose_items.append(it)
    else:
        loose_items = items

    labor_row_needed = include_labor and labor_amt > 0
    labor_desc_lines = [esc(l.strip()) for l in labor_desc.splitlines() if l.strip()]
    labor_desc_html = "<br/>".join(labor_desc_lines) or esc(labor_desc)

    design_img_cache = {}

    def design_image_name(d):
        """Image from the quote, or from the catalog by code/name if the quote has none."""
        img = str(d.get("image") or "").strip()
        if img and img_path(img):
            return img
        code = str(d.get("code") or "").strip()
        name = str(d.get("name") or "").strip()
        key = (code.lower(), name.lower())
        if key in design_img_cache:
            return design_img_cache[key]
        found = ""
        try:
            c = db()
            row = None
            if code:
                row = c.execute("SELECT image FROM designs WHERE code=? LIMIT 1", (code,)).fetchone()
            if not row and name:
                row = c.execute("SELECT image FROM designs WHERE LOWER(name)=LOWER(?) LIMIT 1", (name,)).fetchone()
            c.close()
            found = (row["image"] if row else "") or ""
        except Exception:
            found = ""
        design_img_cache[key] = found
        return found

    def labor_table_row():
        return [
            Paragraph("<font size=7 color='#475569'><b>ΕΡΓΑΣΙΑ</b></font>", st_cell_c),
            Paragraph(f"<b>ΕΡΓΑΣΙΑ &amp; ΤΟΠΟΘΕΤΗΣΗ</b><br/>"
                      f"<font size=7.5 color='#475569'>{labor_desc_html}</font>", st_n),
            Paragraph("1", st_cell_c),
            Paragraph("έργο", st_cell_c),
            Paragraph(fmt(labor_amt), st_cell_r),
            Paragraph(f"<b>{fmt(labor_amt)}</b>", st_cellb_r),
        ]

    if designs:
        prod_rows = [
            [Paragraph("<b>ΚΟΥΦΩΜΑΤΑ &amp; ΚΑΤΑΣΚΕΥΕΣ</b>", st_cellh), "", "", "", "", ""],
            [Paragraph("<b>Εικόνα</b>", st_cellh), Paragraph("<b>Υλικό / Εργασία</b>", st_cellh),
             Paragraph("<b>Ποσ.</b>", st_cellh), Paragraph("<b>Μον.</b>", st_cellh),
             Paragraph("<b>Τιμή μον.</b>", st_cellh), Paragraph("<b>Σύνολο</b>", st_cellh)],
        ]
        tstyle = [
            ('SPAN', (0, 0), (5, 0)),
            ('BACKGROUND', (0, 0), (5, 0), HEADBAR),
            ('BACKGROUND', (0, 1), (5, 1), BLUE),
            ('TOPPADDING', (0, 0), (5, 0), 5),
            ('BOTTOMPADDING', (0, 0), (5, 0), 5),
            ('LEFTPADDING', (0, 0), (5, 0), 8),
            ('BOX', (0, 0), (-1, -1), 0.6, colors.HexColor("#cbd5e1")),
            ('ROUNDEDCORNERS', [6, 6, 6, 6]),
            ('VALIGN', (0, 1), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 1), (0, -1), 'CENTER'),
            ('TOPPADDING', (0, 1), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
            ('LEFTPADDING', (0, 1), (-1, -1), 6),
            ('RIGHTPADDING', (0, 1), (-1, -1), 8),
        ]
        for idx, d in enumerate(designs, start=1):
            pth = img_path(design_image_name(d))
            w_cm, h_cm = dims_cm_values(d.get("width"), d.get("height"))
            im = pdf_image(pth, max_w=20*mm, max_h=17*mm) if pth else None
            if im:
                content = im
            else:
                sch = schematic_for(d, show_labels=False)
                content = ScaledFlowable(sch, 20*mm, 17*mm) if sch else None
            if content is not None and w_cm and h_cm:
                art = DimensionedBox(content, w_cm, h_cm, 29*mm, 25*mm)
            elif content is not None:
                art = content
            else:
                art = Paragraph(
                    "<font size=10 color='#cbd5e1'>▢</font>",
                    ParagraphStyle('art_c', fontName=FONT, alignment=1))
            try:
                dq = float(d.get("qty", 1) or 1)
            except Exception:
                dq = 1
            code = str(d.get("code") or "").strip()
            raw_name = str(d.get("name") or "").strip() or "Κούφωμα"
            title_txt = f"{idx}. {raw_name.upper()}"
            code_html = f" <font size=8 color='#64748b'>({esc(code)})</font>" if code else ""
            location_str = str(d.get("location") or "").strip()
            series = str(d.get("series") or d.get("category") or "—").strip() or "—"
            color = str(d.get("color") or "—").strip() or "—"
            dim_txt = dims_meters_txt(d.get("width"), d.get("height"))

            clean_lines = [esc(l.strip()) for l in str(d.get("descr") or "").splitlines() if l.strip()]
            desc_inline = " • ".join(clean_lines[:2])

            mid_parts = [
                f"<font size=9.5 color='#0f172a'><b>{esc(title_txt)}</b>{code_html}</font>" +
                (f"<br/><font size=8.5 color='#1d4ed8'><b>• Τοποθέτηση: {esc(location_str)}</b></font>" if location_str else ""),
                f"<font size=8 color='#475569'>Σειρά: <b>{esc(series)}</b></font>",
                f"<font size=8 color='#475569'>Χρώμα: <b>{esc(color)}</b> &nbsp;|&nbsp; Διαστάσεις: <b>{esc(dim_txt)}</b></font>"
            ]
            if desc_inline:
                mid_parts.append(f"<font size=7.5 color='#64748b'>{desc_inline}</font>")
            mid_html = "<br/>".join(mid_parts)

            try:
                unit_price = float(d.get("price", 0) or 0)
            except Exception:
                unit_price = 0
            
            tot_price = unit_price * dq
            unit_txt = str(d.get("unit") or "τεμ.").strip() or "τεμ."

            prod_rows.append([
                art,
                Paragraph(mid_html, st_n),
                Paragraph(f"{dq:g}", st_cell_c),
                Paragraph(esc(unit_txt), st_cell_c),
                Paragraph(fmt(unit_price), st_cell_r),
                Paragraph(f"<b>{fmt(tot_price)}</b>", st_cellb_r),
            ])
            r_idx = len(prod_rows) - 1
            bg_col = colors.white if r_idx % 2 == 1 else LIGHT_BG
            tstyle.append(('BACKGROUND', (0, r_idx), (-1, r_idx), bg_col))
            if r_idx > 1:
                tstyle.append(('LINEABOVE', (0, r_idx), (-1, r_idx), 0.4, colors.HexColor("#e2e8f0")))

        if labor_row_needed:
            prod_rows.append(labor_table_row())
            r_idx = len(prod_rows) - 1
            tstyle.append(('BACKGROUND', (0, r_idx), (-1, r_idx), colors.HexColor("#f0fdf4")))
            tstyle.append(('LINEABOVE', (0, r_idx), (-1, r_idx), 0.4, colors.HexColor("#e2e8f0")))

        prod_table = Table(prod_rows, colWidths=[34*mm, 64*mm, 14*mm, 14*mm, 24*mm, 24*mm], repeatRows=2)
        prod_table.setStyle(TableStyle(tstyle))
        story.append(prod_table)
        story.append(Spacer(1, 8))

    if loose_items:
        sec_title = "ΣΥΜΠΛΗΡΩΜΑΤΙΚΑ ΥΛΙΚΑ / ΠΑΡΕΛΚΟΜΕΝΑ" if designs else "ΑΝΑΛΥΤΙΚΗ ΠΡΟΣΦΟΡΑ ΥΛΙΚΩΝ"
        story.append(Paragraph(sec_title, st_h))
        story.append(Spacer(1, 4))
        data = [[Paragraph("<b>Εικόνα</b>", st_cellh), Paragraph("<b>Υλικό / Εργασία</b>", st_cellh), Paragraph("<b>Ποσ.</b>", st_cellh),
                 Paragraph("<b>Μον.</b>", st_cellh), Paragraph("<b>Τιμή μον.</b>", st_cellh),
                 Paragraph("<b>Σύνολο</b>", st_cellh)]]
        for it in loose_items:
            qty = float(it.get("qty", 0)); pr = float(it.get("price", 0))
            item_name = str(it.get("name", "")).lower()
            
            # Try to find a matching thumbnail image based on keywords
            img_cell = None
            thumb_files = os.listdir(IMG_DIR) if os.path.exists(IMG_DIR) else []
            matched_img = None
            
            # Priority matching based on item name keywords (Greek and English)
            if "shutter" in item_name and "screen" in item_name:
                matched_img = "thumb_s350_shutter_screen.png"
            elif "shutter" in item_name:
                matched_img = "thumb_m9660_casement_shutter.png"
            elif "screen" in item_name or "σίτα" in item_name:
                matched_img = "thumb_s350_screen.png"
            elif "door" in item_name or "πόρτα" in item_name:
                matched_img = "thumb_door.png"
            elif "fixed" in item_name or "σταθερό" in item_name:
                matched_img = "thumb_fixed.png"
            elif "casement" in item_name or "επάλληλο" in item_name:
                matched_img = "thumb_m9660_single_casement.png"
            elif "sliding" in item_name or "συρόμενο" in item_name:
                matched_img = "thumb_s350_simple.png"
            elif "transom" in item_name:
                matched_img = "thumb_m9660_transom.png"
            elif "europa" in item_name or "hybrid" in item_name:
                matched_img = "thumb_s350_simple.png"
            elif "διφυλλο" in item_name or "επαλληλο" in item_name:
                matched_img = "thumb_m9660_single_casement.png"
            
            # Fallback: try to find any matching file if priority didn't work
            if not matched_img and thumb_files:
                for thumb in thumb_files:
                    thumb_lower = thumb.lower()
                    if any(kw in item_name for kw in ["shutter", "screen", "door", "fixed", "casement", "sliding", "transom", "europa", "hybrid", "δίφυλλο", "επαλληλο", "σίτα", "πόρτα", "σταθερό", "συρόμενο"]):
                        if kw in thumb_lower:
                            matched_img = thumb
                            break
            
            if matched_img and matched_img in thumb_files:
                img_path_full = os.path.join(IMG_DIR, matched_img)
                img = pdf_image(img_path_full, max_w=20*mm, max_h=18*mm)
                img_cell = img
            else:
                img_cell = Paragraph("<font size=10 color='#cbd5e1'>▢</font>", ParagraphStyle('noimg', fontName=FONT, alignment=1))
            
            # Use the full description as-is
            desc_html = f"<font size=7.5 color='#0f172a'>{esc(it.get('name', ''))}</font>"
            
            data.append([
                img_cell,
                Paragraph(desc_html, st_cell_small),
                Paragraph(str(qty).rstrip("0").rstrip(".") if "." in str(qty) else str(qty), st_cell),
                Paragraph(esc(it.get("unit", "")), st_cell),
                Paragraph(fmt(pr), st_cell),
                Paragraph(fmt(qty*pr), st_cell),
            ])
        if labor_row_needed and not designs:
            data.append(labor_table_row())
        t = Table(data, colWidths=[22*mm, 68*mm, 14*mm, 14*mm, 28*mm, 28*mm], repeatRows=1)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), BLUE),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (2, 0), (-1, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(t)
        story.append(Spacer(1, 8))

    # Καθαρή αξία, ΦΠΑ και τέλος τιμή — ομαδοποιημένα σε έναν ενωμένο πίνακα
    totals = []
    totals.append([Paragraph("<b>Καθαρή Αξία (χωρίς ΦΠΑ):</b>", st_right), Paragraph(f"<b>{fmt(subtotal_val)}</b>", st_right)])
    totals.append([Paragraph(f"ΦΠΑ {q['vat_rate']}%:", st_right), Paragraph(fmt(q["vat_amount"]), st_right)])
    totals.append([Paragraph("ΣΥΝΟΛΟ ΜΕ ΦΠΑ", ParagraphStyle('rt_lbl', fontName=FONTB, fontSize=12, textColor=colors.white, alignment=2)),
                      Paragraph(fmt(q["total"]), ParagraphStyle('rt_val', fontName=FONTB, fontSize=13, leading=16, alignment=2, textColor=colors.white))])
    tt = Table(totals, colWidths=[114*mm, 60*mm])
    tt.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('BACKGROUND', (0, 0), (-1, -2), LIGHT_BG),
        ('BACKGROUND', (0, -1), (-1, -1), BLUE),
        ('BOX', (0, 0), (-1, -1), 0.6, colors.HexColor("#cbd5e1")),
        ('ROUNDEDCORNERS', [6, 6, 6, 6]),
        ('LINEBELOW', (0, -2), (-1, -2), 0.4, colors.HexColor("#cbd5e1")),
    ]))
    story.append(tt)
    story.append(Spacer(1, 10))
    if q.get("notes"):
        story.append(Paragraph("<b>Παρατηρήσεις:</b>", st_n))
        story.append(Paragraph(esc(q["notes"]), st_n))
        story.append(Spacer(1, 6))
    story.append(Paragraph(esc(comp.get("notes", "")), st_small))
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return filepath

# ================= APP =================
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"AluminaOffers v{__version__}")
        self.geometry("1220x740")
        self.minsize(1060, 660)
        self._catalog_tab = "Σχέδια"
        self._thumbs = []
        self._logo_img = None
        self.sidebar = ctk.CTkFrame(self, width=230, corner_radius=0, fg_color=NAVY)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        brand = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        brand.pack(pady=(20, 4), padx=16, fill="x")
        self._brand_img_label = ctk.CTkLabel(brand, text="")
        self._brand_img_label.pack(anchor="w")
        self._brand_img = None
        self._brand_name = ctk.CTkLabel(brand, text="AluminaOffers", font=("Arial", 17, "bold"),
                                       text_color="white", anchor="w")
        self._brand_name.pack(anchor="w")
        ctk.CTkLabel(brand, text=f"Προσφορές αλουμινάδων • v{__version__}", font=("Arial", 11),
                     text_color="#93c5fd", anchor="w").pack(anchor="w", pady=(0, 14))
        self.nav_btns = {}
        for key, txt in [("home", "🏠  Αρχική"), ("new", "➕  Νέα Προσφορά"),
                         ("catalog", "📚  Κατάλογος"), ("settings", "⚙️  Στοιχεία & Λογότυπο")]:
            b = ctk.CTkButton(self.sidebar, text=txt, anchor="w", font=("Arial", 15),
                              fg_color="transparent", hover_color="#1e3a8a",
                              text_color="white", height=48, corner_radius=10,
                              command=lambda k=key: self.show(k))
            b.pack(fill="x", padx=12, pady=3)
            self.nav_btns[key] = b
        ctk.CTkButton(self.sidebar, text="＋ ΝΕΑ ΠΡΟΣΦΟΡΑ", font=("Arial", 15, "bold"),
                      height=50, corner_radius=12, fg_color=GREEN, hover_color="#15803d",
                      command=lambda: self.show("new")).pack(fill="x", padx=12, pady=(14, 4))
        self.main = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.main.pack(side="right", fill="both", expand=True)
        self.show("home")

    def _popup_setup(self, win):
        """Ensure modal dialog pops up in front of the main window and grabs focus."""
        try:
            win.transient(self)
        except Exception:
            pass
        try:
            win.attributes("-topmost", True)
        except Exception:
            pass
        win.lift()
        win.focus_force()
        win.after(150, lambda: (
            (win.attributes("-topmost", False) if win.winfo_exists() else None),
            (win.lift() if win.winfo_exists() else None),
            (win.focus_force() if win.winfo_exists() else None),
            (win.grab_set() if win.winfo_exists() else None)
        ) if win.winfo_exists() else None)

    def clear(self):
        for w in self.main.winfo_children():
            w.destroy()
        self._thumbs = []

    def show(self, key):
        for k, b in self.nav_btns.items():
            b.configure(fg_color="#1e3a8a" if k == key else "transparent")
        self.refresh_brand()
        self.clear()
        {"home": self.page_home, "new": self.page_new, "catalog": self.page_catalog,
         "settings": self.page_settings}[key]()

    def refresh_brand(self):
        """Λογότυπο + επωνυμία πάντα ορατά στο sidebar."""
        try:
            comp = get_company()
            name = comp.get("name", "").strip() or "AluminaOffers"
            self._brand_name.configure(text=name if len(name) <= 24 else name[:23] + "…")
            lg = get_logo()
            if lg:
                with PILImage.open(lg) as im:
                    w0, h0 = im.size
                s = min(170 / w0, 52 / h0, 1.0)
                self._brand_img = ctk.CTkImage(light_image=PILImage.open(lg),
                                              size=(max(1, int(w0*s)), max(1, int(h0*s))))
                self._brand_img_label.configure(text="", image=self._brand_img)
            else:
                self._brand_img = None
                self._brand_img_label.configure(text="◆", image=None,
                                                font=("Arial", 22, "bold"), text_color="white")
        except Exception:
            pass

    def card(self, parent, **kw):
        f = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=16,
                         border_width=1, border_color="#e2e8f0", **kw)
        f.pack(fill="x", padx=18, pady=8)
        return f

    def section(self, parent, txt, sub=""):
        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.pack(fill="x", padx=20, pady=(14, 2))
        ctk.CTkFrame(box, fg_color=BLUEH, width=5, height=24).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(box, text=txt, font=("Arial", 19, "bold"), text_color=TXTD).pack(side="left")
        if sub:
            ctk.CTkLabel(box, text=sub, font=("Arial", 12), text_color=TXTG).pack(side="left", padx=10)

    def stat_card(self, parent, label, value, accent=BLUEH):
        f = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=16,
                         border_width=1, border_color="#e2e8f0")
        f.pack(side="left", expand=True, fill="both", padx=6, pady=4)
        ctk.CTkFrame(f, fg_color=accent, height=4, corner_radius=2).pack(fill="x", padx=14, pady=(12, 0))
        ctk.CTkLabel(f, text=value, font=("Arial", 22, "bold"), text_color=TXTD).pack(anchor="w", padx=14, pady=(6, 0))
        ctk.CTkLabel(f, text=label, font=("Arial", 12), text_color=TXTG).pack(anchor="w", padx=14, pady=(0, 12))
        return f

    # ---------- ΑΡΧΙΚΗ / DASHBOARD ----------
    def page_home(self):
        comp = get_company()
        st = quote_stats()
        top = ctk.CTkFrame(self.main, fg_color="transparent")
        top.pack(fill="x", padx=18, pady=(14, 2))
        lg = get_logo()
        if lg:
            try:
                with PILImage.open(lg) as im:
                    w0, h0 = im.size
                s = min(120 / w0, 56 / h0)
                self._logo_img = ctk.CTkImage(light_image=PILImage.open(lg), size=(int(w0*s), int(h0*s)))
                ctk.CTkLabel(top, text="", image=self._logo_img).pack(side="left", padx=(0, 12))
            except Exception:
                pass
        tbox = ctk.CTkFrame(top, fg_color="transparent")
        tbox.pack(side="left")
        ctk.CTkLabel(tbox, text=comp.get("name", "AluminaOffers"), font=("Arial", 22, "bold"),
                     text_color=TXTD, anchor="w").pack(anchor="w")
        ctk.CTkLabel(tbox, text=datetime.now().strftime("%A %d/%m/%Y"),
                     font=("Arial", 12), text_color=TXTG, anchor="w").pack(anchor="w")
        ctk.CTkButton(top, text="＋ ΝΕΑ ΠΡΟΣΦΟΡΑ", font=("Arial", 16, "bold"), height=52,
                      corner_radius=12, fg_color=GREEN, hover_color="#15803d",
                      command=lambda: self.show("new")).pack(side="right", padx=6)

        stats = ctk.CTkFrame(self.main, fg_color="transparent")
        stats.pack(fill="x", padx=12, pady=2)
        self.stat_card(stats, "Τζίρος μήνα (με ΦΠΑ)", fmt(st["rev_month"]))
        self.stat_card(stats, f"Προσφορές μήνα", str(st["n_month"]), ACCENT)
        self.stat_card(stats, "Τζίρος έτους (με ΦΠΑ)", fmt(st["rev_year"]), GREEN)
        self.stat_card(stats, "Μέση προσφορά", fmt(st["avg"]), "#f59e0b")

        cols = ctk.CTkFrame(self.main, fg_color="transparent")
        cols.pack(fill="both", expand=True, padx=12, pady=2)
        left = ctk.CTkFrame(cols, fg_color=CARD, corner_radius=16, border_width=1, border_color="#e2e8f0")
        left.pack(side="left", fill="both", expand=True, padx=6, pady=4)
        right = ctk.CTkFrame(cols, fg_color="transparent", width=300)
        right.pack(side="right", fill="y", padx=6, pady=4)
        right.pack_propagate(False)

        # τζίρος 6 μηνών
        ctk.CTkLabel(left, text="Τζίρος τελευταίων μηνών", font=("Arial", 14, "bold"),
                     text_color=TXTD).pack(anchor="w", padx=14, pady=(12, 4))
        mx = max([v for _, v in st["bars"]] + [1.0])
        for (y, m), v in st["bars"]:
            row = ctk.CTkFrame(left, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=2)
            ctk.CTkLabel(row, text=f"{GR_MONTHS[m]} {y}", font=("Arial", 12, "bold"),
                         text_color=TXTD, width=80).pack(side="left")
            bar = ctk.CTkProgressBar(row, height=12, corner_radius=6,
                                     progress_color=BLUEH, fg_color="#e2e8f0")
            bar.pack(side="left", fill="x", expand=True, padx=8)
            bar.set(v / mx if mx else 0)
            ctk.CTkLabel(row, text=fmt(v), font=("Arial", 12), text_color=TXTD, width=110,
                         anchor="e").pack(side="left")

        # γρήγορες ενέργειες
        ctk.CTkLabel(right, text="Γρήγορες ενέργειες", font=("Arial", 14, "bold"),
                     text_color=TXTD).pack(anchor="w", padx=4, pady=(4, 6))
        for txt, col, cmd in [
                ("📁 Φάκελος PDF (αποστολή)", ACCENT, lambda: open_path_safe(PDF_DIR)),
                ("📐 Νέο σχέδιο", BLUEH, lambda: (setattr(self, "_catalog_tab", "Σχέδια"), self.show("catalog"), self.design_dialog())),
                ("📥 Εισαγωγή σχεδίων", "#8b5cf6", lambda: (setattr(self, "_catalog_tab", "Σχέδια"), self.show("catalog"), self.bulk_import())),
                ("⚙️ Στοιχεία & λογότυπο", "#64748b", lambda: self.show("settings"))]:
            ctk.CTkButton(right, text=txt, font=("Arial", 13, "bold"), height=44,
                          corner_radius=10, fg_color=col, anchor="w",
                          command=cmd).pack(fill="x", pady=4)

        # προσφορές (λίστα με αναζήτηση)
        self.section(self.main, "Προσφορές", f"{st['n_total']} συνολικά — πάτα PDF για αποστολή")
        box = self.card(self.main)
        bar = ctk.CTkFrame(box, fg_color=CARD); bar.pack(fill="x", padx=12, pady=(10, 2))
        e_s = ctk.CTkEntry(bar, width=320, placeholder_text="🔍 Αναζήτηση πελάτη / αριθμού...",
                           font=("Arial", 13)); e_s.pack(side="left")
        ctk.CTkButton(bar, text="📁 Φάκελος PDF", fg_color=ACCENT, width=130,
                      command=lambda: open_path_safe(PDF_DIR)).pack(side="right")
        lst = ctk.CTkScrollableFrame(box, fg_color=CARD, height=210)
        lst.pack(fill="both", expand=True, padx=8, pady=8)

        def load(*_):
            for w in lst.winfo_children():
                w.destroy()
            q = e_s.get().strip().lower()
            c = db(); rows = c.execute("SELECT * FROM quotes ORDER BY id DESC").fetchall(); c.close()
            n = 0
            for r in rows:
                if q and q not in ((r["number"] or "") + " " + (r["customer_name"] or "")).lower():
                    continue
                n += 1
                ndes = 0
                try:
                    ndes = len(json.loads(r["designs_json"] or "[]"))
                except Exception:
                    pass
                row = ctk.CTkFrame(lst, fg_color=ROWB, corner_radius=10)
                row.pack(fill="x", pady=4, padx=2)
                ctk.CTkLabel(row, text=f"Νο {r['number']}  •  {r['customer_name']}",
                             font=("Arial", 13, "bold"), text_color=TXTD).pack(side="left", padx=10, pady=8)
                info = f"{r['date']}  •  {fmt(r['total'])}"
                if ndes:
                    info += f"  •  {ndes} σχέδια"
                ctk.CTkLabel(row, text=info, font=("Arial", 13), text_color=BLUEH).pack(side="left")
                ctk.CTkButton(row, text="PDF", width=64, command=lambda qq=dict(r): self.open_pdf(qq)).pack(side="right", padx=3, pady=6)
                ctk.CTkButton(row, text="📁 Φάκελος", width=85, fg_color="#0284c7", hover_color="#0369a1",
                              command=lambda qq=dict(r): self.open_quote_folder(qq)).pack(side="right", padx=3, pady=6)
                ctk.CTkButton(row, text="✕", width=32, fg_color=RED,
                              command=lambda i=r["id"]: self.del_quote(i)).pack(side="right", padx=3, pady=6)
            if n == 0:
                ctk.CTkLabel(lst, text="Καμία προσφορά — πάτα «ΝΕΑ ΠΡΟΣΦΟΡΑ»!",
                             font=("Arial", 13), text_color=TXTG).pack(pady=24)
        e_s.bind("<KeyRelease>", load)
        load()

    def del_quote(self, i):
        if messagebox.askyesno("Διαγραφή", "Να διαγραφεί η προσφορά;"):
            c = db(); c.execute("DELETE FROM quotes WHERE id=?", (i,)); c.commit(); c.close()
            self.show("home")

    def _ensure_pdf(self, q):
        """Regenerate the PDF so it always has the current layout, atomically."""
        num = safe_quote_number(q['number'])
        path = os.path.join(PDF_DIR, f"Prosfora_{num}.pdf")
        tmp = path + ".tmp"
        try:
            make_pdf(q, tmp)
            os.replace(tmp, path)
        except Exception:
            try:
                os.remove(tmp)
            except Exception:
                pass
            if not os.path.exists(path):
                raise
        return path

    def open_pdf(self, q):
        open_path_safe(self._ensure_pdf(q))

    def open_quote_folder(self, q):
        open_folder_and_select(self._ensure_pdf(q))

    # ---------- ΝΕΑ ΠΡΟΣΦΟΡΑ (μία οθόνη: γράψε -> PDF) ----------
    def page_new(self):
        self.section(self.main, "Νέα Προσφορά", "γράψε ελεύθερα → ένα κουμπί → PDF")
        c = db()
        custs = c.execute("SELECT * FROM customers ORDER BY name").fetchall()
        des = c.execute("SELECT * FROM designs ORDER BY code").fetchall()
        last = c.execute("SELECT number FROM quotes ORDER BY id DESC LIMIT 1").fetchone()
        c.close()
        try:
            nxt = str(int(last["number"]) + 1) if last and str(last["number"]).isdigit() else "1"
        except Exception:
            nxt = datetime.now().strftime("%Y%m%d%H%M")

        wrap = ctk.CTkScrollableFrame(self.main, fg_color=BG)
        wrap.pack(fill="both", expand=True)
        bind_scroll(wrap, wrap, recursive=False)

        top = self.card(wrap)
        f1 = ctk.CTkFrame(top, fg_color=CARD); f1.pack(fill="x", padx=14, pady=10)
        ctk.CTkLabel(f1, text="Νο:", font=("Arial", 13, "bold")).pack(side="left")
        e_num = ctk.CTkEntry(f1, width=80, font=("Arial", 14)); e_num.insert(0, nxt); e_num.pack(side="left", padx=6)
        ctk.CTkLabel(f1, text="Πελάτης:", font=("Arial", 13, "bold")).pack(side="left", padx=(10, 0))
        cb_cust = ctk.CTkComboBox(f1, values=[x["name"] for x in custs] if custs else [""], width=230, font=("Arial", 13))
        cb_cust.set("")
        cb_cust.pack(side="left", padx=6)
        e_phone = ctk.CTkEntry(f1, width=150, placeholder_text="Τηλέφωνο", font=("Arial", 13))
        e_phone.pack(side="left", padx=6)

        def on_cust(_):
            val = cb_cust.get().strip()
            r = next((dict(x) for x in custs if x["name"] == val), None)
            if r:
                e_phone.delete(0, "end"); e_phone.insert(0, r.get("phone", "") or "")
        cb_cust.configure(command=on_cust)
        ctk.CTkLabel(f1, text="ΦΠΑ %:", font=("Arial", 13, "bold")).pack(side="left", padx=(10, 0))
        e_vat = ctk.CTkEntry(f1, width=55, font=("Arial", 14)); e_vat.insert(0, str(DEFAULT_FPA)); e_vat.pack(side="left", padx=6)

        # Quick Bar / Δημοφιλή κουφώματα
        c = db()
        top_des = c.execute("""
            SELECT * FROM designs 
            ORDER BY COALESCE(use_count, 0) DESC, id ASC 
            LIMIT 5
        """).fetchall()
        c.close()

        if top_des:
            qbox = self.card(wrap)
            qhdr = ctk.CTkFrame(qbox, fg_color="transparent")
            qhdr.pack(fill="x", padx=14, pady=(8, 2))
            ctk.CTkLabel(qhdr, text="⚡ Δημοφιλή / Συχνά Κουφώματα (πατήστε εικόνα για άμεση προσθήκη):",
                         font=("Arial", 12, "bold"), text_color=TXTD).pack(side="left")
            qbar = ctk.CTkFrame(qbox, fg_color="transparent")
            qbar.pack(fill="x", padx=10, pady=(2, 10))

        mid = self.card(wrap)
        hdr = ctk.CTkFrame(mid, fg_color=CARD); hdr.pack(fill="x", padx=14, pady=(10, 0))
        for txt, w in [("Σχέδιο / Τύπος (πάτα για αναζήτηση)", 280), ("Π εκ.", 58),
                       ("Υ εκ.", 58), ("Τοποθέτηση", 125), ("Τεμ", 44), ("Τιμή €", 82), ("Σύνολο", 92), ("", 95)]:
            ctk.CTkLabel(hdr, text=txt, font=("Arial", 12, "bold"), width=w, text_color=TXTG).pack(side="left", padx=3)
        rowsbox = ctk.CTkFrame(mid, fg_color=CARD); rowsbox.pack(fill="x", padx=14, pady=4)
        rows = []
        active_row_ref = [None]  # Reference to currently active row for design picker

        # Πλαίσιο Εργασίας / Τοποθέτησης
        labor_box = ctk.CTkFrame(mid, fg_color="#f8fafc", corner_radius=10, border_width=1, border_color="#cbd5e1")
        labor_box.pack(fill="x", padx=14, pady=(6, 8))

        labor_var = ctk.BooleanVar(value=False)

        top_l = ctk.CTkFrame(labor_box, fg_color="transparent")
        top_l.pack(fill="x", padx=12, pady=(10, 4))

        def toggle_labor():
            active = labor_var.get()
            if active:
                e_labor_amt.configure(state="normal", fg_color="white")
                txt_labor_desc.configure(state="normal", fg_color="white")
            else:
                e_labor_amt.configure(state="disabled", fg_color="#e2e8f0")
                txt_labor_desc.configure(state="disabled", fg_color="#e2e8f0")
            refresh()

        cb_labor = ctk.CTkCheckBox(top_l, text="🛠️ Συμπερίληψη Κόστους Εργασίας / Τοποθέτησης",
                                   font=("Arial", 13, "bold"), text_color=TXTD,
                                   variable=labor_var, command=toggle_labor)
        cb_labor.pack(side="left")

        ctk.CTkLabel(top_l, text="Ποσό Εργασίας €:", font=("Arial", 13, "bold"), text_color=TXTD).pack(side="right", padx=(0, 4))
        e_labor_amt = ctk.CTkEntry(top_l, width=105, font=("Arial", 14, "bold"), placeholder_text="0")
        e_labor_amt.insert(0, "0")
        e_labor_amt.configure(state="disabled", fg_color="#e2e8f0")
        e_labor_amt.pack(side="right", padx=(0, 6))

        desc_l = ctk.CTkFrame(labor_box, fg_color="transparent")
        desc_l.pack(fill="x", padx=12, pady=(2, 10))

        ctk.CTkLabel(desc_l, text="Αναλυτική Περιγραφή Εργασιών (μπορείτε να γράψετε όσο αναλυτικά θέλετε):",
                     font=("Arial", 11, "bold"), text_color="#64748b").pack(anchor="w", pady=(0, 4))
        txt_labor_desc = ctk.CTkTextbox(desc_l, height=72, font=("Arial", 12))
        txt_labor_desc.insert("1.0", "Εργασία αποξήλωσης παλαιών κουφωμάτων & τοποθέτησης νέων")
        txt_labor_desc.configure(state="disabled", fg_color="#e2e8f0")
        txt_labor_desc.pack(fill="x")

        lbl_total = ctk.CTkLabel(mid, text="", font=("Arial", 13), text_color="#334155", justify="right")
        lbl_total.pack(anchor="e", padx=18)
        lbl_big = ctk.CTkLabel(mid, text="", font=("Arial", 20, "bold"), text_color=BLUEH)
        lbl_big.pack(anchor="e", padx=18, pady=(0, 6))

        def refresh():
            sub_mat = 0.0
            for row in rows:
                try:
                    q = float((row["e_q"].get() or "0").replace(",", "."))
                except Exception:
                    q = 0
                try:
                    p = float((row["e_p"].get() or "0").replace(",", "."))
                except Exception:
                    p = 0
                q = max(0.0, min(q, 100000)); p = max(0.0, min(p, 10000000))
                lt = q * p; sub_mat += lt
                row["l_sum"].configure(text=fmt(lt))

            labor_amt = 0.0
            if labor_var.get():
                try:
                    labor_amt = float((e_labor_amt.get() or "0").replace(",", "."))
                except Exception:
                    labor_amt = 0.0
                labor_amt = max(0.0, min(labor_amt, 10000000))

            sub = sub_mat + labor_amt
            try:
                vr = float(e_vat.get().replace(",", ".")) if e_vat.get() else DEFAULT_FPA
            except Exception:
                vr = DEFAULT_FPA
            vr = max(0.0, min(vr, 100.0))
            vat = sub * vr / 100

            if labor_var.get() and labor_amt > 0:
                lbl_total.configure(text=f"Υλικά: {fmt(sub_mat)}   •   Εργασία: {fmt(labor_amt)}   •   ΦΠΑ {vr:g}%: {fmt(vat)}")
            else:
                lbl_total.configure(text=f"Αρχική αξία: {fmt(sub)}      ΦΠΑ {vr:g}%: {fmt(vat)}")
            lbl_big.configure(text=f"ΣΥΝΟΛΟ ΜΕ ΦΠΑ: {fmt(sub + vat)}")
            return sub, vr, vat, sub + vat

        e_vat.bind("<KeyRelease>", lambda e: refresh())
        e_labor_amt.bind("<KeyRelease>", lambda e: refresh())

        def apply_design_to_row(row, d):
            active_row_ref[0] = row
            row["code"] = d.get("code", "")
            row["name"] = d.get("name", "")
            row["category"] = d.get("category", "") or ""
            row["series"] = d.get("series", "") or ""
            row["color"] = d.get("color", "") or ""
            row["descr"] = d.get("descr", "") or ""
            row["image"] = d.get("image", "") or ""

            if d.get("width"):
                row["e_w"].delete(0, "end"); row["e_w"].insert(0, str(d["width"]))
            if d.get("height"):
                row["e_h"].delete(0, "end"); row["e_h"].insert(0, str(d["height"]))
            if d.get("location"):
                row["e_loc"].delete(0, "end"); row["e_loc"].insert(0, str(d["location"]))
            if d.get("price"):
                try:
                    pr_val = float(d["price"])
                    row["e_p"].delete(0, "end")
                    row["e_p"].insert(0, str(int(pr_val) if pr_val == int(pr_val) else pr_val))
                except Exception:
                    pass

            try:
                _dm = d.get("materials_json", []) or []
                row["materials"] = json.loads(_dm) if isinstance(_dm, str) else list(_dm)
            except Exception:
                row["materials"] = []

            short_label = f"✔ {d.get('code','')} {d.get('name','')}".strip()
            if len(short_label) > 30:
                short_label = short_label[:29] + "…"
            row["b_des"].configure(text=short_label, fg_color=GREEN, hover_color="#15803d")
            refresh()

            # Increment use_count
            if d.get("id") or d.get("code"):
                try:
                    cc = db()
                    if d.get("id"):
                        cc.execute("UPDATE designs SET use_count = COALESCE(use_count, 0) + 1 WHERE id=?", (d["id"],))
                    else:
                        cc.execute("UPDATE designs SET use_count = COALESCE(use_count, 0) + 1 WHERE code=?", (d["code"],))
                    cc.commit(); cc.close()
                except Exception:
                    pass

        def quick_add(d):
            target = None
            if len(rows) == 1:
                r0 = rows[0]
                if r0["b_des"].cget("text") == "📐 Διάλεξε Σχέδιο..." and not r0["e_w"].get() and not r0["e_p"].get():
                    target = r0
            if not target:
                target = add_row()
            apply_design_to_row(target, d)
            target["e_w"].focus_set()

        if top_des:
            for td in top_des:
                tdd = dict(td)
                cnt = tdd.get("use_count", 0) or 0
                code = tdd.get("code", "")
                raw_n = tdd.get("name", "")
                name_short = (raw_n[:16] + "…") if len(raw_n) > 16 else raw_n
                ser = tdd.get("series", "") or tdd.get("category", "")
                ser_short = (ser[:14] + "…") if len(ser) > 14 else ser
                btn_txt = f" {code} {name_short}\n ★ {cnt}x  •  {ser_short}"

                pth = img_path(tdd.get("image"))
                ph = None
                if pth and os.path.exists(pth):
                    try:
                        with PILImage.open(pth) as im:
                            w0, h0 = im.size
                        s = min(64 / w0, 50 / h0)
                        ph = ctk.CTkImage(light_image=PILImage.open(pth), size=(max(24, int(w0 * s)), max(24, int(h0 * s))))
                        self._thumbs.append(ph)
                    except Exception:
                        ph = None

                ctk.CTkButton(
                    qbar, text=btn_txt, image=ph, compound="left",
                    font=("Arial", 11, "bold"),
                    height=56, fg_color="#1e293b", hover_color="#334155",
                    corner_radius=10, anchor="w",
                    command=lambda d=tdd: quick_add(d)
                ).pack(side="left", padx=4, pady=2, fill="x", expand=True)

        def pick_design(row):
            win = ctk.CTkToplevel(self)
            win.title("📐 Κατάλογος Κουφωμάτων & Σχεδίων")
            win.geometry("820x620")
            self._popup_setup(win)
            
            top_bar = ctk.CTkFrame(win, fg_color="transparent")
            top_bar.pack(fill="x", padx=14, pady=(12, 6))
            e_s = ctk.CTkEntry(top_bar, placeholder_text="🔍 Αναζήτηση (π.χ. επάλληλο, φεγγίτης, ρολό, S350, M9660, Europa)...",
                               font=("Arial", 14), height=38)
            e_s.pack(fill="x")

            cats_bar = ctk.CTkFrame(win, fg_color="transparent")
            cats_bar.pack(fill="x", padx=14, pady=(0, 6))
            active_cat = {"v": "Όλα"}
            cat_btns = []

            lst = ctk.CTkScrollableFrame(win, fg_color="#f8fafc", corner_radius=10, height=480)
            lst.pack(fill="both", expand=True, padx=14, pady=(0, 12))
            
            picker_thumbs = []

            def choose(d):
                apply_design_to_row(row, d)
                win.destroy()
                row["e_w"].focus_set()

            def fill(q=""):
                for w in lst.winfo_children():
                    w.destroy()
                picker_thumbs.clear()
                q = fold_el(q.strip())
                cat_filter = active_cat["v"]
                c = db()
                all_des = [dict(r) for r in c.execute("SELECT * FROM designs ORDER BY COALESCE(use_count, 0) DESC, id ASC").fetchall()]
                c.close()
                n = 0
                for d in all_des:
                    if cat_filter != "Όλα" and d.get("category") != cat_filter:
                        continue
                    blob = fold_el(" ".join([d.get("code") or "", d.get("name") or "", d.get("series") or "",
                                             d.get("category") or "", d.get("descr") or ""]))
                    if q and q not in blob:
                        continue
                    n += 1
                    card = ctk.CTkFrame(lst, fg_color="white", corner_radius=10, border_width=1, border_color="#e2e8f0")
                    card.pack(fill="x", pady=4, padx=4)

                    # Thumbnail
                    pth = img_path(d.get("image"))
                    if pth:
                        try:
                            with PILImage.open(pth) as im:
                                w0, h0 = im.size
                            s = min(95 / w0, 75 / h0)
                            ph = ctk.CTkImage(light_image=PILImage.open(pth), size=(max(20, int(w0 * s)), max(20, int(h0 * s))))
                            picker_thumbs.append(ph)
                            ctk.CTkLabel(card, text="", image=ph, width=105).pack(side="left", padx=8, pady=6)
                        except Exception:
                            ctk.CTkLabel(card, text="📐", font=("Arial", 22), width=105, text_color="#94a3b8").pack(side="left", padx=8, pady=6)
                    else:
                        ctk.CTkLabel(card, text="📐", font=("Arial", 22), width=105, text_color="#94a3b8").pack(side="left", padx=8, pady=6)

                    # Info
                    info = ctk.CTkFrame(card, fg_color="transparent")
                    info.pack(side="left", fill="both", expand=True, padx=6, pady=6)
                    
                    ctk.CTkLabel(info, text=f"{d.get('code','')} — {d.get('name','')}",
                                 font=("Arial", 13, "bold"), text_color=TXTD, anchor="w").pack(fill="x")
                    
                    sub = f"Σειρά: {d.get('series') or '—'}   •   Χρώμα: {d.get('color') or '—'}"
                    if d.get("width") and d.get("height"):
                        sub += f"   •   {d['width']}x{d['height']} εκ."
                    if d.get("use_count", 0) > 0:
                        sub += f"   •   ★ {d['use_count']} επιλογές"
                    ctk.CTkLabel(info, text=sub, font=("Arial", 11, "bold"), text_color=BLUEH, anchor="w").pack(fill="x", pady=(2, 2))
                    
                    specs_prev = " • ".join([line.strip() for line in (d.get("descr") or "").splitlines() if line.strip()][:2])
                    if specs_prev:
                        ctk.CTkLabel(info, text=specs_prev, font=("Arial", 10), text_color="#64748b", anchor="w").pack(fill="x")

                    # Select button
                    btn_frame = ctk.CTkFrame(card, fg_color="transparent")
                    btn_frame.pack(side="right", padx=10, pady=8)
                    if d.get("price"):
                        ctk.CTkLabel(btn_frame, text=fmt(d["price"]), font=("Arial", 12, "bold"), text_color=GREEN).pack(pady=(0, 4))
                    ctk.CTkButton(btn_frame, text="ΕΠΙΛΟΓΗ ➔", font=("Arial", 12, "bold"),
                                  fg_color="#16a34a", hover_color="#15803d", width=100, height=36,
                                  command=lambda dd=d: choose(dd)).pack()

                    def make_card_clickable(widget, target_d):
                        try:
                            widget.configure(cursor="hand2")
                        except Exception:
                            pass
                        widget.bind("<Button-1>", lambda ev, dd=target_d: choose(dd), add="+")
                        for ch in widget.winfo_children():
                            make_card_clickable(ch, target_d)

                    make_card_clickable(card, d)

                    def on_card_enter(ev, c=card):
                        try:
                            c.configure(fg_color="#eff6ff", border_color=BLUEH)
                        except Exception:
                            pass
                    def on_card_leave(ev, c=card):
                        try:
                            c.configure(fg_color="white", border_color="#e2e8f0")
                        except Exception:
                            pass
                    card.bind("<Enter>", on_card_enter)
                    card.bind("<Leave>", on_card_leave)
                if n == 0:
                    ctk.CTkLabel(lst, text="Δεν βρέθηκε σχέδιο με αυτή την αναζήτηση.", font=("Arial", 13), text_color=TXTG).pack(pady=40)

            def set_cat(c_val):
                active_cat["v"] = c_val
                for b, cv in cat_btns:
                    b.configure(fg_color=BLUEH if cv == c_val else "#e2e8f0",
                                text_color="white" if cv == c_val else TXTD)
                fill(e_s.get())

            for cv in ["Όλα", "Συρόμενο", "Παράθυρο", "Μπαλκονόπορτα", "Πόρτα", "Σταθερό"]:
                btn = ctk.CTkButton(cats_bar, text=cv, font=("Arial", 11, "bold"), height=26,
                                    fg_color=BLUEH if cv == "Όλα" else "#e2e8f0",
                                    text_color="white" if cv == "Όλα" else TXTD,
                                    command=lambda val=cv: set_cat(val))
                btn.pack(side="left", padx=2)
                cat_btns.append((btn, cv))

            e_s.bind("<KeyRelease>", lambda e: fill(e_s.get()))
            fill()

        def edit_details(row):
            win_ed = ctk.CTkToplevel(self)
            win_ed.title("⚙️ Προδιαγραφές & Υλικά Κουφώματος")
            win_ed.geometry("540x560")
            self._popup_setup(win_ed)
            
            pnl = ctk.CTkScrollableFrame(win_ed, fg_color="white")
            pnl.pack(fill="both", expand=True, padx=12, pady=12)

            ctk.CTkLabel(pnl, text="Σειρά Κουφώματος:", font=("Arial", 12, "bold")).pack(anchor="w")
            e_ser = ctk.CTkEntry(pnl, width=480, font=("Arial", 13))
            e_ser.insert(0, row.get("series", "") or "")
            e_ser.pack(pady=(2, 8))

            ctk.CTkLabel(pnl, text="Χρώμα:", font=("Arial", 12, "bold")).pack(anchor="w")
            e_col = ctk.CTkEntry(pnl, width=480, font=("Arial", 13))
            e_col.insert(0, row.get("color", "") or "")
            e_col.pack(pady=(2, 8))

            ctk.CTkLabel(pnl, text="Τοποθέτηση (π.χ. 1ος-ΓΩΝΙΑΚΟ, ΙΣΟΓΕΙΟ):", font=("Arial", 12, "bold")).pack(anchor="w")
            e_lc = ctk.CTkEntry(pnl, width=480, font=("Arial", 13))
            e_lc.insert(0, row["e_loc"].get().strip())
            e_lc.pack(pady=(2, 8))

            ctk.CTkLabel(pnl, text="Αναλυτικές Προδιαγραφές / Υλικά (όπως φαίνονται στο PDF):",
                         font=("Arial", 12, "bold")).pack(anchor="w")
            txt_box = ctk.CTkTextbox(pnl, width=480, height=160, font=("Arial", 12))
            txt_box.insert("1.0", row.get("descr", "") or "")
            txt_box.pack(pady=(2, 8))

            quick_bar = ctk.CTkFrame(pnl, fg_color="transparent")
            quick_bar.pack(fill="x", pady=(0, 10))
            def add_spec(text):
                cur = txt_box.get("1.0", "end").strip()
                if cur:
                    txt_box.insert("end", f"\n{text}")
                else:
                    txt_box.insert("1.0", text)

            ctk.CTkLabel(quick_bar, text="＋ Γρήγορη προσθήκη:", font=("Arial", 11, "bold"), text_color="#64748b").pack(side="left", padx=2)
            ctk.CTkButton(quick_bar, text="＋ Ρολό Ηλεκτρικό", font=("Arial", 11), height=24, fg_color="#0284c7",
                          command=lambda: add_spec("ΡΟΛΟ ΑΛΟΥΜΙΝΙΟΥ ΒΑΡΕΩΣ ΤΥΠΟΥ ΗΛΕΚΤΡΙΚΟ ΜΕ ΘΕΡΜΟΔΙΑΚΟΠΗ")).pack(side="left", padx=2)
            ctk.CTkButton(quick_bar, text="＋ Σίτα", font=("Arial", 11), height=24, fg_color="#0284c7",
                          command=lambda: add_spec("ΣΙΤΑ ΣΥΡΟΜΕΝΗ ΜΟΝΟΦΥΛΛΗ")).pack(side="left", padx=2)
            ctk.CTkButton(quick_bar, text="＋ Triplex", font=("Arial", 11), height=24, fg_color="#0284c7",
                          command=lambda: add_spec("ΥΑΛΟΠΙΝΑΚΕΣ 4 ΕΠΟΧΩΝ 4mm Planistar Evo-Argon-3+3 TRIPLEX")).pack(side="left", padx=2)

            def save_ed():
                row["series"] = e_ser.get().strip()
                row["color"] = e_col.get().strip()
                loc_val = e_lc.get().strip()
                row["e_loc"].delete(0, "end"); row["e_loc"].insert(0, loc_val)
                row["descr"] = txt_box.get("1.0", "end").strip()
                win_ed.destroy()

            ctk.CTkButton(pnl, text="💾 ΑΠΟΘΗΚΕΥΣΗ ΠΡΟΔΙΑΓΡΑΦΩΝ", font=("Arial", 13, "bold"),
                          fg_color=BLUEH, hover_color="#1e40af", height=38,
                          command=save_ed).pack(fill="x", pady=6)

        def del_row(row):
            rows.remove(row); row["frame"].destroy(); refresh()

        def dup_row(src):
            nr = add_row()
            nr["code"] = src.get("code", "")
            nr["name"] = src.get("name", "")
            nr["category"] = src.get("category", "")
            nr["series"] = src.get("series", "")
            nr["color"] = src.get("color", "")
            nr["descr"] = src.get("descr", "")
            nr["image"] = src.get("image", "")
            nr["materials"] = list(src.get("materials", []))
            nr["e_w"].delete(0, "end"); nr["e_w"].insert(0, src["e_w"].get())
            nr["e_h"].delete(0, "end"); nr["e_h"].insert(0, src["e_h"].get())
            nr["e_loc"].delete(0, "end"); nr["e_loc"].insert(0, src["e_loc"].get())
            nr["e_q"].delete(0, "end"); nr["e_q"].insert(0, src["e_q"].get())
            nr["e_p"].delete(0, "end"); nr["e_p"].insert(0, src["e_p"].get())
            if src["b_des"].cget("text") != "📐 Διάλεξε Σχέδιο...":
                nr["b_des"].configure(text=src["b_des"].cget("text"), fg_color=GREEN, hover_color="#15803d")
            refresh()
            nr["e_w"].focus_set()

        def add_row():
            r = ctk.CTkFrame(rowsbox, fg_color=ROWB, corner_radius=8)
            r.pack(fill="x", pady=3)
            
            b_des = ctk.CTkButton(r, text="📐 Διάλεξε Σχέδιο...", width=280, fg_color=ACCENT,
                                  font=("Arial", 12, "bold"), anchor="w")
            b_des.pack(side="left", padx=3, pady=6)
            
            e_w = ctk.CTkEntry(r, width=58, placeholder_text="Π", font=("Arial", 13)); e_w.pack(side="left", padx=3)
            e_h = ctk.CTkEntry(r, width=58, placeholder_text="Υ", font=("Arial", 13)); e_h.pack(side="left", padx=3)
            e_loc = ctk.CTkEntry(r, width=125, placeholder_text="Τοποθέτηση", font=("Arial", 12)); e_loc.pack(side="left", padx=3)
            e_q = ctk.CTkEntry(r, width=44, font=("Arial", 13)); e_q.insert(0, "1"); e_q.pack(side="left", padx=3)
            e_p = ctk.CTkEntry(r, width=82, placeholder_text="0", font=("Arial", 13)); e_p.pack(side="left", padx=3)
            
            l_sum = ctk.CTkLabel(r, text=fmt(0), font=("Arial", 12, "bold"), width=92, text_color=BLUEH)
            l_sum.pack(side="left", padx=3)
            
            row = {"frame": r, "b_des": b_des, "e_w": e_w, "e_h": e_h, "e_loc": e_loc,
                   "e_q": e_q, "e_p": e_p, "l_sum": l_sum, "code": "", "name": "", "series": "",
                   "color": "", "descr": "", "image": "", "category": "", "materials": []}
            
            b_des.configure(command=lambda: (active_row_ref.__setitem__(0, row), pick_design(row)))
            for e in (e_w, e_h, e_loc, e_q, e_p):
                e.bind("<KeyRelease>", lambda e: refresh())
                e.bind("<FocusIn>", lambda ev, rw=row: active_row_ref.__setitem__(0, rw))
                
            b_edit = ctk.CTkButton(r, text="⚙️", width=30, fg_color="#475569", hover_color="#334155",
                                   command=lambda: (active_row_ref.__setitem__(0, row), edit_details(row)))
            b_edit.pack(side="left", padx=2)
            
            b_dup = ctk.CTkButton(r, text="📋", width=30, fg_color="#0284c7", hover_color="#0369a1",
                                  command=lambda: dup_row(row))
            b_dup.pack(side="left", padx=2)
            
            b_del = ctk.CTkButton(r, text="✕", width=28, fg_color=RED, hover_color="#b91c1c",
                                  command=lambda: del_row(row))
            b_del.pack(side="left", padx=2)
            
            rows.append(row); refresh()
            active_row_ref[0] = row
            return row

        brow = ctk.CTkFrame(mid, fg_color=CARD); brow.pack(fill="x", padx=14, pady=(0, 8))
        def add_and_pick():
            target = None
            if len(rows) == 1 and rows[0]["b_des"].cget("text") == "📐 Διάλεξε Σχέδιο..." and not rows[0]["e_w"].get() and not rows[0]["e_p"].get():
                target = rows[0]
            if not target:
                target = add_row()
            pick_design(target)

        ctk.CTkButton(brow, text="📐 ΔΙΑΛΕΞΕ & ΠΡΟΣΘΕΣΕ ΚΟΥΦΩΜΑ", font=("Arial", 13, "bold"),
                      fg_color=GREEN, hover_color="#15803d", command=add_and_pick).pack(side="left", padx=(0, 6))
        ctk.CTkButton(brow, text="＋ Κενή γραμμή", font=("Arial", 12),
                      fg_color="#64748b", hover_color="#475569", command=add_row).pack(side="left")
        ctk.CTkLabel(brow, text="💡 Πατήστε οπουδήποτε στο πλαίσιο του σχεδίου για άμεση επιλογή",
                     font=("Arial", 11), text_color=TXTG).pack(side="left", padx=10)
        add_row()
        refresh()

        bot = self.card(wrap)
        ctk.CTkLabel(bot, text="Παρατηρήσεις (προαιρετικά):", font=("Arial", 13)).pack(anchor="w", padx=14)
        e_notes = ctk.CTkTextbox(bot, height=44, font=("Arial", 13)); e_notes.pack(fill="x", padx=14, pady=6)

        def save():
            cname = cb_cust.get().strip()
            # "CTkComboBox" = default κείμενο του widget όταν ο κατάλογος είναι άδειος
            if not cname or cname == "CTkComboBox":
                return messagebox.showwarning("Προσοχή", "Γράψε όνομα πελάτη")
            lines = []
            for row in rows:
                name = row.get("name") or row["b_des"].cget("text")
                w = row["e_w"].get().strip(); h = row["e_h"].get().strip()
                p_str = row["e_p"].get().strip()
                if name == "📐 Διάλεξε Σχέδιο..." and not w and not h and not p_str:
                    continue
                try:
                    q = float((row["e_q"].get() or "1").replace(",", "."))
                except Exception:
                    q = 1
                try:
                    p = float((p_str or "0").replace(",", "."))
                except Exception:
                    p = 0
                if q < 0 or p < 0:
                    return messagebox.showwarning("Προσοχή", "Ποσότητα και τιμή δεν μπορεί να είναι αρνητικές.")
                if q > 100000 or p > 10000000:
                    return messagebox.showwarning("Προσοχή", "Ποσότητα/τιμή εκτός ορίων.")
                
                loc = row["e_loc"].get().strip()
                base_name = row.get("name") or (f"{row.get('code', '')} Κούφωμα".strip() or "Κούφωμα")
                dim_suffix = f" ({w or '-' }x{h or '-' } εκ.)" if (w or h) else ""
                loc_suffix = f" - {loc}" if loc else ""
                full_name = f"{base_name}{dim_suffix}{loc_suffix}"
                
                lines.append({
                    "name": full_name,
                    "base": base_name,
                    "unit": "τεμ.",
                    "qty": q,
                    "price": p,
                    "code": row.get("code", ""),
                    "category": row.get("category", "") or guess_category(base_name),
                    "series": row.get("series", ""),
                    "color": row.get("color", ""),
                    "location": loc,
                    "width": w,
                    "height": h,
                    "descr": row.get("descr", "") or base_name,
                    "image": row.get("image", ""),
                    "materials": row.get("materials", [])
                })
            if not lines:
                return messagebox.showwarning("Προσοχή", "Γράψε τουλάχιστον 1 γραμμή κουφώματος")
            sub, vr, vat, tot = refresh()
            phone = e_phone.get().strip()
            c = db()
            crow = c.execute("SELECT * FROM customers WHERE name=?", (cname,)).fetchone()
            if crow:
                cid = crow["id"]
                if phone and not crow["phone"]:
                    c.execute("UPDATE customers SET phone=? WHERE id=?", (phone, cid))
                cinfo = f"{crow['address'] or ''}  •  {phone or crow['phone'] or ''}  •  {crow['email'] or ''}"
            else:
                cur = c.execute("INSERT INTO customers(name,phone,email,address) VALUES(?,?,?,?)",
                                (cname, phone, "", ""))
                cid = cur.lastrowid; cinfo = phone
            items = [{"name": L["name"], "unit": L["unit"], "qty": L["qty"], "price": L["price"]} for L in lines]
            qdesigns = [{
                "code": L["code"],
                "name": L["base"],
                "category": L["category"],
                "series": L["series"],
                "color": L["color"],
                "location": L["location"],
                "width": L["width"],
                "height": L["height"],
                "descr": L["descr"],
                "image": L["image"],
                "qty": L["qty"],
                "price": L["price"],
                "unit": L["unit"],
                "materials": L.get("materials", [])
            } for L in lines if L.get("image") or (L.get("width") and L.get("height"))]
            labor_amt = 0.0
            if labor_var.get():
                try:
                    labor_amt = float((e_labor_amt.get() or "0").replace(",", "."))
                except Exception:
                    labor_amt = 0.0

            labor_desc_val = txt_labor_desc.get("1.0", "end").strip() if labor_var.get() else ""

            qobj = {"number": safe_quote_number(e_num.get().strip() or nxt), "date": datetime.now().strftime("%d/%m/%Y"),
                    "customer_id": cid, "customer_name": cname, "customer_info": cinfo,
                    "items_json": json.dumps(items, ensure_ascii=False),
                    "designs_json": json.dumps(qdesigns, ensure_ascii=False),
                    "subtotal": sub, "vat_rate": vr, "vat_amount": vat, "total": tot,
                    "notes": e_notes.get("1.0", "end").strip()[:2000],
                    "include_labor": 1 if (labor_var.get() and labor_amt > 0) else 0,
                    "labor_amount": labor_amt if labor_var.get() else 0.0,
                    "labor_desc": labor_desc_val}
            c.execute("""INSERT INTO quotes(number,date,customer_id,customer_name,customer_info,
                       items_json,designs_json,subtotal,vat_rate,vat_amount,total,notes,
                       include_labor,labor_amount,labor_desc)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (qobj["number"], qobj["date"], qobj["customer_id"], qobj["customer_name"],
                       qobj["customer_info"], qobj["items_json"], qobj["designs_json"],
                       qobj["subtotal"], qobj["vat_rate"], qobj["vat_amount"], qobj["total"], qobj["notes"],
                       qobj["include_labor"], qobj["labor_amount"], qobj["labor_desc"]))
            for L in lines:
                code_val = L.get("code")
                if code_val:
                    c.execute("UPDATE designs SET use_count = COALESCE(use_count, 0) + 1 WHERE code=?", (code_val,))
                # Auto-save new materials into the materials table
                m_name = (L.get("base") or L.get("name") or "").strip()
                if m_name and m_name != "Κούφωμα" and not m_name.startswith("📐"):
                    exists = c.execute("SELECT 1 FROM materials WHERE LOWER(name)=?", (m_name.lower(),)).fetchone()
                    if not exists:
                        unit = L.get("unit") or "τεμ."
                        pr = float(L.get("price") or 0)
                        c.execute("INSERT INTO materials(name, unit, price) VALUES(?,?,?)", (m_name, unit, pr))

            c.commit(); c.close()
            path = os.path.join(PDF_DIR, f"Prosfora_{qobj['number']}.pdf")
            make_pdf(qobj, path)
            open_path_safe(path)
            open_folder_and_select(path)
            self.show("home")
        ctk.CTkButton(bot, text="💾 ΑΠΟΘΗΚΕΥΣΗ + PDF", font=("Arial", 16, "bold"),
                      height=52, fg_color=BLUEH, hover_color="#1e40af",
                      command=save).pack(padx=16, pady=12, fill="x")
        bind_scroll(wrap, wrap, recursive=True)

    # ---------- ΚΑΤΑΛΟΓΟΣ (Σχέδια | Υλικά | Πελάτες) ----------
    def page_catalog(self):
        self.section(self.main, "Κατάλογος", "σχέδια • υλικά • πελάτες σε ένα μέρος")
        box = ctk.CTkFrame(self.main, fg_color=CARD, corner_radius=16,
                           border_width=1, border_color="#e2e8f0")
        box.pack(fill="both", expand=True, padx=18, pady=(4, 12))
        seg = ctk.CTkSegmentedButton(box, values=["Σχέδια", "Υλικά", "Πελάτες"],
                                     font=("Arial", 14, "bold"), height=40,
                                     selected_color=BLUEH,
                                     command=self._seg_change)
        seg.set(self._catalog_tab)
        seg.pack(padx=14, pady=(12, 4))
        body = ctk.CTkFrame(box, fg_color=CARD)
        body.pack(fill="both", expand=True, padx=6, pady=6)
        {"Σχέδια": self.render_designs, "Υλικά": self.render_materials,
         "Πελάτες": self.render_customers}[self._catalog_tab](body)

    def _seg_change(self, v):
        self._catalog_tab = v
        self.show("catalog")

    def render_designs(self, box):
        bar = ctk.CTkFrame(box, fg_color=CARD); bar.pack(fill="x", padx=10, pady=8)
        e_search = ctk.CTkEntry(bar, width=240, placeholder_text="🔍 Αναζήτηση (κωδικός / όνομα)...", font=("Arial", 13))
        e_search.pack(side="left", padx=4)
        cb_cat = ctk.CTkComboBox(bar, values=["Όλες"] + CATEGORIES, width=150, font=("Arial", 13))
        cb_cat.set("Όλες"); cb_cat.pack(side="left", padx=4)
        ctk.CTkButton(bar, text="＋ Νέο σχέδιο", font=("Arial", 13, "bold"),
                      command=lambda: self.design_dialog()).pack(side="left", padx=4)
        ctk.CTkButton(bar, text="📥 Εισαγωγή φακέλου", fg_color=ACCENT,
                      command=lambda: self.bulk_import()).pack(side="left", padx=4)
        
        def reload_presets():
            if messagebox.askyesno("Φόρτωση Προτύπων", "Να προστεθούν τα 10 βασικά πρότυπα κουφωμάτων Alumil & Europa;"):
                c = db()
                seed_default_designs(c)
                c.commit(); c.close()
                load()
        ctk.CTkButton(bar, text="⭐ Πρότυπα Alumil", fg_color="#0284c7",
                      command=reload_presets).pack(side="left", padx=4)
        grid = ctk.CTkScrollableFrame(box, fg_color=CARD)
        grid.pack(fill="both", expand=True, padx=8, pady=8)
        grid.grid_columnconfigure(0, weight=1)
        grid.grid_columnconfigure(1, weight=1)
        grid.grid_columnconfigure(2, weight=1)
        bind_scroll(grid, grid, recursive=False)

        def load(*_):
            for w in grid.winfo_children():
                w.destroy()
            self._thumbs = []
            q = fold_el(e_search.get().strip())
            cat = cb_cat.get()
            c = db()
            rows = c.execute("SELECT * FROM designs ORDER BY code").fetchall()
            c.close()
            n = 0
            for r in rows:
                if cat != "Όλες" and r["category"] != cat:
                    continue
                blob = fold_el(" ".join([r["code"] or "", r["name"] or "", r["series"] or "", r["category"] or ""]))
                if q and q not in blob:
                    continue
                card = ctk.CTkFrame(grid, fg_color=ROWB, corner_radius=12)
                card.grid(row=n // 3, column=n % 3, padx=8, pady=8, sticky="nsew")
                n += 1
                pth = img_path(r["image"])
                if pth:
                    try:
                        with PILImage.open(pth) as im:
                            w0, h0 = im.size
                        s = min(200 / w0, 140 / h0)
                        photo = ctk.CTkImage(light_image=PILImage.open(pth), size=(int(w0*s), int(h0*s)))
                        self._thumbs.append(photo)
                        ctk.CTkLabel(card, text="", image=photo).pack(padx=8, pady=(8, 2))
                    except Exception:
                        ctk.CTkLabel(card, text="(χαλασμένη εικόνα)", font=("Arial", 11)).pack(padx=8, pady=8)
                else:
                    ctk.CTkLabel(card, text="📐\n(χωρίς εικόνα)", font=("Arial", 12),
                                 text_color="#94a3b8", justify="center").pack(padx=40, pady=20)
                dims = f"{r['width'] or '-'}×{r['height'] or '-'} εκ."
                ctk.CTkLabel(card, text=f"{r['code']} — {r['name']}", font=("Arial", 13, "bold"),
                             text_color=TXTD).pack()
                ctk.CTkLabel(card, text=f"{r['category'] or ''} • {dims}",
                             font=("Arial", 12), text_color=BLUEH).pack()
                btns = ctk.CTkFrame(card, fg_color="transparent"); btns.pack(pady=6)
                ctk.CTkButton(btns, text="Επεξεργασία", width=110,
                              command=lambda i=r["id"]: self.design_dialog(i)).pack(side="left", padx=3)
                ctk.CTkButton(btns, text="✕", width=36, fg_color=RED,
                              command=lambda i=r["id"]: self.del_design(i, load)).pack(side="left", padx=3)
                bind_scroll(card, grid, recursive=True)
            if n == 0:
                ctk.CTkLabel(grid, text="Κανένα σχέδιο.\nΠάτα «Νέο σχέδιο» ή «Εισαγωγή φακέλου».",
                             font=("Arial", 14), text_color=TXTG, justify="center").grid(row=0, column=0, columnspan=3, pady=40)
        e_search.bind("<KeyRelease>", load)
        cb_cat.configure(command=load)
        load()

    def del_design(self, i, reload):
        if not messagebox.askyesno("Σίγουρα;", "Διαγραφή σχεδίου;"):
            return
        c = db()
        r = c.execute("SELECT image FROM designs WHERE id=?", (i,)).fetchone()
        c.execute("DELETE FROM designs WHERE id=?", (i,))
        c.commit(); c.close()
        if r and r["image"]:
            b = safe_img_name(r["image"])
            if b:
                try:
                    os.remove(os.path.join(IMG_DIR, b))
                except Exception:
                    pass
        reload()

    def bulk_import(self):
        folder = filedialog.askdirectory(title="Διάλεξε φάκελο με φωτογραφίες σχεδίων")
        if not folder:
            return
        files = [f for f in os.listdir(folder)
                 if os.path.splitext(f)[1].lower() in (".jpg", ".jpeg", ".png", ".bmp", ".webp")]
        if not files:
            return messagebox.showwarning("Προσοχή", "Ο φάκελος δεν έχει φωτογραφίες")
        if len(files) > 500:
            return messagebox.showwarning("Προσοχή", "Πάρα πολλά αρχεία (όριο 500 ανά εισαγωγή).")
        c = db(); n = 0
        for f in sorted(files)[:500]:
            full = os.path.join(folder, f)
            # no symlinks / dirs, size cap before decode
            try:
                if not os.path.isfile(full) or os.path.islink(full):
                    continue
                if os.path.getsize(full) > MAX_UPLOAD_BYTES:
                    continue
            except Exception:
                continue
            code = os.path.splitext(f)[0][:40]
            if c.execute("SELECT 1 FROM designs WHERE code=?", (code,)).fetchone():
                continue
            try:
                fn = store_image(full)
            except Exception:
                continue
            c.execute("INSERT INTO designs(code,name,category,width,height,descr,image,price) VALUES(?,?,?,?,?,?,?,0)",
                      (code, code, "Άλλο", "", "", "", fn))
            n += 1
        c.commit(); c.close()
        messagebox.showinfo("ΟΚ", f"Προστέθηκαν {n} σχέδια! Συμπλήρωσε ονόματα/μέτρα όπου χρειάζεται.")
        self.show("catalog")

    def design_dialog(self, did=None):
        data = {}
        if did:
            c = db()
            data = dict(c.execute("SELECT * FROM designs WHERE id=?", (did,)).fetchone())
            c.close()
        win = ctk.CTkToplevel(self)
        win.title("Σχέδιο"); win.geometry("460x620")
        self._popup_setup(win)
        img_file = {"v": data.get("image", "")}
        prev = {"lbl": None}

        def pick():
            f = filedialog.askopenfilename(title="Διάλεξε εικόνα σχεδίου",
                filetypes=[("Εικόνες", "*.jpg *.jpeg *.png *.bmp *.webp")])
            if f:
                try:
                    img_file["v"] = store_image(f)
                    show_prev()
                except Exception as e:
                    messagebox.showerror("Σφάλμα", str(e))

        def show_prev():
            pth = img_path(img_file["v"])
            if prev["lbl"]:
                prev["lbl"].destroy(); prev["lbl"] = None
            if pth:
                try:
                    with PILImage.open(pth) as im:
                        w0, h0 = im.size
                    s = min(300 / w0, 180 / h0)
                    ph = ctk.CTkImage(light_image=PILImage.open(pth), size=(int(w0*s), int(h0*s)))
                    prev["lbl"] = ctk.CTkLabel(frm, text="", image=ph)
                    prev["lbl"].image = ph
                    prev["lbl"].pack(pady=6)
                except Exception:
                    pass
        frm = ctk.CTkScrollableFrame(win, fg_color="white")
        frm.pack(fill="both", expand=True, padx=12, pady=12)
        ents = {}

        def row(lbl, key, val=""):
            ctk.CTkLabel(frm, text=lbl, font=("Arial", 12, "bold")).pack(anchor="w")
            e = ctk.CTkEntry(frm, width=380, font=("Arial", 13)); e.insert(0, val or ""); e.pack(pady=(0, 8))
            ents[key] = e
        row("Κωδικός σχεδίου * (π.χ. Π-101)", "code", data.get("code", ""))
        row("Όνομα * (π.χ. Συρόμενο δίφυλλο)", "name", data.get("name", ""))
        row("Σειρά (π.χ. ALUMIL/S350 ALUTHERM, M9660)", "series", data.get("series", ""))
        row("Χρώμα (π.χ. ΑΝΘΡΑΚΙ RAL 8.85 ΘΕΡΜΟ)", "color", data.get("color", ""))
        row("Τοποθέτηση (π.χ. 1ος-ΓΩΝΙΑΚΟ, ΙΣΟΓΕΙΟ)", "location", data.get("location", ""))
        ctk.CTkLabel(frm, text="Κατηγορία", font=("Arial", 12, "bold")).pack(anchor="w")
        cb = ctk.CTkComboBox(frm, values=CATEGORIES, width=380, font=("Arial", 13))
        cb.set(data.get("category", "Άλλο") or "Άλλο"); cb.pack(pady=(0, 8))
        row("Πλάτος (εκ.)", "width", data.get("width", ""))
        row("Ύψος (εκ.)", "height", data.get("height", ""))
        row("Περιγραφή", "descr", data.get("descr", ""))
        row("Ενδεικτική τιμή € (0 = χωρίς)", "price", str(data.get("price", 0) or 0))
        ctk.CTkLabel(frm, text="Υλικά κατασκευής (φαίνονται στο PDF κάτω από το σχέδιο)",
                     font=("Arial", 12, "bold")).pack(anchor="w", pady=(4, 0))
        matbox = ctk.CTkFrame(frm, fg_color="#f8fafc", corner_radius=8)
        matbox.pack(fill="x", pady=4)
        mat_rows = []

        def add_mat_row(pre=None):
            pre = pre if isinstance(pre, dict) else {}
            r = ctk.CTkFrame(matbox, fg_color="white", corner_radius=6)
            r.pack(fill="x", pady=2, padx=4)
            e = ctk.CTkEntry(r, width=150, placeholder_text="Υλικό", font=("Arial", 12))
            e.insert(0, pre.get("name", "")); e.pack(side="left", padx=3, pady=4)
            qe = ctk.CTkEntry(r, width=42, font=("Arial", 12)); qe.insert(0, str(pre.get("qty", 1))); qe.pack(side="left", padx=3)
            ue = ctk.CTkComboBox(r, values=["τεμ.", "τ.μ.", "μέτρο", "ώρες"], width=68, font=("Arial", 12))
            ue.set(pre.get("unit", "τεμ.") or "τεμ."); ue.pack(side="left", padx=3)
            pe = ctk.CTkEntry(r, width=58, placeholder_text="€", font=("Arial", 12))
            pe.insert(0, str(pre.get("price", "") or "")); pe.pack(side="left", padx=3)
            mr = {"e": e, "q": qe, "u": ue, "p": pe, "f": r}
            ctk.CTkButton(r, text="✕", width=28, fg_color="#ef4444",
                          command=lambda: (mat_rows.remove(mr), r.destroy())).pack(side="left", padx=3)
            mat_rows.append(mr)
        try:
            _init = json.loads(data.get("materials_json", "") or "[]")
        except Exception:
            _init = []
        for _m in (_init if isinstance(_init, list) else []):
            add_mat_row(_m)
        ctk.CTkButton(frm, text="＋ Υλικό", fg_color="#0ea5e9",
                      command=lambda: add_mat_row()).pack(anchor="w", pady=(0, 6))
        ctk.CTkButton(frm, text="🖼️ Διάλεξε εικόνα / φωτογραφία σχεδίου",
                      fg_color=ACCENT, command=pick).pack(pady=6)
        show_prev()

        def save():
            code = ents["code"].get().strip(); name = ents["name"].get().strip()
            if not code or not name:
                return messagebox.showwarning("Προσοχή", "Συμπλήρωσε κωδικό και όνομα")
            try:
                pr = float(ents["price"].get().replace(",", ".") or 0)
            except Exception:
                pr = 0
            mats = []
            for mrow in mat_rows:
                nm = mrow["e"].get().strip()
                if not nm:
                    continue
                try:
                    mq = float((mrow["q"].get() or "1").replace(",", "."))
                except Exception:
                    mq = 1
                try:
                    mp = float((mrow["p"].get() or "0").replace(",", "."))
                except Exception:
                    mp = 0
                mats.append({"name": nm, "qty": mq, "unit": mrow["u"].get(), "price": mp})
            vals = (code, name, cb.get(), ents["width"].get().strip(), ents["height"].get().strip(),
                    ents["descr"].get().strip(), img_file["v"], pr, json.dumps(mats, ensure_ascii=False),
                    ents["series"].get().strip(), ents["color"].get().strip(), ents["location"].get().strip())
            c = db()
            if did:
                c.execute("UPDATE designs SET code=?,name=?,category=?,width=?,height=?,descr=?,image=?,price=?,materials_json=?,series=?,color=?,location=? WHERE id=?",
                          (*vals, did))
            else:
                c.execute("INSERT INTO designs(code,name,category,width,height,descr,image,price,materials_json,series,color,location) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", vals)
            c.commit(); c.close()
            win.destroy(); self.show("catalog")
        ctk.CTkButton(frm, text="💾 Αποθήκευση", font=("Arial", 14, "bold"),
                      height=44, fg_color=BLUEH, command=save).pack(pady=10, fill="x")

    def render_materials(self, box):
        bar = ctk.CTkFrame(box, fg_color=CARD); bar.pack(fill="x", padx=14, pady=(8, 4))
        e_search = ctk.CTkEntry(bar, width=280, placeholder_text="🔍 Αναζήτηση υλικού...", font=("Arial", 13))
        e_search.pack(side="left", padx=4)

        fr = ctk.CTkFrame(box, fg_color=CARD); fr.pack(fill="x", padx=14, pady=(4, 8))
        e_n = ctk.CTkEntry(fr, width=280, placeholder_text="Όνομα νέου υλικού π.χ. Σίτα Plisse", font=("Arial", 13)); e_n.pack(side="left", padx=4)
        e_u = ctk.CTkComboBox(fr, values=["τεμ.", "τ.μ.", "μέτρο", "ώρες", "κιλό", "σετ"], width=90, font=("Arial", 13)); e_u.pack(side="left", padx=4)
        e_p = ctk.CTkEntry(fr, width=90, placeholder_text="Τιμή €", font=("Arial", 13)); e_p.pack(side="left", padx=4)
        
        lst = ctk.CTkScrollableFrame(box, fg_color=CARD)
        lst.pack(fill="both", expand=True, padx=8, pady=8)
        bind_scroll(lst, lst, recursive=False)

        def edit_mat_dialog(i, curr_n, curr_u, curr_p):
            d = ctk.CTkToplevel(self)
            d.title("Επεξεργασία Υλικού"); d.geometry("380x250")
            self._popup_setup(d)
            f = ctk.CTkFrame(d, fg_color="white", corner_radius=10); f.pack(fill="both", expand=True, padx=14, pady=14)
            ctk.CTkLabel(f, text="Όνομα Υλικού:", font=("Arial", 12, "bold")).pack(anchor="w", pady=(4, 2))
            en = ctk.CTkEntry(f, width=320, font=("Arial", 13)); en.insert(0, curr_n or ""); en.pack(fill="x", pady=(0, 8))
            ctk.CTkLabel(f, text="Μονάδα:", font=("Arial", 12, "bold")).pack(anchor="w", pady=(2, 2))
            eu = ctk.CTkComboBox(f, values=["τεμ.", "τ.μ.", "μέτρο", "ώρες", "κιλό", "σετ"], width=320, font=("Arial", 13))
            eu.set(curr_u or "τεμ."); eu.pack(fill="x", pady=(0, 8))
            ctk.CTkLabel(f, text="Τιμή €:", font=("Arial", 12, "bold")).pack(anchor="w", pady=(2, 2))
            ep = ctk.CTkEntry(f, width=320, font=("Arial", 13)); ep.insert(0, str(curr_p or "0")); ep.pack(fill="x", pady=(0, 12))
            def do_save():
                nm = en.get().strip()
                if not nm:
                    return messagebox.showwarning("Προσοχή", "Βάλε όνομα υλικού")
                try:
                    pr = float(ep.get().replace(",", "."))
                except Exception:
                    return messagebox.showwarning("Προσοχή", "Βάλε έγκυρη τιμή")
                c = db(); c.execute("UPDATE materials SET name=?, unit=?, price=? WHERE id=?", (nm, eu.get(), pr, i))
                c.commit(); c.close()
                d.destroy(); load()
            ctk.CTkButton(f, text="💾 Αποθήκευση", font=("Arial", 13, "bold"), fg_color=BLUEH, command=do_save).pack(fill="x")

        def delete_mat(i):
            if messagebox.askyesno("Σίγουρα;", "Διαγραφή υλικού;"):
                c = db(); c.execute("DELETE FROM materials WHERE id=?", (i,)); c.commit(); c.close()
                load()

        def load(*_):
            for w in lst.winfo_children():
                w.destroy()
            q = fold_el(e_search.get().strip())
            c = db(); rows = c.execute("SELECT * FROM materials ORDER BY name").fetchall(); c.close()
            n = 0
            for r in rows:
                if q and q not in fold_el(r["name"] or ""):
                    continue
                n += 1
                row = ctk.CTkFrame(lst, fg_color=ROWB, corner_radius=10); row.pack(fill="x", pady=4)
                ctk.CTkLabel(row, text=f"{r['name']}", font=("Arial", 14, "bold"),
                             text_color=TXTD).pack(side="left", padx=12, pady=8)
                ctk.CTkLabel(row, text=f"{fmt(r['price'])} / {r['unit']}", font=("Arial", 13),
                             text_color=BLUEH).pack(side="left", padx=8)
                ctk.CTkButton(row, text="✕", width=36, fg_color=RED,
                              command=lambda i=r["id"]: delete_mat(i)).pack(side="right", padx=6, pady=6)
                ctk.CTkButton(row, text="Επεξεργασία", width=100,
                              command=lambda i=r["id"], nm=r["name"], un=r["unit"], pr=r["price"]: edit_mat_dialog(i, nm, un, pr)).pack(side="right", padx=4, pady=6)
                bind_scroll(row, lst, recursive=True)
            if n == 0:
                ctk.CTkLabel(lst, text="Δεν βρέθηκαν υλικά.", font=("Arial", 13), text_color=TXTG).pack(pady=30)

        def add():
            try:
                pr = float(e_p.get().replace(",", "."))
            except Exception:
                return messagebox.showwarning("Προσοχή", "Βάλε σωστή τιμή")
            if not e_n.get().strip():
                return messagebox.showwarning("Προσοχή", "Βάλε όνομα υλικού")
            c = db(); c.execute("INSERT INTO materials(name,unit,price) VALUES(?,?,?)",
                                (e_n.get().strip(), e_u.get(), pr)); c.commit(); c.close()
            e_n.delete(0, "end"); e_p.delete(0, "end"); load()
        ctk.CTkButton(fr, text="＋ Προσθήκη", font=("Arial", 13, "bold"), command=add).pack(side="left", padx=6)
        e_search.bind("<KeyRelease>", load)
        load()

    def render_customers(self, box):
        bar = ctk.CTkFrame(box, fg_color=CARD); bar.pack(fill="x", padx=14, pady=(8, 4))
        e_search = ctk.CTkEntry(bar, width=280, placeholder_text="🔍 Αναζήτηση πελάτη (όνομα / τηλ)...", font=("Arial", 13))
        e_search.pack(side="left", padx=4)

        fr = ctk.CTkFrame(box, fg_color=CARD); fr.pack(fill="x", padx=14, pady=(4, 8))
        e1 = ctk.CTkEntry(fr, width=180, placeholder_text="Ονοματεπώνυμο *", font=("Arial", 13)); e1.pack(side="left", padx=4)
        e2 = ctk.CTkEntry(fr, width=120, placeholder_text="Τηλέφωνο", font=("Arial", 13)); e2.pack(side="left", padx=4)
        e3 = ctk.CTkEntry(fr, width=150, placeholder_text="Email", font=("Arial", 13)); e3.pack(side="left", padx=4)
        e4 = ctk.CTkEntry(fr, width=160, placeholder_text="Διεύθυνση", font=("Arial", 13)); e4.pack(side="left", padx=4)
        lst = ctk.CTkScrollableFrame(box, fg_color=CARD); lst.pack(fill="both", expand=True, padx=8, pady=8)
        bind_scroll(lst, lst, recursive=False)

        def edit_cust_dialog(i, cdata):
            d = ctk.CTkToplevel(self)
            d.title("Επεξεργασία Πελάτη"); d.geometry("400x320")
            self._popup_setup(d)
            f = ctk.CTkFrame(d, fg_color="white", corner_radius=10); f.pack(fill="both", expand=True, padx=14, pady=14)
            ctk.CTkLabel(f, text="Ονοματεπώνυμο *:", font=("Arial", 12, "bold")).pack(anchor="w", pady=(2, 2))
            ce1 = ctk.CTkEntry(f, width=340, font=("Arial", 13)); ce1.insert(0, cdata.get("name","") or ""); ce1.pack(fill="x", pady=(0, 6))
            ctk.CTkLabel(f, text="Τηλέφωνο:", font=("Arial", 12, "bold")).pack(anchor="w", pady=(2, 2))
            ce2 = ctk.CTkEntry(f, width=340, font=("Arial", 13)); ce2.insert(0, cdata.get("phone","") or ""); ce2.pack(fill="x", pady=(0, 6))
            ctk.CTkLabel(f, text="Email:", font=("Arial", 12, "bold")).pack(anchor="w", pady=(2, 2))
            ce3 = ctk.CTkEntry(f, width=340, font=("Arial", 13)); ce3.insert(0, cdata.get("email","") or ""); ce3.pack(fill="x", pady=(0, 6))
            ctk.CTkLabel(f, text="Διεύθυνση:", font=("Arial", 12, "bold")).pack(anchor="w", pady=(2, 2))
            ce4 = ctk.CTkEntry(f, width=340, font=("Arial", 13)); ce4.insert(0, cdata.get("address","") or ""); ce4.pack(fill="x", pady=(0, 10))
            def do_save():
                nm = ce1.get().strip()
                if not nm:
                    return messagebox.showwarning("Προσοχή", "Βάλε όνομα πελάτη")
                c = db(); c.execute("UPDATE customers SET name=?, phone=?, email=?, address=? WHERE id=?",
                                    (nm, ce2.get().strip(), ce3.get().strip(), ce4.get().strip(), i))
                c.commit(); c.close()
                d.destroy(); load()
            ctk.CTkButton(f, text="💾 Αποθήκευση", font=("Arial", 13, "bold"), fg_color=BLUEH, command=do_save).pack(fill="x")

        def delete_cust(i):
            if messagebox.askyesno("Σίγουρα;", "Διαγραφή πελάτη;"):
                c = db(); c.execute("DELETE FROM customers WHERE id=?", (i,)); c.commit(); c.close()
                load()

        def load(*_):
            for w in lst.winfo_children():
                w.destroy()
            q = fold_el(e_search.get().strip())
            c = db(); rows = c.execute("SELECT * FROM customers ORDER BY name").fetchall(); c.close()
            n = 0
            for r in rows:
                blob = fold_el(" ".join([r["name"] or "", r["phone"] or "", r["email"] or "", r["address"] or ""]))
                if q and q not in blob:
                    continue
                n += 1
                row = ctk.CTkFrame(lst, fg_color=ROWB, corner_radius=10); row.pack(fill="x", pady=4)
                info_text = f"{r['name']}"
                if r['phone']:
                    info_text += f"  •  📞 {r['phone']}"
                if r['email']:
                    info_text += f"  •  ✉️ {r['email']}"
                if r['address']:
                    info_text += f"  •  📍 {r['address']}"
                ctk.CTkLabel(row, text=info_text,
                             font=("Arial", 13, "bold"), text_color=TXTD).pack(side="left", padx=12, pady=8)
                ctk.CTkButton(row, text="✕", width=36, fg_color=RED,
                              command=lambda i=r["id"]: delete_cust(i)).pack(side="right", padx=6)
                ctk.CTkButton(row, text="Επεξεργασία", width=100,
                              command=lambda i=r["id"], cd=dict(r): edit_cust_dialog(i, cd)).pack(side="right", padx=4)
                bind_scroll(row, lst, recursive=True)
            if n == 0:
                ctk.CTkLabel(lst, text="Δεν βρέθηκαν πελάτες.", font=("Arial", 13), text_color=TXTG).pack(pady=30)

        def add():
            if not e1.get().strip():
                return messagebox.showwarning("Προσοχή", "Βάλε όνομα πελάτη")
            c = db(); c.execute("INSERT INTO customers(name,phone,email,address) VALUES(?,?,?,?)",
                                (e1.get().strip(), e2.get(), e3.get(), e4.get())); c.commit(); c.close()
            for e in (e1, e2, e3, e4):
                e.delete(0, "end")
            load()
        ctk.CTkButton(fr, text="＋ Προσθήκη", font=("Arial", 13, "bold"), command=add).pack(side="left", padx=6)
        e_search.bind("<KeyRelease>", load)
        load()

    # ---------- ΣΤΟΙΧΕΙΑ & ΛΟΓΟΤΥΠΟ ----------
    def page_settings(self):
        self.section(self.main, "Στοιχεία & Λογότυπο", "εμφανίζονται στο PDF της προσφοράς")
        comp = get_company()
        box = self.card(self.main)
        cols = ctk.CTkFrame(box, fg_color=CARD); cols.pack(fill="x", padx=14, pady=12)
        left = ctk.CTkFrame(cols, fg_color=CARD); left.pack(side="left", fill="both", expand=True)
        right = ctk.CTkFrame(cols, fg_color=ROWB, corner_radius=12, width=300)
        right.pack(side="right", fill="y", padx=10, pady=4)
        right.pack_propagate(False)
        ents = {}
        fields = [("name", "Επωνυμία *"), ("address", "Διεύθυνση"), ("phone", "Τηλέφωνα"),
                  ("email", "Email"), ("afm", "ΑΦΜ"), ("doy", "ΔΟΥ"), ("notes", "Σημείωση PDF (π.χ. ισχύς προσφοράς)")]
        for i, (k, lbl) in enumerate(fields):
            ctk.CTkLabel(left, text=lbl, font=("Arial", 13, "bold"), text_color=TXTD).grid(row=i, column=0, sticky="w", padx=8, pady=6)
            e = ctk.CTkEntry(left, width=420, font=("Arial", 13)); e.insert(0, comp.get(k, "")); e.grid(row=i, column=1, padx=8, pady=6)
            ents[k] = e

        ctk.CTkLabel(right, text="Λογότυπο", font=("Arial", 15, "bold"), text_color=TXTD).pack(pady=(14, 4))
        lg = get_logo()
        if lg:
            try:
                with PILImage.open(lg) as im:
                    w0, h0 = im.size
                s = min(240 / w0, 150 / h0)
                self._logo_img = ctk.CTkImage(light_image=PILImage.open(lg), size=(int(w0*s), int(h0*s)))
                ctk.CTkLabel(right, text="", image=self._logo_img).pack(pady=6)
            except Exception:
                ctk.CTkLabel(right, text="(σφάλμα εικόνας)", font=("Arial", 12)).pack(pady=6)
        else:
            ctk.CTkLabel(right, text="(χωρίς λογότυπο)\nΘα φαίνεται πάνω-αριστερά\nστο PDF.",
                         font=("Arial", 12), text_color=TXTG, justify="center").pack(pady=16)

        def pick_logo():
            f = filedialog.askopenfilename(title="Διάλεξε λογότυπο",
                filetypes=[("Εικόνες", "*.png *.jpg *.jpeg *.bmp *.webp")])
            if f:
                try:
                    set_logo(f)
                    messagebox.showinfo("ΟΚ", "Το λογότυπο ανέβηκε!")
                    self.show("settings")
                except Exception as e:
                    messagebox.showerror("Σφάλμα", str(e))

        def del_logo():
            try:
                os.remove(LOGO_FILE)
            except Exception:
                pass
            self.show("settings")
        ctk.CTkButton(right, text="📤 Ανέβασμα λογότυπου", fg_color=ACCENT,
                      command=pick_logo).pack(pady=6, padx=20, fill="x")
        if lg:
            ctk.CTkButton(right, text="Αφαίρεση", fg_color=RED,
                          command=del_logo).pack(pady=2, padx=20, fill="x")

        def save():
            save_company({k: e.get() for k, e in ents.items()})
            messagebox.showinfo("ΟΚ", "Αποθηκεύτηκαν!")
        ctk.CTkButton(box, text="💾 Αποθήκευση", font=("Arial", 15, "bold"),
                      height=48, fg_color=BLUEH, hover_color="#1e40af",
                      command=save).pack(padx=16, pady=12, fill="x")

if __name__ == "__main__":
    init_db()
    App().mainloop()
