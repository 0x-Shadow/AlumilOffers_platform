#!/usr/bin/env python3
"""
Draw all 26 catalog product images manually as clean architectural LINE drawings
(CAD-style elevation), matching the Alumil catalog look exactly:
 - thin gray line art (no heavy fills)
 - double-line frames
 - thin diagonal opening lines for casement/tilt
 - solid arrows for sliding
 - roller shutter box + flat cap with horizontal lines
 - vertical screen hatching
 - small handle rectangles
Saved as high-res lossless PNG.
"""
import os
from PIL import Image, ImageDraw, ImageFont

BASE = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(BASE, "Sxedia")
os.makedirs(IMG_DIR, exist_ok=True)

CANVAS = 1400

# ---------- Line art palette (grayscale, like the scan) ----------
LINE   = (45, 45, 48)      # main outline lines
LINE2  = (95, 95, 100)     # secondary/inner lines
LINEL  = (140, 140, 145)   # lightest detail lines
GLASS  = (250, 251, 252)   # glass fill (near white)
SCREENBG = (232, 235, 238) # silkscreen leaf bg
SHUTBG = (228, 231, 235)   # shutter area fill
ARROWC = (40, 40, 42)      # solid sliding arrows
HANDLEC= (40, 40, 42)      # handles
CAPTIONC=(95, 110, 130)    # caption

WHITE = (255, 255, 255)
BG    = (255, 255, 255)

def load_font(size, bold=False):
    cand = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for p in cand:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()

def f_bold(sz): return load_font(sz, bold=True)
def f_reg(sz):  return load_font(sz, bold=False)

def rect(d, x0, y0, x1, y1, outline=LINE, width=3):
    d.rectangle([x0, y0, x1, y1], outline=outline, width=width)

def hatch_v(d, x0, y0, x1, y1, step, color=LINEL, width=2):
    xx = x0 + step
    while xx < x1:
        d.line([xx, y0, xx, y1], fill=color, width=width)
        xx += step

def hatch_h(d, x0, y0, x1, y1, step, color=LINEL, width=2):
    yy = y0 + step
    while yy < y1:
        d.line([x0, yy, x1, yy], fill=color, width=width)
        yy += step

def solid_arrow(d, x, y, direction, size, color=ARROWC):
    s = size
    if direction == "R":
        pts = [(x, y), (x - s, y + int(s * 0.55)), (x - s, y - int(s * 0.55))]
    elif direction == "L":
        pts = [(x, y), (x + s, y + int(s * 0.55)), (x + s, y - int(s * 0.55))]
    else:
        pts = [(x, y), (x - int(s * 0.55), y - s), (x + int(s * 0.55), y - s)]
    d.polygon(pts, fill=color)

def draw_product(img, d, w_cm, h_cm, category, location, shutter=False, screen=False,
                 leaves=2, tilt=False, fixed=False, door=False, transom=False):
    cx = CANVAS // 2
    pad = 90
    box_w = CANVAS - 2 * pad
    box_h = CANVAS - 2 * pad - 110
    s = min(box_w / w_cm, box_h / h_cm)
    iw, ih = int(w_cm * s), int(h_cm * s)
    if transom and ih < 150:
        s2 = 150 / h_cm
        if w_cm * s2 <= box_w:
            iw, ih = int(w_cm * s2), 150
    # shutter sits on top; reserve vertical room
    sh = int(ih * 0.26) if shutter else 0  # shutter box height
    total_h = ih + sh
    top = (CANVAS - 110 - total_h) // 2 + 40
    x0 = cx - iw // 2
    x1 = x0 + iw
    y0 = top + sh          # frame top
    y1 = y0 + ih           # frame bottom

    ft = max(8, int(min(iw, ih) * 0.045))   # frame line offset

    # ---- roller shutter box on top ----
    if shutter:
        cap_out = max(6, int(iw * 0.02))
        sy1 = y0
        sy0 = y0 - sh
        # bottom rail of the box (thin)
        rect(d, x0 - cap_out, sy0, x1 + cap_out, sy1, outline=LINE, width=3)
        # flat top cap
        rect(d, x0 - cap_out, sy0 - max(8, int(sh * 0.18)), x1 + cap_out, sy0, outline=LINE, width=3)
        # horizontal shutter slats
        hatch_h(d, x0 - cap_out + 8, sy0 + int(sh * 0.30), x1 + cap_out - 8, sy1 - 8,
                step=max(10, sh // 4), color=LINEL, width=2)

    # ---- outer frame (double line) ----
    rect(d, x0, y0, x1, y1, outline=LINE, width=4)
    rect(d, x0 + ft, y0 + ft, x1 - ft, y1 - ft, outline=LINE2, width=2)

    gx0, gy0 = x0 + ft, y0 + ft
    gx1, gy1 = x1 - ft, y1 - ft
    d.rectangle([gx0, gy0, gx1, gy1], fill=GLASS)

    n = max(1, leaves)
    leaf_w = (gx1 - gx0) / n
    for i in range(n):
        lx0 = gx0 + i * leaf_w
        lx1 = lx0 + leaf_w
        # sash inner offset
        off = max(8, int(ft * 0.9))
        sx0, sy0i, sx1, sy1i = lx0 + off, gy0 + off, lx1 - off, gy1 - off
        is_screen = screen and i == n - 1
        if is_screen:
            d.rectangle([sx0, sy0i, sx1, sy1i], fill=SCREENBG)
        rect(d, sx0, sy0i, sx1, sy1i, outline=LINE2, width=2)

        cxm = (sx0 + sx1) // 2
        cym = (sy0i + sy1i) // 2
        glass_w = sx1 - sx0
        glass_h = sy1i - sy0i

        # opening indicator
        if fixed:
            d.line([sx0, sy0i, sx1, sy1i], fill=LINEL, width=2)
            d.line([sx0, sy1i, sx1, sy0i], fill=LINEL, width=2)
        elif transom or tilt:
            # tilt/top-hung transom: lines from both bottom corners to top centre
            d.line([sx0, sy1i, cxm, sy0i], fill=LINE2, width=2)
            d.line([sx1, sy1i, cxm, sy0i], fill=LINE2, width=2)
            # small handle bar at bottom
            d.rectangle([cxm - 10, sy1i - 10, cxm + 10, sy1i - 3], outline=HANDLEC, width=2)
        elif category == "Συρόμενο" or (door and n > 1):
            az = min(38, int(glass_w * 0.30), int(glass_h * 0.16))
            if n == 1:
                solid_arrow(d, sx0 + int(glass_w * 0.70), cym, "R", az)
            elif i == 0:
                solid_arrow(d, sx0 + int(glass_w * 0.68), cym, "R", az)
            elif i == n - 1:
                solid_arrow(d, sx0 + int(glass_w * 0.32), cym, "L", az)
            else:
                solid_arrow(d, sx0 + int(glass_w * 0.36), cym, "L", int(az * 0.8))
                solid_arrow(d, sx0 + int(glass_w * 0.64), cym, "R", int(az * 0.8))
        else:
            # casement: hinge on outer edge, opening triangle to inner (handle) edge
            if i == 0:
                d.line([sx0, sy0i, sx1, cym], fill=LINE2, width=2)
                d.line([sx0, sy1i, sx1, cym], fill=LINE2, width=2)
                hx = sx1
            else:
                d.line([sx1, sy0i, sx0, cym], fill=LINE2, width=2)
                d.line([sx1, sy1i, sx0, cym], fill=LINE2, width=2)
                hx = sx0
            # handle on the meeting edge
            d.rectangle([hx - 6 if i == 0 else hx, cym - 12,
                         hx if i == 0 else hx + 6, cym + 12], outline=HANDLEC, width=2)

        # screen hatching (vertical fine lines)
        if is_screen:
            hatch_v(d, sx0 + 4, sy0i + 4, sx1 - 4, sy1i - 4, step=max(9, glass_w // 22),
                    color=LINEL, width=2)

        # middle rebate between leaves
        if i > 0:
            mid = max(3, ft // 2)
            rect(d, lx0 - mid, gy0, lx0 + mid, gy1, outline=LINE2, width=2)

    # rotate door handle: door leaf handled on the outer edge, long bar
    if door:
        hw = max(8, int(ft * 1.1))
        hh = int(ih * 0.20)
        hx = x1 - ft - max(18, int(iw * 0.10))
        hy = gy0 + int(ih * 0.42)
        d.rectangle([hx, hy, hx + hw, hy + hh], fill=HANDLEC)

    # caption
    cap = location if location else f"{w_cm:g} x {h_cm:g} εκ."
    cw = int(d.textlength(cap, font=f_reg(28)))
    d.text(((CANVAS - cw) // 2, CANVAS - 55), cap, font=f_reg(28), fill=CAPTIONC)

def render(w_cm, h_cm, category, name, location, image_name, **feat):
    img = Image.new("RGB", (CANVAS, CANVAS), BG)
    d = ImageDraw.Draw(img)
    draw_product(img, d, w_cm, h_cm, category, location, **feat)
    path = os.path.join(IMG_DIR, image_name)
    img.save(path, "PNG")
    print(f"  drew {image_name} ({w_cm}x{h_cm}) {category}")

PRODUCTS = [
    ("Π-201", 360, 235, "Συρόμενο", "ΔΙΦΥΛΛΟ ΕΠΑΛΛΗΛΟ ΜΕ ΣΙΤΑ", "1ος-ΓΩΝΙΑΚΟ", "catalog_01.png", {"shutter": True, "screen": True, "leaves": 2}),
    ("Π-202", 255, 75,  "Συρόμενο", "ΔΙΦΥΛΛΟ ΕΠΑΛΛΗΛΟ ΜΕ ΣΙΤΑ", "1ος-ΓΩΝΙΑΚΟ", "catalog_02.png", {"screen": True, "leaves": 2}),
    ("Π-203", 243, 75,  "Παράθυρο", "ΜΟΝΟΦΥΛΛΟ ΑΝΟΙΓΟΜΕΝΟ ΦΕΓΓΙΤΗΣ", "1ος-ΓΩΝΙΑΚΟ", "catalog_03.png", {"leaves": 1, "tilt": True}),
    ("Π-204", 195, 235, "Παράθυρο", "ΔΙΦΥΛΛΟ ΑΝΟΙΓΟΜΕΝΟ ΤΖΑΜΙ", "ΙΣΟΓΕΙΟ", "catalog_04.png", {"shutter": True, "screen": True, "leaves": 2}),
    ("Π-205", 140, 220, "Μπαλκονόπορτα", "ΜΠΑΛΚΟΝΟΠΟΡΤΑ ΔΙΦΥΛΛΗ", "ΣΑΛΟΝΙ", "catalog_05.png", {"shutter": True, "screen": True, "leaves": 2, "door": True}),
    ("Π-206", 160, 140, "Συρόμενο", "ΔΙΦΥΛΛΟ ΕΠΑΛΛΗΛΟ ΑΠΛΟ", "ΥΠΝΟΔΩΜΑΤΙΟ", "catalog_06.png", {"leaves": 2}),
    ("Π-207", 80, 120,  "Παράθυρο", "ΜΟΝΟΦΥΛΛΟ ΑΝΟΙΓΟΜΕΝΟ", "ΚΟΥΖΙΝΑ", "catalog_07.png", {"leaves": 1, "tilt": True}),
    ("Π-208", 200, 150, "Σταθερό", "ΣΤΑΘΕΡΟ ΠΛΑΙΣΙΟ", "ΧΩΛ", "catalog_08.png", {"fixed": True, "leaves": 1}),
    ("Π-209", 330, 235, "Συρόμενο", "ΔΙΦΥΛΛΟ ΕΠΑΛΛΗΛΟ ΜΕ ΣΙΤΑ", "1ος-ΓΩΝΙΑΚΟ", "catalog_09.png", {"shutter": True, "screen": True, "leaves": 2}),
    ("Π-210", 255, 75,  "Συρόμενο", "ΔΙΦΥΛΛΟ ΕΠΑΛΛΗΛΟ ΜΕ ΣΙΤΑ", "1ος-ΓΩΝΙΑΚΟ", "catalog_10.png", {"screen": True, "leaves": 2}),
    ("Π-211", 243, 75,  "Παράθυρο", "ΜΟΝΟΦΥΛΛΟ ΑΝΟΙΓΟΜΕΝΟ ΦΕΓΓΙΤΗΣ", "1ος-ΓΩΝΙΑΚΟ", "catalog_11.png", {"leaves": 1, "tilt": True}),
    ("Π-212", 195, 235, "Παράθυρο", "ΔΙΦΥΛΛΟ ΑΝΟΙΓΟΜΕΝΟ ΤΖΑΜΙ", "ΙΣΟΓΕΙΟ", "catalog_12.png", {"shutter": True, "screen": True, "leaves": 2}),
    ("Π-213", 243, 78,  "Παράθυρο", "ΜΟΝΟΦΥΛΛΟ ΑΝΟΙΓΟΜΕΝΟ ΦΕΓΓΙΤΗΣ", "1ος-ΓΩΝΙΑΚΟ", "catalog_13.png", {"leaves": 1, "tilt": True}),
    ("Π-214", 150, 78,  "Παράθυρο", "ΔΙΦΥΛΛΟ ΑΝΟΙΓΟΜΕΝΟ ΤΖΑΜΙ", "ΙΣΟΓΕΙΟ", "catalog_14.png", {"shutter": True, "screen": True, "leaves": 2}),
    ("Π-215", 150, 235, "Παράθυρο", "ΔΙΦΥΛΛΟ ΑΝΟΙΓΟΜΕΝΟ ΤΖΑΜΙ", "ΙΣΟΓΕΙΟ", "catalog_15.png", {"shutter": True, "screen": True, "leaves": 2}),
    ("Π-216", 240, 235, "Συρόμενο", "ΔΙΦΥΛΛΟ ΕΠΑΛΛΗΛΟ ΜΕ ΣΙΤΑ", "1ος-ΚΑΤΩ-ΣΑΛΩΝΙ", "catalog_16.png", {"shutter": True, "screen": True, "leaves": 2}),
    ("Π-217", 250, 235, "Συρόμενο", "ΔΙΦΥΛΛΟ ΕΠΑΛΛΗΛΟ ΜΕ ΣΙΤΑ", "1ος-ΚΑΤΩ-ΣΑΛΩΝΙ", "catalog_17.png", {"shutter": True, "screen": True, "leaves": 2}),
    ("Π-218", 243, 78,  "Παράθυρο", "ΜΟΝΟΦΥΛΛΟ ΑΝΟΙΓΟΜΕΝΟ ΦΕΓΓΙΤΗΣ", "1ος-ΚΑΤΩ-ΣΑΛΩΝΙ", "catalog_18.png", {"leaves": 1, "tilt": True}),
    ("Π-219", 150, 235, "Παράθυρο", "ΔΙΦΥΛΛΟ ΑΝΟΙΓΟΜΕΝΟ ΤΖΑΜΙ", "ΙΣΟΓΕΙΟ", "catalog_19.png", {"shutter": True, "screen": True, "leaves": 2}),
    ("Π-220", 750, 235, "Παράθυρο", "ΣΕΙΡΑ ΓΛΑΣΙΩΝ", "ΣΕΙΡΑ ΓΛΑΣΙΩΝ", "catalog_20.png", {"fixed": True, "leaves": 1, "transom": True}),
    ("Π-221", 340, 235, "Συρόμενο", "ΔΙΦΥΛΛΟ ΕΠΑΛΛΗΛΟ ΜΕ ΣΙΤΑ", "3ος-ΚΑΤΩ-ΣΑΛΩΝΙ", "catalog_21.png", {"shutter": True, "screen": True, "leaves": 2}),
    ("Π-222", 370, 235, "Συρόμενο", "ΔΙΦΥΛΛΟ ΕΠΑΛΛΗΛΟ ΜΕ ΣΙΤΑ", "3ος-ΚΑΤΩ-ΣΑΛΩΝΙ", "catalog_22.png", {"shutter": True, "screen": True, "leaves": 2}),
    ("Π-223", 243, 78,  "Παράθυρο", "ΜΟΝΟΦΥΛΛΟ ΑΝΟΙΓΟΜΕΝΟ ΦΕΓΓΙΤΗΣ", "3ος-ΚΑΤΩ-ΥΠΝΟΔΩΜΑΤΙΑ", "catalog_23.png", {"leaves": 1, "tilt": True}),
    ("Π-224", 150, 235, "Παράθυρο", "ΔΙΦΥΛΛΟ ΑΝΟΙΓΟΜΕΝΟ ΤΖΑΜΙ", "3ος-ΚΑΤΩ-ΥΠΝΟΔΩΜΑΤΙΑ", "catalog_24.png", {"shutter": True, "screen": True, "leaves": 2}),
    ("Π-225", 243, 78,  "Παράθυρο", "ΜΟΝΟΦΥΛΛΟ ΑΝΟΙΓΟΜΕΝΟ ΦΕΓΓΙΤΗΣ", "3ος-ΚΑΤΩ-ΑΝΟΙΓΤΟΥ", "catalog_25.png", {"leaves": 1, "tilt": True}),
    ("Π-226", 75, 235,  "Πόρτα", "ΠΟΡΤΑ ΑΝΟΙΓΟΜΕΝΗ", "3ος-ΚΑΤΩ-ΔΙΑΔΡΟΜΟΣ", "catalog_26.png", {"door": True, "leaves": 1}),
]

print(f"Rendering {len(PRODUCTS)} product images into {IMG_DIR} ...")
for code, w, h, cat, name, loc, img_name, feat in PRODUCTS:
    render(w, h, cat, name, loc, img_name, **feat)
print("Done.")
