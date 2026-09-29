"""Build the sample bid documents in frontend/samples/ (demo only, clearly labelled as such)."""
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor

OUT = Path(__file__).resolve().parents[1] / "frontend" / "samples"
OUT.mkdir(exist_ok=True)
SAMPLES = [
    ("petrotech-registration-sample.pdf", "Petrotech Valve Industries Private Limited", "33AABCP4821K1ZJ",
     "UDYAM-TN-02-0048211", "U29120TN2015PTC098765", "Plot 14, Manali Industrial Estate, Chennai",
     "Everything matches the bid on record."),
    ("vantage-registration-sample.pdf", "Vantage Flow Solutions Ltd", "33AADCV7310L1ZB",
     "UDYAM-TN-02-0073102", "U51909TN2020PTC137310", "Unit 7, Guindy Industrial Estate, Chennai",
     "The legal name differs from the bidding entity."),
    ("trident-registration-sample.pdf", "Trident Protective Gear & Co", "29AANFT2204Q1ZX",
     "", "", "12 Whitefield Road, Bengaluru",
     "The GSTIN fails the check digit."),
]
for fname, name, gstin, udyam, cin, addr, purpose in SAMPLES:
    c = canvas.Canvas(str(OUT / fname), pagesize=A4)
    w, h = A4
    c.setTitle(f"Sample bid document: {name}")
    c.setFillColor(HexColor("#C8102E")); c.rect(0, h - 70, w, 70, fill=1, stroke=0)
    c.setFillColor(HexColor("#FFFFFF")); c.setFont("Helvetica-Bold", 13)
    c.drawString(40, h - 32, "SAMPLE DOCUMENT FOR A PROTOTYPE DEMO. NOT ISSUED BY ANY GOVERNMENT AUTHORITY.")
    c.setFont("Helvetica", 10); c.drawString(40, h - 52, "Procurement Pilot, Team Ace Azael, SIH 2026. All numbers are fictional.")
    c.setFillColor(HexColor("#111010")); c.setFont("Helvetica-Bold", 18)
    c.drawString(40, h - 120, "Bidder registration details (sample)")
    rows = [("Legal Name of Business", name), ("GSTIN", gstin), ("PAN", gstin[2:12]), ("Udyam Registration Number", udyam or "Not applicable"),
            ("CIN", cin or "Not applicable (not a company)"), ("Principal place of business", addr)]
    y = h - 170
    for k, v in rows:
        c.setFont("Helvetica", 11); c.drawString(40, y, f"{k}: {v}"); y -= 26
    c.setFont("Helvetica-Oblique", 10); c.setFillColor(HexColor("#55524E"))
    c.drawString(40, y - 20, f"What this sample shows in the demo: {purpose}")
    c.showPage(); c.save()
    print("wrote", fname)
