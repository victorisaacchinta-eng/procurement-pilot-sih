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


# ---------------------------------------------------------------- tender document (rulebook demo)
def banner(c, w, h):
    c.setFillColor(HexColor("#C8102E")); c.rect(0, h - 70, w, 70, fill=1, stroke=0)
    c.setFillColor(HexColor("#FFFFFF")); c.setFont("Helvetica-Bold", 13)
    c.drawString(40, h - 32, "SAMPLE DOCUMENT FOR A PROTOTYPE DEMO. NOT ISSUED BY ANY GOVERNMENT AUTHORITY.")
    c.setFont("Helvetica", 10); c.drawString(40, h - 52, "Procurement Pilot, Team Ace Azael, SIH 2026. All numbers are fictional.")
    c.setFillColor(HexColor("#111010"))


def lines(c, y, rows, size=10.5, gap=19):
    for k, v in rows:
        if k:
            c.setFont("Helvetica-Bold", size); c.drawString(40, y, k)
            c.setFont("Helvetica", size); c.drawString(300, y, v)
        else:
            c.setFont("Helvetica", size); c.drawString(40, y, v)
        y -= gap
    return y


NIT = "tanker-transport-tender-sample.pdf"
c = canvas.Canvas(str(OUT / NIT), pagesize=A4)
w, h = A4
c.setTitle("Sample tender document: tank truck transportation services")
banner(c, w, h)
c.setFont("Helvetica-Bold", 17); c.drawString(40, h - 115, "Bid Document (sample)")
c.setFont("Helvetica", 10.5); c.drawString(40, h - 134, "Tank truck transportation services for petroleum product distribution (12 months)")
y = lines(c, h - 172, [
    ("Bid Number", "GEM/2026/B/5512874"),
    ("Bid End Date/Time", "28-11-2026 15:00:00"),
    ("Organisation Name", "Sample Refinery Ltd (fictional)"),
    ("Contract Period", "12 Months"),
    ("Estimated Bid Value", "Rs 95 Lakh"),
    ("Minimum Average Annual Turnover of the bidder (For 3 Years)", ""),
    ("", "Rs 4 Crore"),
    ("Years of Past Experience Required for same/similar service", ""),
    ("", "3 Years"),
    ("MSE Exemption for Years of Experience and Turnover", "No"),
    ("Startup Exemption for Years of Experience and Turnover", "No"),
    ("EMD Detail", ""),
    ("EMD Amount", "Rs 1,80,000"),
])
c.setFont("Helvetica-Bold", 12); c.drawString(40, y - 10, "Document required from seller")
lines(c, y - 34, [
    ("", "1. GST registration certificate"),
    ("", "2. Copy of PAN card"),
    ("", "3. Audited balance sheets for the last three financial years"),
    ("", "4. PESO licence for petroleum tank trucks"),
    ("", "5. Vehicle registration certificates (RC) for every tank truck offered"),
])
c.setFont("Helvetica", 9); c.setFillColor(HexColor("#55524E")); c.drawString(40, 40, "Page 1 of 2")
c.showPage()
banner(c, w, h)
c.setFont("Helvetica-Bold", 14); c.drawString(40, h - 115, "Additional terms and conditions (sample)")
lines(c, h - 150, [
    ("", "1. The bidder shall deploy a fleet of at least 8 tank trucks, each under 10 years old and fitted with GPS."),
    ("", "2. Every driver shall hold a hazardous goods endorsement on the driving licence."),
    ("", "3. The service provider shall comply with EPF and ESIC for all drivers and helpers deployed,"),
    ("", "    and shall pay not less than the notified minimum wages."),
    ("", "4. Tank trucks shall carry a valid PESO licence and calibration certificate at all times."),
    ("", "5. Short delivery beyond 0.1% of the loaded quantity shall be recovered at the invoice rate."),
], size=10, gap=20)
c.setFont("Helvetica-Oblique", 10); c.setFillColor(HexColor("#55524E"))
c.drawString(40, h - 300, "What this sample shows in the demo: the tender record says Rs 40 lakh minimum turnover;")
c.drawString(40, h - 316, "the document asks for Rs 4 crore. Applying the rulebook changes the result for one bidder.")
c.setFont("Helvetica", 9); c.drawString(40, 40, "Page 2 of 2")
c.showPage(); c.save()
print("wrote", NIT)


# ---------------------------------------------------------------- scanned registration (OCR demo)
# An image-only PDF: no text layer at all, like a phone photo or a flatbed scan. pypdf reads
# nothing from it; Sarvam Vision (Document AI) reads it.
from io import BytesIO  # noqa: E402
import random  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: E402
from reportlab.lib.utils import ImageReader  # noqa: E402

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
img = Image.new("L", (1240, 1754), 246)
d = ImageDraw.Draw(img)
f_b, f, f_s = ImageFont.truetype(BOLD, 30), ImageFont.truetype(FONT, 26), ImageFont.truetype(FONT, 21)
d.rectangle([0, 0, 1240, 120], fill=70)
d.text((50, 30), "SAMPLE FOR A PROTOTYPE DEMO. NOT ISSUED BY ANY AUTHORITY.", font=f_b, fill=246)
d.text((50, 76), "Procurement Pilot, Team Ace Azael, SIH 2026. All details are fictional.", font=f_s, fill=230)
d.text((50, 190), "Bidder registration details (scanned sample)", font=f_b, fill=20)
rows = [("Legal Name of Business", "Ratnagiri Roadlines Pvt Ltd"), ("GSTIN", "27AAHCR6652N1ZP"), ("PAN", "AAHCR6652N"),
        ("CIN", "U60231MH2023PTC166520"), ("Udyam Registration Number", "Not applicable"),
        ("Principal place of business", "11 MIDC Road, Ratnagiri")]
y = 280
for k, v in rows:
    d.text((50, y), f"{k}: {v}", font=f, fill=25); y += 62
d.text((50, y + 40), "Scanned copy. There is no text layer in this PDF.", font=f_s, fill=90)
rnd = random.Random(7)
for _ in range(9000):  # scanner speckle
    x, yy = rnd.randrange(1240), rnd.randrange(130, 1754)
    d.point((x, yy), fill=rnd.randrange(120, 220))
img = img.rotate(0.8, resample=Image.BICUBIC, fillcolor=246).filter(ImageFilter.GaussianBlur(0.6))
buf = BytesIO(); img.save(buf, format="JPEG", quality=70); buf.seek(0)
SCAN = "ratnagiri-registration-scanned-sample.pdf"
c = canvas.Canvas(str(OUT / SCAN), pagesize=A4)
c.setTitle("Sample scanned bid document: Ratnagiri Roadlines Pvt Ltd")
c.drawImage(ImageReader(buf), 0, 0, width=A4[0], height=A4[1])
c.showPage(); c.save()
print("wrote", SCAN)
