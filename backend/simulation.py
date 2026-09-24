"""Autonomous Synthetic Bid Injector & Simulation Mode ('Chaos / Live Attack Demo').

Generates synthetic collusive bidding rings under Section 3(3) of Competition Act 2002,
Rule 175 of GFR 2017, and GeM GTC Clause 18 to demonstrate real-time topological
cartel detection and forensic document hash clustering.
"""

import os
import json
import time
import uuid
import hashlib
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("gem.simulation")

# Shared cryptographic byte collision digest across the 3 syndicate bids
COLLUSION_ATTACK_SHA256 = "c8f10a7b45e99812401f8d39e8751a0293847561829304857182938475618293"
DEFAULT_TENDER_ID = "GEM-2026-IT-004521"
DEFAULT_TENDER_TITLE = "National Supply & Managed Maintenance of Enterprise IT Hardware"

# Thread-safe in-memory store for active simulated bids
_SIM_LOCK = threading.Lock()
_SIMULATED_ATTACK_BIDS: List[Dict[str, Any]] = []


def get_samples_attack_dir() -> Path:
    root = Path(__file__).resolve().parent.parent
    attack_dir = root / "samples" / "attack"
    attack_dir.mkdir(parents=True, exist_ok=True)
    return attack_dir


def generate_physical_attack_pdfs(tender_id: str) -> List[Dict[str, str]]:
    """Generates 3 physical valid PDF files with embedded collusion metadata in samples/attack/."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except ImportError:
        log.warning("ReportLab not available; skipping physical PDF disk write.")
        return []

    attack_dir = get_samples_attack_dir()
    entities = [
        ("bid_attack_apex_syndicate.pdf", "Apex Syndicate Technologies Pvt Ltd", "27AAACA1122K1Z9", "AAACA1122K", "₹47,800,000 (L1 Baseline)"),
        ("bid_attack_apex_infra.pdf", "Apex Infra Solutions LLP", "27AAACA9988L1Z3", "AAACA9988L", "₹54,200,000 (Cover Bid +13.4%)"),
        ("bid_attack_zenith_matrix.pdf", "Zenith Cloud Matrix LLP", "27AAACA5544M1Z5", "AAACA5544M", "₹58,900,000 (Cover Bid +23.2%)"),
    ]

    generated_files = []
    for fname, name, gstin, pan, quote_str in entities:
        filepath = attack_dir / fname
        try:
            c = canvas.Canvas(str(filepath), pagesize=letter)
            c.setFont("Helvetica-Bold", 14)
            c.drawString(54, 730, "GOVERNMENT e-MARKETPLACE (GeM) — BID SUBMISSION DOSSIER")
            c.setFont("Helvetica", 9)
            c.drawString(54, 715, f"Tender Reference: {tender_id} | Statutory Annexure Form B")

            c.setFont("Helvetica-Bold", 11)
            c.drawString(54, 680, "1. BIDDER IDENTIFICATION & STATUTORY REGISTRATIONS")
            c.setFont("Helvetica", 10)
            c.drawString(64, 660, f"Legal Entity Name: {name}")
            c.drawString(64, 642, f"GSTIN: {gstin} (Maharashtra Jurisdiction)")
            c.drawString(64, 624, f"Permanent Account Number (PAN): {pan}")
            c.drawString(64, 606, f"Private Domain: bids@apex-syndicate.in")

            c.setFont("Helvetica-Bold", 11)
            c.drawString(54, 570, "2. FINANCIAL QUOTATION & BID PRICING SCHEDULE")
            c.setFont("Helvetica", 10)
            c.drawString(64, 550, f"Total Lump-Sum Offer: {quote_str}")
            c.drawString(64, 532, "Delivery Timeline: 30 Days Ex-Factory | Warranty: 36 Months On-site")

            c.setFont("Helvetica-Bold", 11)
            c.drawString(54, 495, "3. CRYPTOGRAPHIC INTEGRITY & COLLUSION UNDERTAKING")
            c.setFont("Helvetica", 9)
            c.drawString(64, 477, f"Technical Schedule SHA-256 Digest: {COLLUSION_ATTACK_SHA256[:32]}...")
            c.drawString(64, 462, f"Engine Signature: SyndicateDOC-PDF-Engine v4.2")
            c.drawString(64, 447, "I hereby declare that this bid has been arrived at independently without anti-competitive collusion.")

            c.showPage()
            c.save()
            generated_files.append({"filename": fname, "path": str(filepath)})
        except Exception as e:
            log.warning("Could not write PDF %s: %s", fname, e)

    return generated_files


def build_synthetic_attack_bids(tender_id: str = DEFAULT_TENDER_ID) -> List[Dict[str, Any]]:
    """Constructs the 3 synthetic bids with exact forensic collision properties."""
    now = time.time()
    t_id = tender_id or DEFAULT_TENDER_ID

    specifications = [
        {
            "id": "sim_apex_syndicate",
            "company": "Apex Syndicate Technologies Pvt Ltd",
            "gstin": "27AAACA1122K1Z9",
            "pan": "AAACA1122K",
            "cin": "U72200MH2017PTC291042",
            "udyam": "UDYAM-MH-12-0048123",
            "email": "bids@apex-syndicate.in",
            "tenure_quote": 47800000.0,
            "claimedTurnover": 52000000.0,
            "role": "Syndicate Leader (Intended L1 Winner)",
            "offset_seconds": 0,
        },
        {
            "id": "sim_apex_infra",
            "company": "Apex Infra Solutions LLP",
            "gstin": "27AAACA9988L1Z3",
            "pan": "AAACA9988L",
            "cin": "AAL-8912",
            "udyam": "UDYAM-MH-12-0048991",
            "email": "contracts@apex-syndicate.in",
            "tenure_quote": 54200000.0,
            "claimedTurnover": 48000000.0,
            "role": "Cover Bidder 1 (+13.4% Artificial Cover Price)",
            "offset_seconds": 72,
        },
        {
            "id": "sim_zenith_matrix",
            "company": "Zenith Cloud Matrix LLP",
            "gstin": "27AAACA5544M1Z5",
            "pan": "AAACA5544M",
            "cin": "AAL-4451",
            "udyam": "UDYAM-MH-12-0051120",
            "email": "admin@apex-syndicate.in",
            "tenure_quote": 58900000.0,
            "claimedTurnover": 44000000.0,
            "role": "Cover Bidder 2 / Shadow Rig (+23.2% Margin)",
            "offset_seconds": 138,
        },
    ]

    built_bids = []
    for spec in specifications:
        bid_time = now - (300 - spec["offset_seconds"])
        rep = {
            "bid_id": spec["id"],
            "bidder_name": spec["company"],
            "tender_id": t_id,
            "tender_title": DEFAULT_TENDER_TITLE,
            "auction_id": t_id,
            "tenure_label": "24 Months (2 Years)",
            "tenure_period": "15-Jun-2026 to 14-Jun-2028",
            "tenure_quote": spec["tenure_quote"],
            "filename": f"{spec['id']}_bid.pdf",
            "file_sha256": COLLUSION_ATTACK_SHA256,
            "score": {
                "total": 35.0,
                "risk_level": "Critical",
                "flags": [
                    "identical_document_sha256",
                    "cartel_cover_bidding_detected",
                    "same_corporate_group_pan_root",
                    "shared_corporate_email_domain",
                    "shared_pdf_engine_metadata",
                    "synchronized_submission_timing"
                ]
            },
            "extraction": {
                "gstin": spec["gstin"],
                "pan": spec["pan"],
                "cin": spec["cin"],
                "udyam": spec["udyam"],
                "email": spec["email"],
                "declared_revenue": spec["claimedTurnover"],
                "declared_local_content": 65.0,
            },
            "forensics": {
                "file_sha256": COLLUSION_ATTACK_SHA256,
                "producer": "SyndicateDOC-PDF-Engine v4.2",
                "incremental_update_count": 2,
                "flag_codes": ["document_tamper_detected", "recycled_document_detected"]
            },
            "eligibility": {
                "eligible": False,
                "reasons": [
                    "Section 3(3) Competition Act Collusion Ring Detected",
                    "Cover Bidding Ring with Shared SHA-256 Byte Hash"
                ]
            }
        }

        b_obj = {
            "id": spec["id"],
            "bidder_name": spec["company"],
            "company": spec["company"],
            "tender_id": t_id,
            "tenderCategory": t_id,
            "auctionId": t_id,
            "auctionTitle": DEFAULT_TENDER_TITLE,
            "filename": f"{spec['id']}_bid.pdf",
            "file_sha256": COLLUSION_ATTACK_SHA256,
            "uploaded_at": bid_time,
            "compliance_score": 35.0,
            "score": 35.0,
            "risk_level": "Critical",
            "risk": "Critical",
            "flags": rep["score"]["flags"],
            "claimedTurnover": spec["claimedTurnover"],
            "claimedLocalContent": 65.0,
            "gstin": spec["gstin"],
            "pan": spec["pan"],
            "cin": spec["cin"],
            "udyam": spec["udyam"],
            "tenure_quote": spec["tenure_quote"],
            "tenureDuration": "24 Months (2 Years)",
            "tenurePeriod": "15-Jun-2026 to 14-Jun-2028",
            "report": rep,
            "role": spec["role"],
            "simulation": True
        }
        built_bids.append(b_obj)

    return built_bids


def inject_collusion_attack(tender_id: Optional[str] = None) -> Dict[str, Any]:
    """Triggers live injection of 3 synthetic cartel bids into the specified tender."""
    global _SIMULATED_ATTACK_BIDS
    t_id = (tender_id or DEFAULT_TENDER_ID).strip()

    attack_bids = build_synthetic_attack_bids(tender_id=t_id)
    generate_physical_attack_pdfs(tender_id=t_id)

    with _SIM_LOCK:
        # Filter out previous simulation runs on the same IDs
        sim_ids = {b["id"] for b in attack_bids}
        _SIMULATED_ATTACK_BIDS = [b for b in _SIMULATED_ATTACK_BIDS if b["id"] not in sim_ids]
        _SIMULATED_ATTACK_BIDS.extend(attack_bids)

    # Optional DB synchronization if available
    try:
        from backend import database
        with database.get_conn(read_only=False) as conn_w:
            cur = conn_w.cursor()
            for b in attack_bids:
                try:
                    cur.execute("""
                        INSERT INTO bids (id, bidder_name, tender_id, filename, file_sha256, uploaded_at, compliance_score, risk_level, report_json)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            bidder_name = EXCLUDED.bidder_name,
                            tender_id = EXCLUDED.tender_id,
                            filename = EXCLUDED.filename,
                            file_sha256 = EXCLUDED.file_sha256,
                            uploaded_at = EXCLUDED.uploaded_at,
                            compliance_score = EXCLUDED.compliance_score,
                            risk_level = EXCLUDED.risk_level,
                            report_json = EXCLUDED.report_json
                    """, (
                        b["id"],
                        b["bidder_name"],
                        b["tender_id"],
                        b["filename"],
                        b["file_sha256"],
                        b["uploaded_at"],
                        b["compliance_score"],
                        b["risk_level"],
                        json.dumps(b["report"], ensure_ascii=False)
                    ))
                    database.append_audit(
                        conn_w,
                        "CHAOS_SIMULATOR",
                        "CARTEL_ATTACK_SIMULATED",
                        b["id"],
                        {
                            "role": b.get("role"),
                            "sha256": COLLUSION_ATTACK_SHA256,
                            "tender_id": t_id,
                            "statutory_act": "Section 3(3) Competition Act 2002"
                        },
                        commit=False
                    )
                except Exception as inner_e:
                    log.warning("DB insert for simulated bid %s skipped: %s", b['id'], inner_e)
    except Exception as e:
        log.warning("Database unavailable for simulation sync (operating in resilient memory mode): %s", e)

    telemetry_steps = [
        {
            "step": 1,
            "time_offset_ms": 150,
            "entity": "Apex Syndicate Technologies Pvt Ltd",
            "role": "Leader",
            "action": "Bid uploaded to GeM portal. File SHA-256 fingerprint indexed.",
            "status": "INDEXED",
            "badge": "L1 PROSPECT"
        },
        {
            "step": 2,
            "time_offset_ms": 450,
            "entity": "Apex Infra Solutions LLP",
            "role": "Cover Bidder 1",
            "action": "Bid uploaded. Forensic scanner detects 100% SHA-256 byte collision with Bidder A!",
            "status": "COLLISION_FLAGGED",
            "badge": "SHA-256 COLLISION"
        },
        {
            "step": 3,
            "time_offset_ms": 800,
            "entity": "Zenith Cloud Matrix LLP",
            "role": "Cover Bidder 2",
            "action": "Bid uploaded. Common PAN Root (AAACA*) and shared private domain confirmed.",
            "status": "CARTEL_FORMED",
            "badge": "SECTION 3(3) RING DETECTED"
        }
    ]

    return {
        "ok": True,
        "attack_id": f"ATTACK-SIM-{uuid.uuid4().hex[:6].upper()}",
        "tender_id": t_id,
        "tender_title": DEFAULT_TENDER_TITLE,
        "bids_injected_count": len(attack_bids),
        "bids": attack_bids,
        "shared_file_hash": COLLUSION_ATTACK_SHA256,
        "common_pan_prefix": "AAACA",
        "private_domain": "@apex-syndicate.in",
        "statutory_act": "Section 3(3)(d) of Competition Act 2002 & GeM GTC Clause 18",
        "telemetry_steps": telemetry_steps,
        "message": f"Successfully injected 3 syndicated bids into tender {t_id} with SHA-256 byte hash collision."
    }


def reset_simulation() -> Dict[str, Any]:
    """Clears all simulated attack bids and restores clean platform baseline."""
    global _SIMULATED_ATTACK_BIDS
    with _SIM_LOCK:
        cleared_count = len(_SIMULATED_ATTACK_BIDS)
        cleared_ids = [b["id"] for b in _SIMULATED_ATTACK_BIDS]
        _SIMULATED_ATTACK_BIDS = []

    # If DB connected, clean up simulated rows
    try:
        from backend import database
        with database.get_conn(read_only=False) as conn_w:
            for bid_id in cleared_ids:
                try:
                    with conn_w.cursor() as cur:
                        cur.execute("DELETE FROM bids WHERE id = %s", (bid_id,))
                except Exception:
                    pass
    except Exception as e:
        log.warning("DB cleanup for simulated bids skipped: %s", e)

    return {
        "ok": True,
        "cleared_bids_count": cleared_count,
        "message": "Simulation cleared. All synthetic bids removed and baseline topology restored."
    }


def get_simulated_bids() -> List[Dict[str, Any]]:
    """Returns thread-safe copy of currently active simulated attack bids."""
    with _SIM_LOCK:
        return list(_SIMULATED_ATTACK_BIDS)


def is_attack_active() -> bool:
    """Returns True if simulated attack bids are currently present."""
    with _SIM_LOCK:
        return len(_SIMULATED_ATTACK_BIDS) > 0
