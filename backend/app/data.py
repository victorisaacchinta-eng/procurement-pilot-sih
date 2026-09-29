"""
Seed tenders and bids for the prototype.

These are SAMPLE records built for the SIH26100 demo. They are not real
procurement records, and the GSTIN / Udyam numbers are fictional (formatted to
pass or fail the real checksum rules on purpose).

Each bidder exists to demonstrate one behaviour:
  pipeline-valves   Petrotech     clean bid, 100/100
                    Vantage       document name and GSTIN legal name disagree
  refinery-ppe      SafeGuard     clean bid
                    Trident       no EMD, missing BIS licence, turnover short, bad GSTIN checksum
  tanker-transport  Konkan        clean bid
                    Swift         incorporated ~10 weeks ago (shell signal)
                    Ratnagiri     quote 0.4% from Swift, submitted 2 minutes later (collusion screen)
  depot-security    Meridian      adverse public-interest record
                    Falcon        no EMD, PSARA licence copy missing
  pipeline-survey   Falcon        same firm on a second tender (past performance builds up)
"""

TENDERS = {
    "pipeline-valves": {
        "title": "Supply of API 6D fire-safe pipeline valves",
        "category": "Goods",
        "authority": "CPCL",
        "authority_full": "Chennai Petroleum Corporation Limited",
        "spec": "All valves must be API 6D certified fire-safe ball valves with independent API 607 fire-safe testing.",
        "min_turnover": 6_000_000,
        "benchmark_price": 15_500_000,
        "bidders": {
            "Petrotech Valve Industries Private Limited": {
                "emd": 250_000, "turnover": 90_000_000, "price": 15_300_000,
                "cert": "udyam", "reputational_note": "", "documents_missing": [],
                "document_name": "Petrotech Valve Industries Private Limited",
                "incorporated_years_ago": 11, "address": "Plot 14, Manali Industrial Estate, Chennai",
                "gstin": "33AABCP4821K1ZJ", "udyam": "UDYAM-TN-02-0048211",
                "submitted_at": "2026-09-06T11:42:00+05:30",
            },
            "Vantage Flow Systems Pvt Ltd": {
                "emd": 250_000, "turnover": 78_000_000, "price": 15_200_000,
                "cert": "msme", "reputational_note": "", "documents_missing": [],
                "document_name": "Vantage Flow Solutions Ltd",
                "incorporated_years_ago": 6, "address": "Unit 7, Guindy Industrial Estate, Chennai",
                "gstin": "33AADCV7310L1ZB", "udyam": "UDYAM-TN-02-0073102",
                "submitted_at": "2026-09-06T16:05:00+05:30",
            },
        },
    },
    "refinery-ppe": {
        "title": "Supply of flame-retardant PPE kits for refinery operations (2,000 kits)",
        "category": "Goods",
        "authority": "ONGC",
        "authority_full": "Oil and Natural Gas Corporation",
        "spec": "All coveralls must be IS 15298 (Part 2) certified flame-retardant garments, with a valid BIS licence.",
        "min_turnover": 2_500_000,
        "benchmark_price": 4_200_000,
        "bidders": {
            "SafeGuard Industrial Wear Pvt Ltd": {
                "emd": 90_000, "turnover": 31_000_000, "price": 4_180_000,
                "cert": "startup", "reputational_note": "", "documents_missing": [],
                "document_name": "SafeGuard Industrial Wear Pvt Ltd",
                "incorporated_years_ago": 8, "address": "44 Peenya Industrial Area, Bengaluru",
                "gstin": "29AAHCS5516M1ZT", "udyam": "",
                "submitted_at": "2026-09-04T12:10:00+05:30",
            },
            "Trident Protective Gear & Co": {
                "emd": 0, "turnover": 1_900_000, "price": 3_990_000,
                "cert": "none", "reputational_note": "", "documents_missing": ["BIS licence copy"],
                "document_name": "Trident Protective Gear & Co",
                "incorporated_years_ago": 4, "address": "12 Whitefield Road, Bengaluru",
                "gstin": "29AANFT2204Q1ZX", "udyam": "",
                "submitted_at": "2026-09-04T17:55:00+05:30",
            },
        },
    },
    "tanker-transport": {
        "title": "Tank truck transportation services for petroleum product distribution (12 months)",
        "category": "Services",
        "authority": "CPCL",
        "authority_full": "Chennai Petroleum Corporation Limited",
        "spec": "Bidder must hold a valid PESO licence for petroleum tanker transport and a fleet of at least 8 verified vehicles.",
        "min_turnover": 4_000_000,
        "benchmark_price": 9_500_000,
        "bidders": {
            "Konkan Bulk Carriers Ltd": {
                "emd": 180_000, "turnover": 51_000_000, "price": 9_350_000,
                "cert": "msme", "reputational_note": "", "documents_missing": [],
                "document_name": "Konkan Bulk Carriers Ltd",
                "incorporated_years_ago": 9, "address": "Plot 3, JNPT Road, Navi Mumbai",
                "gstin": "27AABCK9043R1ZV", "udyam": "UDYAM-MH-33-0090431",
                "submitted_at": "2026-09-07T11:20:00+05:30",
            },
            "Swift Tanker Logistics Pvt Ltd": {
                "emd": 180_000, "turnover": 42_000_000, "price": 9_100_000,
                "cert": "none", "reputational_note": "", "documents_missing": [],
                "document_name": "Swift Tanker Logistics Pvt Ltd",
                "incorporated_years_ago": 0.2,
                "address": "204 Business Park, Navi Mumbai",
                "gstin": "27AAMCS1187T1ZB", "udyam": "",
                "submitted_at": "2026-09-07T16:01:00+05:30",
            },
            "Ratnagiri Roadlines Pvt Ltd": {
                "emd": 180_000, "turnover": 38_000_000, "price": 9_135_000,
                "cert": "none", "reputational_note": "", "documents_missing": [],
                "document_name": "Ratnagiri Roadlines Pvt Ltd",
                "incorporated_years_ago": 3, "address": "11 MIDC Road, Ratnagiri",
                "gstin": "27AAHCR6652N1ZP", "udyam": "",
                "submitted_at": "2026-09-07T16:03:00+05:30",
            },
        },
    },
    "depot-security": {
        "title": "Security and surveillance services for fuel storage depots",
        "category": "Services",
        "authority": "MoPNG",
        "authority_full": "Ministry of Petroleum and Natural Gas",
        "spec": "Bidder must be PSARA-licensed with a minimum of 5 years operating a static guarding and CCTV monitoring contract of comparable scale.",
        "min_turnover": 3_000_000,
        "benchmark_price": 6_800_000,
        "bidders": {
            "Meridian Guard Solutions Pvt Ltd": {
                "emd": 120_000, "turnover": 42_000_000, "price": 6_650_000,
                "cert": "msme", "documents_missing": [],
                "document_name": "Meridian Guard Solutions Pvt Ltd",
                "incorporated_years_ago": 7, "address": "9 Rajaji Salai, Chennai",
                "gstin": "33AAECM3390P1Z3", "udyam": "UDYAM-TN-02-0033901",
                "submitted_at": "2026-09-05T10:14:00+05:30",
                "reputational_note": (
                    "Adverse media on record: a labour dispute involving the promoter was "
                    "reported in regional press. Officer should review before award."
                ),
            },
            "Falcon Inspection Technologies": {
                "emd": 0, "turnover": 18_000_000, "price": 6_500_000,
                "cert": "none", "reputational_note": "", "documents_missing": ["PSARA licence copy"],
                "document_name": "Falcon Inspection Technologies",
                "incorporated_years_ago": 5, "address": "17 Anna Salai, Chennai",
                "gstin": "33AAGFF8120H1ZP", "udyam": "",
                "submitted_at": "2026-09-05T17:40:00+05:30",
            },
        },
    },
    "pipeline-survey": {
        "title": "Pipeline integrity inspection and NDT survey services",
        "category": "Services",
        "authority": "CPCL",
        "authority_full": "Chennai Petroleum Corporation Limited",
        "spec": "Bidder must hold a valid PESO-recognised NDT (non-destructive testing) accreditation and ASNT Level II certified inspectors on staff.",
        "min_turnover": 3_500_000,
        "benchmark_price": 8_000_000,
        "bidders": {
            "Falcon Inspection Technologies": {
                "emd": 0, "turnover": 18_000_000, "price": 7_900_000,
                "cert": "none", "reputational_note": "", "documents_missing": [],
                "document_name": "Falcon Inspection Technologies",
                "incorporated_years_ago": 5, "address": "17 Anna Salai, Chennai",
                "gstin": "33AAGFF8120H1ZP", "udyam": "",
                "submitted_at": "2026-09-08T09:20:00+05:30",
            },
        },
    },
}

# Simulated GST registry: GSTIN -> legal name on record. Stands in for a GST
# data provider until a live key is configured (see registry.py).
SIMULATED_GST_REGISTRY = {
    "33AABCP4821K1ZJ": "Petrotech Valve Industries Private Limited",
    "33AADCV7310L1ZB": "Vantage Flow Solutions Ltd",
    "29AAHCS5516M1ZT": "SafeGuard Industrial Wear Pvt Ltd",
    "27AABCK9043R1ZV": "Konkan Bulk Carriers Ltd",
    "27AAMCS1187T1ZB": "Swift Tanker Logistics Pvt Ltd",
    "27AAHCR6652N1ZP": "Ratnagiri Roadlines Pvt Ltd",
    "33AAECM3390P1Z3": "Meridian Guard Solutions Pvt Ltd",
    "33AAGFF8120H1ZP": "Falcon Inspection Technologies",
}

# Seeded debarment list. Empty in the demo; a live build would read the
# GeM / CPPP debarred-bidders list instead.
DEBARRED = set()
