"""
Seed tenders, bids and simulated government registries for the prototype.

These are SAMPLE records built for the SIH26100 demo. They are not real
procurement records. Every GSTIN, PAN, CIN, Udyam, DPIIT, NSIC, EPFO and ESIC
number here is fictional; GSTINs are formatted to pass or fail the real
check-digit rule on purpose, and each PAN is the one embedded in its GSTIN.

The registries at the bottom stand in for GSTN, the Income Tax Department,
MCA21, Udyam, DPIIT (Startup India), NSIC, EPFO, ESIC, DigiLocker and the
GeM / CPPP debarment list. registry.py reads them through one adapter per
source, and every result says it is simulated.

Each bid exists to show one behaviour:
  pipeline-valves   Petrotech   clean bid, OEM, Class-I local supplier: 100
                    Vantage     trader with OEM authorisation; documents and GST legal
                                name say "Vantage Flow Solutions Ltd": two flags
  refinery-ppe      SafeGuard   DPIIT-recognised startup: EMD exempt, verified
                    Trident     no EMD and no exemption, BIS licence missing, turnover
                                short, bad GSTIN check digit, ITR gap, non-local supplier
                    Apex        on the debarment list; not the OEM and no authorisation
  tanker-transport  Konkan      verified MSE, EPFO and ESIC current: clean
                    Swift       incorporated weeks before the tender (MCA21); no ESIC
                    Ratnagiri   quote 0.38% from Swift, 2 minutes later; one document
                                only self-attested
  depot-security    Meridian    adverse public-interest record
                    Falcon      no EMD, PSARA licence missing, GST returns and EPFO
                                challans behind
  pipeline-survey   Falcon      same firm again (past performance builds up)
"""

_BASE_DOCS = ["GST registration certificate", "PAN card", "Audited financial statements"]


def _docs(required, **overrides):
    """Every required document verified through DigiLocker unless overridden."""
    return {d: overrides.get(d, "verified") for d in required}


TENDERS = {
    "pipeline-valves": {
        "title": "Supply of API 6D fire-safe pipeline valves",
        "category": "Goods",
        "authority": "CPCL",
        "authority_full": "Chennai Petroleum Corporation Limited",
        "spec": "All valves must be API 6D certified fire-safe ball valves with independent API 607 fire-safe testing.",
        "min_turnover": 6_000_000,
        "benchmark_price": 15_500_000,
        "required_documents": _BASE_DOCS + ["API 6D licence", "API 607 fire-test report"],
        "oem_authorisation_required": True,
        "labour_services": False,
        "bidders": {
            "Petrotech Valve Industries Private Limited": {
                "emd": 250_000, "turnover": 90_000_000, "price": 15_300_000,
                "claims": ["mse"], "reputational_note": "",
                "document_name": "Petrotech Valve Industries Private Limited",
                "incorporated_years_ago": 11, "address": "Plot 14, Manali Industrial Estate, Chennai",
                "gstin": "33AABCP4821K1ZJ", "udyam": "UDYAM-TN-02-0048211", "cin": "U29120TN2015PTC098765",
                "local_content_pct": 72, "oem": {"is_oem": True},
                "epfo": "TNMAS0048211000", "esic": "51000482110001001",
                "submitted_at": "2026-09-06T11:42:00+05:30",
            },
            "Vantage Flow Systems Pvt Ltd": {
                "emd": 250_000, "turnover": 78_000_000, "price": 15_200_000,
                "claims": ["mse"], "reputational_note": "",
                "document_name": "Vantage Flow Solutions Ltd",
                "incorporated_years_ago": 6, "address": "Unit 7, Guindy Industrial Estate, Chennai",
                "gstin": "33AADCV7310L1ZB", "udyam": "UDYAM-TN-02-0073102", "cin": "U51909TN2020PTC137310",
                "local_content_pct": 55, "oem": {"is_oem": False, "authorisation": "verified"},
                "epfo": "TNMAS0073102000", "esic": "51000731020001001",
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
        "required_documents": _BASE_DOCS + ["BIS licence copy"],
        "oem_authorisation_required": True,
        "labour_services": False,
        "bidders": {
            "SafeGuard Industrial Wear Pvt Ltd": {
                "emd": 0, "turnover": 31_000_000, "price": 4_180_000,
                "claims": ["startup"], "reputational_note": "",
                "document_name": "SafeGuard Industrial Wear Pvt Ltd",
                "incorporated_years_ago": 8, "address": "44 Peenya Industrial Area, Bengaluru",
                "gstin": "29AAHCS5516M1ZT", "udyam": "", "dpiit": "DIPP45516", "cin": "U18101KA2018PTC115516",
                "local_content_pct": 64, "oem": {"is_oem": True},
                "epfo": "KABNG0055160000", "esic": "53000551600001001",
                "submitted_at": "2026-09-04T12:10:00+05:30",
            },
            "Trident Protective Gear & Co": {
                "emd": 0, "turnover": 1_900_000, "price": 3_990_000,
                "claims": [], "reputational_note": "",
                "document_name": "Trident Protective Gear & Co",
                "incorporated_years_ago": 4, "address": "12 Whitefield Road, Bengaluru",
                "gstin": "29AANFT2204Q1ZX", "udyam": "", "cin": "",
                "local_content_pct": 15, "oem": {"is_oem": True},
                "epfo": "", "esic": "",
                "submitted_at": "2026-09-04T17:55:00+05:30",
                "documents": _docs(_BASE_DOCS + ["BIS licence copy"], **{"BIS licence copy": "missing"}),
            },
            "Apex Safety Products Pvt Ltd": {
                "emd": 90_000, "turnover": 26_000_000, "price": 4_350_000,
                "claims": [], "reputational_note": "",
                "document_name": "Apex Safety Products Pvt Ltd",
                "incorporated_years_ago": 9, "address": "7 Bommasandra Industrial Area, Bengaluru",
                "gstin": "29AAKCA7741E1ZI", "udyam": "", "cin": "U51397KA2017PTC107741",
                "local_content_pct": 58, "oem": {"is_oem": False, "authorisation": "missing"},
                "epfo": "KABNG0077410000", "esic": "53000774100001001",
                "submitted_at": "2026-09-04T13:30:00+05:30",
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
        "required_documents": _BASE_DOCS + ["PESO licence", "Vehicle registration certificates"],
        "oem_authorisation_required": False,
        "labour_services": True,
        "bidders": {
            "Konkan Bulk Carriers Ltd": {
                "emd": 180_000, "turnover": 51_000_000, "price": 9_350_000,
                "claims": ["mse"], "reputational_note": "",
                "document_name": "Konkan Bulk Carriers Ltd",
                "incorporated_years_ago": 9, "address": "Plot 3, JNPT Road, Navi Mumbai",
                "gstin": "27AABCK9043R1ZV", "udyam": "UDYAM-MH-33-0090431", "cin": "U60231MH2017PLC090431",
                "local_content_pct": 100, "oem": {"is_oem": False},
                "epfo": "MHBAN0090431000", "esic": "35000904310001001",
                "submitted_at": "2026-09-07T11:20:00+05:30",
            },
            "Swift Tanker Logistics Pvt Ltd": {
                "emd": 180_000, "turnover": 42_000_000, "price": 9_100_000,
                "claims": [], "reputational_note": "",
                "document_name": "Swift Tanker Logistics Pvt Ltd",
                "incorporated_years_ago": 0.2, "address": "204 Business Park, Navi Mumbai",
                "gstin": "27AAMCS1187T1ZB", "udyam": "", "cin": "U60231MH2026PTC211187",
                "local_content_pct": 100, "oem": {"is_oem": False},
                "epfo": "MHBAN0211870000", "esic": "",
                "submitted_at": "2026-09-07T16:01:00+05:30",
            },
            "Ratnagiri Roadlines Pvt Ltd": {
                "emd": 180_000, "turnover": 38_000_000, "price": 9_135_000,
                "claims": [], "reputational_note": "",
                "document_name": "Ratnagiri Roadlines Pvt Ltd",
                "incorporated_years_ago": 3, "address": "11 MIDC Road, Ratnagiri",
                "gstin": "27AAHCR6652N1ZP", "udyam": "", "cin": "U60231MH2023PTC166520",
                "local_content_pct": 100, "oem": {"is_oem": False},
                "epfo": "MHRAT0166520000", "esic": "35001665200001001",
                "submitted_at": "2026-09-07T16:03:00+05:30",
                "documents": _docs(_BASE_DOCS + ["PESO licence", "Vehicle registration certificates"],
                                   **{"Vehicle registration certificates": "self-attested"}),
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
        "required_documents": _BASE_DOCS + ["PSARA licence copy"],
        "oem_authorisation_required": False,
        "labour_services": True,
        "bidders": {
            "Meridian Guard Solutions Pvt Ltd": {
                "emd": 120_000, "turnover": 42_000_000, "price": 6_650_000,
                "claims": ["mse"],
                "document_name": "Meridian Guard Solutions Pvt Ltd",
                "incorporated_years_ago": 7, "address": "9 Rajaji Salai, Chennai",
                "gstin": "33AAECM3390P1Z3", "udyam": "UDYAM-TN-02-0033901", "cin": "U74920TN2019PTC133901",
                "local_content_pct": 100, "oem": {"is_oem": False},
                "epfo": "TNMAS0133901000", "esic": "51001339010001001",
                "submitted_at": "2026-09-05T10:14:00+05:30",
                "reputational_note": (
                    "Adverse media on record: a labour dispute involving the promoter was "
                    "reported in regional press. Officer should review before award."
                ),
            },
            "Falcon Inspection Technologies": {
                "emd": 0, "turnover": 18_000_000, "price": 6_500_000,
                "claims": [], "reputational_note": "",
                "document_name": "Falcon Inspection Technologies",
                "incorporated_years_ago": 5, "address": "17 Anna Salai, Chennai",
                "gstin": "33AAGFF8120H1ZP", "udyam": "", "cin": "",
                "local_content_pct": 100, "oem": {"is_oem": False},
                "epfo": "TNMAS0081200000", "esic": "51000812000001001",
                "submitted_at": "2026-09-05T17:40:00+05:30",
                "documents": _docs(_BASE_DOCS + ["PSARA licence copy"], **{"PSARA licence copy": "missing"}),
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
        "required_documents": _BASE_DOCS + ["NDT accreditation certificate"],
        "oem_authorisation_required": False,
        "labour_services": True,
        "bidders": {
            "Falcon Inspection Technologies": {
                "emd": 0, "turnover": 18_000_000, "price": 7_900_000,
                "claims": [], "reputational_note": "",
                "document_name": "Falcon Inspection Technologies",
                "incorporated_years_ago": 5, "address": "17 Anna Salai, Chennai",
                "gstin": "33AAGFF8120H1ZP", "udyam": "", "cin": "",
                "local_content_pct": 100, "oem": {"is_oem": False},
                "epfo": "TNMAS0081200000", "esic": "51000812000001001",
                "submitted_at": "2026-09-08T09:20:00+05:30",
            },
        },
    },
}

# Fill in the document list for bids that did not override it: all verified.
for _t in TENDERS.values():
    for _b in _t["bidders"].values():
        _b.setdefault("documents", _docs(_t["required_documents"]))
        _b.setdefault("dpiit", "")
        _b.setdefault("nsic", "")


# ---------------------------------------------------------------------------
# Simulated registries. One per source named in the problem statement.
# ---------------------------------------------------------------------------

# GSTN: registration status, legal name, and GSTR-3B returns filed of the last six due.
SIMULATED_GST_REGISTRY = {
    "33AABCP4821K1ZJ": {"legal_name": "Petrotech Valve Industries Private Limited", "status": "Active", "returns_filed": 6, "returns_due": 6},
    "33AADCV7310L1ZB": {"legal_name": "Vantage Flow Solutions Ltd", "status": "Active", "returns_filed": 6, "returns_due": 6},
    "29AAHCS5516M1ZT": {"legal_name": "SafeGuard Industrial Wear Pvt Ltd", "status": "Active", "returns_filed": 6, "returns_due": 6},
    "29AAKCA7741E1ZI": {"legal_name": "Apex Safety Products Pvt Ltd", "status": "Active", "returns_filed": 6, "returns_due": 6},
    "27AABCK9043R1ZV": {"legal_name": "Konkan Bulk Carriers Ltd", "status": "Active", "returns_filed": 6, "returns_due": 6},
    "27AAMCS1187T1ZB": {"legal_name": "Swift Tanker Logistics Pvt Ltd", "status": "Active", "returns_filed": 2, "returns_due": 2},
    "27AAHCR6652N1ZP": {"legal_name": "Ratnagiri Roadlines Pvt Ltd", "status": "Active", "returns_filed": 6, "returns_due": 6},
    "33AAECM3390P1Z3": {"legal_name": "Meridian Guard Solutions Pvt Ltd", "status": "Active", "returns_filed": 6, "returns_due": 6},
    "33AAGFF8120H1ZP": {"legal_name": "Falcon Inspection Technologies", "status": "Active", "returns_filed": 4, "returns_due": 6},
}

# Income Tax Department: PAN holder name and income tax returns filed for the last two assessment years.
SIMULATED_ITD_REGISTRY = {
    "AABCP4821K": {"name": "Petrotech Valve Industries Private Limited", "itr_filed": ["AY 2024-25", "AY 2025-26"]},
    "AADCV7310L": {"name": "Vantage Flow Solutions Ltd", "itr_filed": ["AY 2024-25", "AY 2025-26"]},
    "AAHCS5516M": {"name": "SafeGuard Industrial Wear Pvt Ltd", "itr_filed": ["AY 2024-25", "AY 2025-26"]},
    "AANFT2204Q": {"name": "Trident Protective Gear & Co", "itr_filed": ["AY 2024-25"]},
    "AAKCA7741E": {"name": "Apex Safety Products Pvt Ltd", "itr_filed": ["AY 2024-25", "AY 2025-26"]},
    "AABCK9043R": {"name": "Konkan Bulk Carriers Ltd", "itr_filed": ["AY 2024-25", "AY 2025-26"]},
    "AAMCS1187T": {"name": "Swift Tanker Logistics Pvt Ltd", "itr_filed": []},
    "AAHCR6652N": {"name": "Ratnagiri Roadlines Pvt Ltd", "itr_filed": ["AY 2024-25", "AY 2025-26"]},
    "AAECM3390P": {"name": "Meridian Guard Solutions Pvt Ltd", "itr_filed": ["AY 2024-25", "AY 2025-26"]},
    "AAGFF8120H": {"name": "Falcon Inspection Technologies", "itr_filed": ["AY 2024-25", "AY 2025-26"]},
}
ITR_YEARS_REQUIRED = ["AY 2024-25", "AY 2025-26"]

# MCA21 company master: name, status and date of incorporation.
SIMULATED_MCA21 = {
    "U29120TN2015PTC098765": {"name": "Petrotech Valve Industries Private Limited", "status": "Active", "incorporated": "2015-04-12"},
    "U51909TN2020PTC137310": {"name": "Vantage Flow Systems Pvt Ltd", "status": "Active", "incorporated": "2020-08-03"},
    "U18101KA2018PTC115516": {"name": "SafeGuard Industrial Wear Pvt Ltd", "status": "Active", "incorporated": "2018-06-21"},
    "U51397KA2017PTC107741": {"name": "Apex Safety Products Pvt Ltd", "status": "Active", "incorporated": "2017-02-14"},
    "U60231MH2017PLC090431": {"name": "Konkan Bulk Carriers Ltd", "status": "Active", "incorporated": "2017-01-09"},
    "U60231MH2026PTC211187": {"name": "Swift Tanker Logistics Pvt Ltd", "status": "Active", "incorporated": "2026-07-14"},
    "U60231MH2023PTC166520": {"name": "Ratnagiri Roadlines Pvt Ltd", "status": "Active", "incorporated": "2023-05-30"},
    "U74920TN2019PTC133901": {"name": "Meridian Guard Solutions Pvt Ltd", "status": "Active", "incorporated": "2019-03-18"},
}

# Udyam (MSME), DPIIT (Startup India) and NSIC registrations.
SIMULATED_UDYAM = {
    "UDYAM-TN-02-0048211": {"name": "Petrotech Valve Industries Private Limited", "category": "Small"},
    "UDYAM-TN-02-0073102": {"name": "Vantage Flow Systems Pvt Ltd", "category": "Small"},
    "UDYAM-MH-33-0090431": {"name": "Konkan Bulk Carriers Ltd", "category": "Small"},
    "UDYAM-TN-02-0033901": {"name": "Meridian Guard Solutions Pvt Ltd", "category": "Micro"},
}
SIMULATED_DPIIT = {
    "DIPP45516": {"name": "SafeGuard Industrial Wear Pvt Ltd", "valid_until": "2028-06-20"},
}
SIMULATED_NSIC = {}

# EPFO and ESIC: establishment name and the last monthly contribution (challan) on record.
SIMULATED_EPFO = {
    "TNMAS0048211000": {"name": "Petrotech Valve Industries Private Limited", "last_challan": "2026-08"},
    "TNMAS0073102000": {"name": "Vantage Flow Systems Pvt Ltd", "last_challan": "2026-08"},
    "KABNG0055160000": {"name": "SafeGuard Industrial Wear Pvt Ltd", "last_challan": "2026-08"},
    "KABNG0077410000": {"name": "Apex Safety Products Pvt Ltd", "last_challan": "2026-08"},
    "MHBAN0090431000": {"name": "Konkan Bulk Carriers Ltd", "last_challan": "2026-08"},
    "MHBAN0211870000": {"name": "Swift Tanker Logistics Pvt Ltd", "last_challan": "2026-08"},
    "MHRAT0166520000": {"name": "Ratnagiri Roadlines Pvt Ltd", "last_challan": "2026-08"},
    "TNMAS0133901000": {"name": "Meridian Guard Solutions Pvt Ltd", "last_challan": "2026-08"},
    "TNMAS0081200000": {"name": "Falcon Inspection Technologies", "last_challan": "2026-05"},
}
SIMULATED_ESIC = {
    "51000482110001001": {"name": "Petrotech Valve Industries Private Limited", "last_challan": "2026-08"},
    "51000731020001001": {"name": "Vantage Flow Systems Pvt Ltd", "last_challan": "2026-08"},
    "53000551600001001": {"name": "SafeGuard Industrial Wear Pvt Ltd", "last_challan": "2026-08"},
    "53000774100001001": {"name": "Apex Safety Products Pvt Ltd", "last_challan": "2026-08"},
    "35000904310001001": {"name": "Konkan Bulk Carriers Ltd", "last_challan": "2026-08"},
    "35001665200001001": {"name": "Ratnagiri Roadlines Pvt Ltd", "last_challan": "2026-08"},
    "51001339010001001": {"name": "Meridian Guard Solutions Pvt Ltd", "last_challan": "2026-08"},
    "51000812000001001": {"name": "Falcon Inspection Technologies", "last_challan": "2026-07"},
}

# GeM / CPPP debarment list (seeded). A live build reads the published lists instead.
DEBARRED = {
    "Apex Safety Products Pvt Ltd": {"until": "2027-03-31", "reason": "debarred by a procuring entity for supplying non-conforming goods"},
}
