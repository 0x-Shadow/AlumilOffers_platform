# -*- coding: utf-8 -*-
"""
AluminaOffers v4 - Προσφορές Αλουμινάδων για Windows
Dashboard | Νέα Προσφορά (μία οθόνη) | Κατάλογος | Στοιχεία+Λογότυπο | PDF με ΦΠΑ
"""
import os, sqlite3, json, shutil, re, html, sys, subprocess
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
    # allow only sane chars + known extensions
    if not re.fullmatch(r"[A-Za-z0-9\u0370-\u03FF_\-]+\.(jpg|jpeg|png|bmp|webp)", b, re.IGNORECASE):
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

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, HRFlowable, Image as RLImage,
                                KeepTogether)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "alumina.db")
PDF_DIR = os.path.join(BASE, "PDF_Prosfores")
IMG_DIR = os.path.join(BASE, "Sxedia")
LOGO_FILE = os.path.join(BASE, "logo.png")
os.makedirs(PDF_DIR, exist_ok=True)
os.makedirs(IMG_DIR, exist_ok=True)

try:
    pdfmetrics.registerFont(TTFont('Greek', r'C:\Windows\Fonts\arial.ttf'))
    pdfmetrics.registerFont(TTFont('Greek-Bold', r'C:\Windows\Fonts\arialbd.ttf'))
    FONT, FONTB = 'Greek', 'Greek-Bold'
except Exception:
    FONT, FONTB = 'Helvetica', 'Helvetica-Bold'

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
    c.execute("""CREATE TABLE IF NOT EXISTS quotes(
        id INTEGER PRIMARY KEY AUTOINCREMENT, number TEXT, date TEXT,
        customer_id INTEGER, customer_name TEXT, customer_info TEXT,
        items_json TEXT, subtotal REAL, vat_rate REAL, vat_amount REAL,
        total REAL, notes TEXT)""")
    cols = [r[1] for r in c.execute("PRAGMA table_info(quotes)").fetchall()]
    if "designs_json" not in cols:
        c.execute("ALTER TABLE quotes ADD COLUMN designs_json TEXT DEFAULT '[]'")
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
        title=f"Prosfora {q['number']}")
    st_title = ParagraphStyle('t', fontName=FONTB, fontSize=20, textColor=BLUE, leading=24)
    st_h = ParagraphStyle('h', fontName=FONTB, fontSize=11, textColor=BLUE, leading=14)
    st_n = ParagraphStyle('n', fontName=FONT, fontSize=9.5, textColor=DARK, leading=13)
    st_small = ParagraphStyle('s', fontName=FONT, fontSize=8.5, textColor=colors.grey, leading=11)
    st_cell = ParagraphStyle('c', fontName=FONT, fontSize=9, leading=12)
    st_cellb = ParagraphStyle('cb', fontName=FONTB, fontSize=9, leading=12)
    st_cellh = ParagraphStyle('ch', fontName=FONTB, fontSize=9, leading=12, textColor=colors.white)
    st_right = ParagraphStyle('r', fontName=FONT, fontSize=10, leading=14, alignment=2)
    st_total = ParagraphStyle('rt', fontName=FONTB, fontSize=13, leading=16, alignment=2, textColor=colors.white)
    st_d = ParagraphStyle('d', fontName=FONT, fontSize=9, leading=12, textColor=DARK)

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

    meta = Table([
        [Paragraph(f"<b>Ημερομηνία:</b> {esc(q['date'])}", st_right)],
    ], colWidths=[170*mm])
    meta.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (1, 0), (1, 0), 0)]))
    story.append(meta)
    story.append(Spacer(1, 6))
    cust = Table([[Paragraph(f"<b>{esc(q['customer_name'])}</b><br/><font size=9>{esc(q.get('customer_info',''))}</font>", st_n)]],
                 colWidths=[174*mm])
    cust.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), LIGHT_BG),
        ('ROUNDEDCORNERS', [6, 6, 6, 6]),
        ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10), ('RIGHTPADDING', (0, 0), (-1, -1), 10)]))
    story.append(cust)
    story.append(Spacer(1, 8))

    if items:
        data = [[Paragraph("<b>Υλικό / Εργασία</b>", st_cellh), Paragraph("<b>Ποσ.</b>", st_cellh),
                 Paragraph("<b>Μον.</b>", st_cellh), Paragraph("<b>Τιμή μον.</b>", st_cellh),
                 Paragraph("<b>Σύνολο</b>", st_cellh)]]
        for it in items:
            qty = float(it.get("qty", 0)); pr = float(it.get("price", 0))
            data.append([
                Paragraph(esc(it.get("name", "")), st_cell),
                Paragraph(str(qty).rstrip("0").rstrip(".") if "." in str(qty) else str(qty), st_cell),
                Paragraph(esc(it.get("unit", "")), st_cell),
                Paragraph(fmt(pr), st_cell),
                Paragraph(fmt(qty*pr), st_cell),
            ])
        t = Table(data, colWidths=[78*mm, 16*mm, 16*mm, 28*mm, 32*mm], repeatRows=1)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), DARK),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ]))
        story.append(t)
        story.append(Spacer(1, 10))

    if designs:
        story.append(Paragraph("ΣΧΕΔΙΑ / ΚΑΤΑΣΚΕΥΕΣ", st_h))
        story.append(Spacer(1, 4))
        for d in designs:
            pth = img_path(d.get("image", ""))
            im = pdf_image(pth) if pth else None
            dims = f"{esc(d.get('width',''))} x {esc(d.get('height',''))} εκ." if d.get("width") or d.get("height") else "-"
            try:
                dq = float(d.get("qty", 1) or 1)
            except Exception:
                dq = 1
            info = (f"<b>{esc(d.get('code',''))} - {esc(d.get('name',''))}</b><br/>"
                    f"Κατηγορία: {esc(d.get('category',''))}<br/>"
                    f"Διαστάσεις (Π x Υ): <b>{dims}</b><br/>"
                    f"Τεμάχια: <b>{dq:g}</b>")
            if d.get("descr"):
                info += f"<br/><font size=8>{esc(d.get('descr',''))}</font>"
            cells = [[im or Paragraph("(χωρίς εικόνα)", st_small), Paragraph(info, st_d)]]
            dt = Table(cells, colWidths=[70*mm, 100*mm])
            dt.setStyle(TableStyle([
                ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ('BACKGROUND', (0, 0), (-1, -1), colors.white),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ]))
            parts = [dt]
            dm = d.get("materials") or []
            if isinstance(dm, str):
                try:
                    dm = json.loads(dm)
                except Exception:
                    dm = []
            if dm:
                mrows = [[Paragraph("<b>Υλικό κατασκευής</b>", st_cellh),
                          Paragraph("<b>Ποσ.</b>", st_cellh),
                          Paragraph("<b>Τιμή</b>", st_cellh)]]
                for m in dm:
                    try:
                        mq = float(m.get("qty", 0) or 0) * dq
                    except Exception:
                        mq = 0
                    mrows.append([
                        Paragraph(esc(m.get("name", "")), st_cell),
                        Paragraph(esc(f"{mq:g} {m.get('unit','')}").strip(), st_cell),
                        Paragraph(fmt(m.get("price", 0)), st_cell),
                    ])
                mt = Table(mrows, colWidths=[96*mm, 38*mm, 36*mm])
                mt.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), DARK),
                    ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                    ('LEFTPADDING', (0, 0), (-1, -1), 6),
                    ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
                ]))
                parts.append(Spacer(1, 3))
                parts.append(mt)
            story.append(KeepTogether(parts))
            story.append(Spacer(1, 6))

    totals = [
        [Paragraph("Αρχική Αξία (χωρίς ΦΠΑ):", st_right), Paragraph(fmt(q["subtotal"]), st_right)],
        [Paragraph(f"ΦΠΑ {q['vat_rate']}%:", st_right), Paragraph(fmt(q["vat_amount"]), st_right)],
    ]
    tt = Table(totals, colWidths=[110*mm, 60*mm])
    tt.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]))
    story.append(tt)
    story.append(Spacer(1, 4))
    totbox = Table([[Paragraph("ΣΥΝΟΛΟ ΜΕ ΦΠΑ", ParagraphStyle('l', fontName=FONTB, fontSize=12, textColor=colors.white, leading=16)),
                      Paragraph(fmt(q["total"]), st_total)]], colWidths=[110*mm, 60*mm])
    totbox.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), BLUE),
        ('ROUNDEDCORNERS', [6, 6, 6, 6]), ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10), ('RIGHTPADDING', (0, 0), (-1, -1), 10)]))
    story.append(totbox)
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
        self.title("AluminaOffers")
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
        ctk.CTkLabel(brand, text="Προσφορές αλουμινάδων", font=("Arial", 12),
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
                ctk.CTkButton(row, text="PDF", width=64, command=lambda qq=dict(r): self.open_pdf(qq)).pack(side="right", padx=4, pady=6)
                ctk.CTkButton(row, text="✕", width=36, fg_color=RED,
                              command=lambda i=r["id"]: self.del_quote(i)).pack(side="right", pady=6)
            if n == 0:
                ctk.CTkLabel(lst, text="Καμία προσφορά — πάτα «ΝΕΑ ΠΡΟΣΦΟΡΑ»!",
                             font=("Arial", 13), text_color=TXTG).pack(pady=24)
        e_s.bind("<KeyRelease>", load)
        load()

    def del_quote(self, i):
        if messagebox.askyesno("Διαγραφή", "Να διαγραφεί η προσφορά;"):
            c = db(); c.execute("DELETE FROM quotes WHERE id=?", (i,)); c.commit(); c.close()
            self.show("home")

    def open_pdf(self, q):
        num = safe_quote_number(q['number'])
        path = os.path.join(PDF_DIR, f"Prosfora_{num}.pdf")
        make_pdf(q, path)
        open_path_safe(path)

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

        wrap = ctk.CTkScrollableFrame(self.main, fg_color=BG, height=600)
        wrap.pack(fill="both", expand=True)

        top = self.card(wrap)
        f1 = ctk.CTkFrame(top, fg_color=CARD); f1.pack(fill="x", padx=14, pady=10)
        ctk.CTkLabel(f1, text="Νο:", font=("Arial", 13, "bold")).pack(side="left")
        e_num = ctk.CTkEntry(f1, width=80, font=("Arial", 14)); e_num.insert(0, nxt); e_num.pack(side="left", padx=6)
        ctk.CTkLabel(f1, text="Πελάτης:", font=("Arial", 13, "bold")).pack(side="left", padx=(10, 0))
        cb_cust = ctk.CTkComboBox(f1, values=[x["name"] for x in custs], width=220, font=("Arial", 13))
        cb_cust.pack(side="left", padx=6)
        e_phone = ctk.CTkEntry(f1, width=150, placeholder_text="Τηλέφωνο", font=("Arial", 13))
        e_phone.pack(side="left", padx=6)

        def on_cust(_):
            r = next((dict(x) for x in custs if x["name"] == cb_cust.get()), None)
            if r:
                e_phone.delete(0, "end"); e_phone.insert(0, r.get("phone", "") or "")
        cb_cust.configure(command=on_cust)
        ctk.CTkLabel(f1, text="ΦΠΑ %:", font=("Arial", 13, "bold")).pack(side="left", padx=(10, 0))
        e_vat = ctk.CTkEntry(f1, width=55, font=("Arial", 14)); e_vat.insert(0, str(DEFAULT_FPA)); e_vat.pack(side="left", padx=6)

        mid = self.card(wrap)
        hdr = ctk.CTkFrame(mid, fg_color=CARD); hdr.pack(fill="x", padx=14, pady=(10, 0))
        for txt, w in [("Περιγραφή (γράψε ελεύθερα)", 290), ("", 42), ("Π εκ.", 62),
                       ("Υ εκ.", 62), ("Τεμ", 56), ("Τιμή €", 86), ("Σύνολο", 96)]:
            ctk.CTkLabel(hdr, text=txt, font=("Arial", 12, "bold"), width=w, text_color=TXTG).pack(side="left", padx=3)
        rowsbox = ctk.CTkFrame(mid, fg_color=CARD); rowsbox.pack(fill="x", padx=14, pady=4)
        rows = []
        lbl_total = ctk.CTkLabel(mid, text="", font=("Arial", 13), text_color="#334155", justify="right")
        lbl_total.pack(anchor="e", padx=18)
        lbl_big = ctk.CTkLabel(mid, text="", font=("Arial", 20, "bold"), text_color=BLUEH)
        lbl_big.pack(anchor="e", padx=18, pady=(0, 6))

        def refresh():
            sub = 0.0
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
                lt = q * p; sub += lt
                row["l_sum"].configure(text=fmt(lt))
            try:
                vr = float(e_vat.get().replace(",", ".")) if e_vat.get() else DEFAULT_FPA
            except Exception:
                vr = DEFAULT_FPA
            vr = max(0.0, min(vr, 100.0))
            vat = sub * vr / 100
            lbl_total.configure(text=f"Αρχική αξία: {fmt(sub)}      ΦΠΑ {vr:g}%: {fmt(vat)}")
            lbl_big.configure(text=f"ΣΥΝΟΛΟ ΜΕ ΦΠΑ: {fmt(sub + vat)}")
            return sub, vr, vat, sub + vat
        e_vat.bind("<KeyRelease>", lambda e: refresh())

        def pick_design(row):
            win = ctk.CTkToplevel(self)
            win.title("Διάλεξε σχέδιο"); win.geometry("440x520"); win.grab_set()
            e_s = ctk.CTkEntry(win, placeholder_text="🔍 Αναζήτηση...", font=("Arial", 13))
            e_s.pack(fill="x", padx=12, pady=10)
            lst = ctk.CTkScrollableFrame(win, fg_color="white", height=400)
            lst.pack(fill="both", expand=True, padx=12, pady=6)

            def choose(d):
                if not row["e_desc"].get().strip():
                    row["e_desc"].delete(0, "end")
                    row["e_desc"].insert(0, f"{d['code']} {d['name']}")
                row["e_w"].delete(0, "end"); row["e_w"].insert(0, d.get("width", "") or "")
                row["e_h"].delete(0, "end"); row["e_h"].insert(0, d.get("height", "") or "")
                row["code"] = d["code"]; row["image"] = d.get("image", "") or ""
                row["category"] = d.get("category", "") or ""
                try:
                    _dm = d.get("materials_json", []) or []
                    row["materials"] = json.loads(_dm) if isinstance(_dm, str) else list(_dm)
                except Exception:
                    row["materials"] = []
                row["b_des"].configure(fg_color=GREEN)
                refresh(); win.destroy()

            def fill(q=""):
                for w in lst.winfo_children():
                    w.destroy()
                q = (q or "").lower()
                n = 0
                for d in des:
                    if q and q not in ((d["code"] or "") + " " + (d["name"] or "")).lower():
                        continue
                    n += 1
                    if n > 150:
                        break
                    dims = f"{d['width'] or '-'}x{d['height'] or '-'}"
                    try:
                        _mm = d.get("materials_json", []) or []
                        _mm = json.loads(_mm) if isinstance(_mm, str) else _mm
                    except Exception:
                        _mm = []
                    tag = f" • {len(_mm)} υλικά" if _mm else ""
                    ctk.CTkButton(lst, text=f"{d['code']} — {d['name']} ({dims}){tag}", anchor="w",
                                  font=("Arial", 12), fg_color=ROWB, text_color=TXTD,
                                  hover_color="#dbeafe",
                                  command=lambda dd=dict(d): choose(dd)).pack(fill="x", pady=2)
                if n == 0:
                    ctk.CTkLabel(lst, text="Δεν βρέθηκε σχέδιο", font=("Arial", 12)).pack(pady=20)
            e_s.bind("<KeyRelease>", lambda e: fill(e_s.get()))
            fill()

        def del_row(row):
            rows.remove(row); row["frame"].destroy(); refresh()

        def add_row():
            r = ctk.CTkFrame(rowsbox, fg_color=ROWB, corner_radius=8)
            r.pack(fill="x", pady=3)
            e_desc = ctk.CTkEntry(r, width=290, placeholder_text="π.χ. Συρόμενο σαλονιού", font=("Arial", 13))
            e_desc.pack(side="left", padx=3, pady=6)
            b_des = ctk.CTkButton(r, text="📐", width=42, fg_color=ACCENT, font=("Arial", 14, "bold"))
            b_des.pack(side="left", padx=3)
            e_w = ctk.CTkEntry(r, width=62, placeholder_text="Π", font=("Arial", 13)); e_w.pack(side="left", padx=3)
            e_h = ctk.CTkEntry(r, width=62, placeholder_text="Υ", font=("Arial", 13)); e_h.pack(side="left", padx=3)
            e_q = ctk.CTkEntry(r, width=56, font=("Arial", 13)); e_q.insert(0, "1"); e_q.pack(side="left", padx=3)
            e_p = ctk.CTkEntry(r, width=86, placeholder_text="0", font=("Arial", 13)); e_p.pack(side="left", padx=3)
            l_sum = ctk.CTkLabel(r, text=fmt(0), font=("Arial", 12, "bold"), width=96, text_color=BLUEH)
            l_sum.pack(side="left", padx=3)
            row = {"frame": r, "e_desc": e_desc, "b_des": b_des, "e_w": e_w, "e_h": e_h,
                   "e_q": e_q, "e_p": e_p, "l_sum": l_sum, "code": "", "image": "", "category": "",
                   "materials": []}
            b_des.configure(command=lambda: pick_design(row))
            for e in (e_desc, e_w, e_h, e_q, e_p):
                e.bind("<KeyRelease>", lambda e: refresh())
            ctk.CTkButton(r, text="✕", width=30, fg_color=RED,
                          command=lambda: del_row(row)).pack(side="left", padx=3)
            rows.append(row); refresh()
            e_desc.focus_set()

        brow = ctk.CTkFrame(mid, fg_color=CARD); brow.pack(fill="x", padx=14, pady=(0, 8))
        ctk.CTkButton(brow, text="＋ Προσθήκη γραμμής", font=("Arial", 13, "bold"),
                      fg_color=ACCENT, command=add_row).pack(side="left")
        ctk.CTkLabel(brow, text="Το 📐 φέρνει σχέδιο από τον κατάλογο (προαιρετικό)",
                     font=("Arial", 11), text_color=TXTG).pack(side="left", padx=10)
        add_row()
        refresh()

        bot = self.card(wrap)
        ctk.CTkLabel(bot, text="Παρατηρήσεις (προαιρετικά):", font=("Arial", 13)).pack(anchor="w", padx=14)
        e_notes = ctk.CTkTextbox(bot, height=44, font=("Arial", 13)); e_notes.pack(fill="x", padx=14, pady=6)

        def save():
            cname = cb_cust.get().strip()
            if not cname:
                return messagebox.showwarning("Προσοχή", "Γράψε όνομα πελάτη")
            lines = []
            for row in rows:
                desc = row["e_desc"].get().strip()
                if not desc and not row.get("image"):
                    continue
                try:
                    q = float((row["e_q"].get() or "1").replace(",", "."))
                except Exception:
                    q = 1
                try:
                    p = float((row["e_p"].get() or "0").replace(",", "."))
                except Exception:
                    p = 0
                if q < 0 or p < 0:
                    return messagebox.showwarning("Προσοχή", "Ποσότητα και τιμή δεν μπορεί να είναι αρνητικές.")
                if q > 100000 or p > 10000000:
                    return messagebox.showwarning("Προσοχή", "Ποσότητα/τιμή εκτός ορίων.")
                w = row["e_w"].get().strip(); h = row["e_h"].get().strip()
                base = desc or f"{row.get('code', '')}"
                name = base + (f" ({w or '-' }x{h or '-' } εκ.)" if (w or h) else "")
                lines.append({"name": name, "base": base, "unit": "τεμ.", "qty": q, "price": p,
                              "code": row.get("code", ""), "category": row.get("category", ""),
                              "width": w, "height": h, "image": row.get("image", ""),
                              "materials": row.get("materials", [])})
            if not lines:
                return messagebox.showwarning("Προσοχή", "Γράψε τουλάχιστον 1 γραμμή")
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
            qdesigns = [{"code": L["code"], "name": L["base"], "category": L["category"],
                         "width": L["width"], "height": L["height"], "descr": "",
                         "image": L["image"], "qty": L["qty"],
                         "materials": L.get("materials", [])} for L in lines if L.get("image")]
            qobj = {"number": safe_quote_number(e_num.get().strip() or nxt), "date": datetime.now().strftime("%d/%m/%Y"),
                    "customer_id": cid, "customer_name": cname, "customer_info": cinfo,
                    "items_json": json.dumps(items, ensure_ascii=False),
                    "designs_json": json.dumps(qdesigns, ensure_ascii=False),
                    "subtotal": sub, "vat_rate": vr, "vat_amount": vat, "total": tot,
                    "notes": e_notes.get("1.0", "end").strip()[:2000]}
            c.execute("""INSERT INTO quotes(number,date,customer_id,customer_name,customer_info,
                       items_json,designs_json,subtotal,vat_rate,vat_amount,total,notes)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (qobj["number"], qobj["date"], qobj["customer_id"], qobj["customer_name"],
                       qobj["customer_info"], qobj["items_json"], qobj["designs_json"],
                       qobj["subtotal"], qobj["vat_rate"], qobj["vat_amount"], qobj["total"], qobj["notes"]))
            c.commit(); c.close()
            messagebox.showinfo("ΟΚ", f"Η προσφορά {qobj['number']} αποθηκεύτηκε!")
            path = os.path.join(PDF_DIR, f"Prosfora_{qobj['number']}.pdf")
            make_pdf(qobj, path); open_path_safe(path)
            self.show("home")
        ctk.CTkButton(bot, text="💾 ΑΠΟΘΗΚΕΥΣΗ + PDF", font=("Arial", 16, "bold"),
                      height=52, fg_color=BLUEH, hover_color="#1e40af",
                      command=save).pack(padx=16, pady=12, fill="x")

    # ---------- ΚΑΤΑΛΟΓΟΣ (Σχέδια | Υλικά | Πελάτες) ----------
    def page_catalog(self):
        self.section(self.main, "Κατάλογος", "σχέδια • υλικά • πελάτες σε ένα μέρος")
        box = self.card(self.main)
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
        grid = ctk.CTkScrollableFrame(box, fg_color=CARD, height=430)
        grid.pack(fill="both", expand=True, padx=8, pady=8)

        def load(*_):
            for w in grid.winfo_children():
                w.destroy()
            self._thumbs = []
            q = e_search.get().strip().lower()
            cat = cb_cat.get()
            c = db()
            rows = c.execute("SELECT * FROM designs ORDER BY code").fetchall()
            c.close()
            n = 0
            for r in rows:
                if cat != "Όλες" and r["category"] != cat:
                    continue
                if q and q not in ((r["code"] or "") + " " + (r["name"] or "")).lower():
                    continue
                n += 1
                card = ctk.CTkFrame(grid, fg_color=ROWB, corner_radius=12)
                card.pack(side="left", padx=8, pady=8)
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
            if n == 0:
                ctk.CTkLabel(grid, text="Κανένα σχέδιο.\nΠάτα «Νέο σχέδιο» ή «Εισαγωγή φακέλου».",
                             font=("Arial", 14), text_color=TXTG, justify="center").pack(pady=40)
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
        win.title("Σχέδιο"); win.geometry("460x620"); win.grab_set()
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
                    ents["descr"].get().strip(), img_file["v"], pr, json.dumps(mats, ensure_ascii=False))
            c = db()
            if did:
                c.execute("UPDATE designs SET code=?,name=?,category=?,width=?,height=?,descr=?,image=?,price=?,materials_json=? WHERE id=?",
                          (*vals, did))
            else:
                c.execute("INSERT INTO designs(code,name,category,width,height,descr,image,price,materials_json) VALUES(?,?,?,?,?,?,?,?,?)", vals)
            c.commit(); c.close()
            win.destroy(); self.show("catalog")
        ctk.CTkButton(frm, text="💾 Αποθήκευση", font=("Arial", 14, "bold"),
                      height=44, fg_color=BLUEH, command=save).pack(pady=10, fill="x")

    def render_materials(self, box):
        fr = ctk.CTkFrame(box, fg_color=CARD); fr.pack(fill="x", padx=14, pady=10)
        e_n = ctk.CTkEntry(fr, width=300, placeholder_text="Όνομα υλικού π.χ. Συρόμενο τ.μ.", font=("Arial", 13)); e_n.pack(side="left", padx=4)
        e_u = ctk.CTkComboBox(fr, values=["τ.μ.", "τεμ.", "μέτρο", "ώρες"], width=100, font=("Arial", 13)); e_u.pack(side="left", padx=4)
        e_p = ctk.CTkEntry(fr, width=110, placeholder_text="Τιμή €", font=("Arial", 13)); e_p.pack(side="left", padx=4)
        lst = ctk.CTkScrollableFrame(box, fg_color=CARD, height=420); lst.pack(fill="both", expand=True, padx=8, pady=8)

        def delete_mat(i):
            if messagebox.askyesno("Σίγουρα;", "Διαγραφή υλικού;"):
                c = db(); c.execute("DELETE FROM materials WHERE id=?", (i,)); c.commit(); c.close()
                load()

        def load():
            for w in lst.winfo_children():
                w.destroy()
            c = db(); rows = c.execute("SELECT * FROM materials ORDER BY name").fetchall(); c.close()
            for r in rows:
                row = ctk.CTkFrame(lst, fg_color=ROWB, corner_radius=10); row.pack(fill="x", pady=4)
                ctk.CTkLabel(row, text=f"{r['name']}", font=("Arial", 14, "bold"),
                             text_color=TXTD).pack(side="left", padx=12)
                ctk.CTkLabel(row, text=f"{fmt(r['price'])} / {r['unit']}", font=("Arial", 13),
                             text_color=BLUEH).pack(side="left", padx=8)
                ctk.CTkButton(row, text="Διαγραφή", width=90, fg_color=RED,
                              command=lambda i=r["id"]: delete_mat(i)).pack(side="right", padx=6, pady=6)

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
        load()

    def render_customers(self, box):
        fr = ctk.CTkFrame(box, fg_color=CARD); fr.pack(fill="x", padx=14, pady=10)
        e1 = ctk.CTkEntry(fr, width=200, placeholder_text="Ονοματεπώνυμο *", font=("Arial", 13)); e1.pack(side="left", padx=4)
        e2 = ctk.CTkEntry(fr, width=120, placeholder_text="Τηλέφωνο", font=("Arial", 13)); e2.pack(side="left", padx=4)
        e3 = ctk.CTkEntry(fr, width=170, placeholder_text="Email", font=("Arial", 13)); e3.pack(side="left", padx=4)
        e4 = ctk.CTkEntry(fr, width=180, placeholder_text="Διεύθυνση", font=("Arial", 13)); e4.pack(side="left", padx=4)
        lst = ctk.CTkScrollableFrame(box, fg_color=CARD, height=420); lst.pack(fill="both", expand=True, padx=8, pady=8)

        def delete_cust(i):
            if messagebox.askyesno("Σίγουρα;", "Διαγραφή πελάτη;"):
                c = db(); c.execute("DELETE FROM customers WHERE id=?", (i,)); c.commit(); c.close()
                load()

        def load():
            for w in lst.winfo_children():
                w.destroy()
            c = db(); rows = c.execute("SELECT * FROM customers ORDER BY name").fetchall(); c.close()
            for r in rows:
                row = ctk.CTkFrame(lst, fg_color=ROWB, corner_radius=10); row.pack(fill="x", pady=4)
                ctk.CTkLabel(row, text=f"{r['name']}  •  {r['phone']}  •  {r['email']}",
                             font=("Arial", 13, "bold"), text_color=TXTD).pack(side="left", padx=12, pady=8)
                ctk.CTkButton(row, text="Διαγραφή", width=90, fg_color=RED,
                              command=lambda i=r["id"]: delete_cust(i)).pack(side="right", padx=6)

        def add():
            if not e1.get().strip():
                return messagebox.showwarning("Προσοχή", "Βάλε όνομα πελάτη")
            c = db(); c.execute("INSERT INTO customers(name,phone,email,address) VALUES(?,?,?,?)",
                                (e1.get().strip(), e2.get(), e3.get(), e4.get())); c.commit(); c.close()
            for e in (e1, e2, e3, e4):
                e.delete(0, "end")
            load()
        ctk.CTkButton(fr, text="＋ Προσθήκη", font=("Arial", 13, "bold"), command=add).pack(side="left", padx=6)
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
