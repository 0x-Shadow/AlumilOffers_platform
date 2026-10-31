import json, os, sys, types
# Provide dummy customtkinter module with minimal classes to allow app import
class DummyWidget:
    def __init__(self, *args, **kwargs):
        pass
    def pack(self, *args, **kwargs):
        return self
    def configure(self, *args, **kwargs):
        pass
    def bind(self, *args, **kwargs):
        pass
    def destroy(self):
        pass
    def winfo_children(self):
        return []
    def after(self, *args, **kwargs):
        pass
    def set(self, *args, **kwargs):
        pass

class DummyCTk:
    def __init__(self, *args, **kwargs):
        pass
    def title(self, *args, **kwargs):
        pass
    def geometry(self, *args, **kwargs):
        pass
    def minsize(self, *args, **kwargs):
        pass
    def pack(self, *args, **kwargs):
        return self
    def pack_propagate(self, *args, **kwargs):
        pass
    def bind(self, *args, **kwargs):
        pass
    def after(self, *args, **kwargs):
        pass
    def destroy(self):
        pass
    def winfo_children(self):
        return []
    def configure(self, *args, **kwargs):
        pass

dummy_ctk = types.SimpleNamespace(
    CTk=DummyCTk,
    CTkFrame=DummyWidget,
    CTkLabel=DummyWidget,
    CTkButton=DummyWidget,
    CTkEntry=DummyWidget,
    CTkScrollableFrame=DummyWidget,
    CTkImage=lambda *a, **kw: None,
    set_appearance_mode=lambda *a, **kw: None,
    set_default_color_theme=lambda *a, **kw: None,
)
sys.modules['customtkinter'] = dummy_ctk

from app import make_pdf, init_db

# Ensure DB is initialized (creates tables if missing)
init_db()

quote = {
    "number": "TEST001",
    "date": "01/01/2025",
    "customer_name": "Test Customer",
    "customer_info": "Test Info",
    "items_json": json.dumps([
        {"name": "ΔΙΦΥΛΛΟ ΕΠΑΛΛΗΛΟ EUROPA 5500 HYBRID (180x220 εκ.) - 1ος-ΠΡΟΣΟΨΗ", "qty": 1, "unit": "τεμ.", "price": 1900},
        {"name": "ΔΙΦΥΛΛΟ ΕΠΑΛΛΗΛΟ ΜΕ ΣΙΤΑ (330x235 εκ.) - 1ος-ΓΩΝΙΑΚΟ", "qty": 1, "unit": "τεμ.", "price": 3400},
        {"name": "ΔΙΦΥΛΛΟ ΕΠΑΛΛΗΛΟ ΜΕ ΣΙΤΑ (255x75 εκ.) - 1ος-ΓΩΝΙΑΚΟ", "qty": 3, "unit": "τεμ.", "price": 1300},
        {"name": "Συρόμενο παράθυρο με shutter", "qty": 2, "unit": "τεμ.", "price": 800},
        {"name": "Σταθερό παράθυρο", "qty": 1, "unit": "τεμ.", "price": 450},
    ]),
    "designs_json": "[]",
    "subtotal": 11250.0,
    "vat_rate": 24.0,
    "vat_amount": 2700.0,
    "total": 13950.0,
    "include_labor": 0,
    "labor_amount": 0.0,
    "labor_desc": ""
}

pdf_path = os.path.join(os.path.dirname(__file__), "PDF_Prosfores", "test_quote.pdf")
make_pdf(quote, pdf_path)
print(f"PDF generated at: {pdf_path}")