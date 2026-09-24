"""Reseed Demo Data for GeM Bid Compliance Verification Platform.

Resets the database tables and populates realistic demo bids and bidders
with 100% cryptographically verified audit chains for live presentations.
"""

import os
import sys
import time
from pathlib import Path

# Ensure repo root is on sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from backend import database, extraction, forensics, verification, scoring, recommendations, eligibility


def reseed_demo():
    print("=================================================================")
    print(" ARCHON: Database Reset & Demo Reseed Pipeline")
    print("=================================================================")
    print("Connecting to PostgreSQL...")
    conn = database.connect(read_only=False)
    try:
        print("Resetting database tables...")
        database.reset_db()
        database.init_db()

        samples_dir = root_dir / "samples"
        vantara_pdf_path = samples_dir / "bid_vantara_systems.pdf"
        northstar_pdf_path = samples_dir / "bid_northstar_traders.pdf"

        if not vantara_pdf_path.exists() or not northstar_pdf_path.exists():
            print("Generating sample PDFs first...")
            from samples import generate_samples
            generate_samples.main()

        def ingest_bid(pdf_path: Path, bidder_name: str, tender_id: str, claimed_turnover: float = 85000000.0, claimed_local: float = 65.0):
            data = pdf_path.read_bytes()
            file_sha = forensics.sha256_bytes(data)
            extracted = extraction.analyze_pdf_bytes(data, filename=pdf_path.name)
            forens = forensics.analyze_pdf_forensics(data)
            duplicate_bids = database.find_bids_by_sha256(conn, file_sha)

            flags = []
            if extracted.get("ocr_used"):
                flags.append("ocr_low_confidence")
            for fcode in forens.get("flag_codes", []):
                if fcode not in flags:
                    flags.append(fcode)
            if forens.get("incremental_update_count", 0) > 0 and "document_tamper_detected" not in flags:
                flags.append("document_tamper_detected")

            gstin_val = extracted.get("gstin")
            if gstin_val and not verification.validate_gstin_checksum(gstin_val):
                flags.append("gstin_checksum_invalid")

            registry_results = verification.verify_registry_checks(conn, extracted)
            for r in registry_results:
                if r.get("debarred"):
                    flags.append("debarment_match")
                if r.get("registry") == "EPFO / ESIC" and not r.get("ecr_filed_current_month"):
                    flags.append("epfo_esic_noncompliant")

            if duplicate_bids:
                flags.append("recycled_document_detected")

            extracted["declared_revenue"] = claimed_turnover
            extracted["declared_local_content"] = claimed_local

            eligibility_res = eligibility.check_eligibility(tender_id, extracted)
            if eligibility_res.get('eligible') is False:
                flags.append('tender_ineligible')

            score_res = scoring.compute_score(flags)
            recom = recommendations.recommend({"score": score_res, "flags": flags, "eligibility": eligibility_res})

            import uuid
            bid_id = uuid.uuid4().hex[:8]
            bid_row = {
                "id": bid_id,
                "bidder_name": bidder_name,
                "tender_id": tender_id,
                "filename": pdf_path.name,
                "file_sha256": file_sha,
                "uploaded_at": round(time.time(), 3),
                "compliance_score": score_res["score"],
                "risk_level": score_res["risk_level"],
                "report": {
                    "id": bid_id,
                    "bidder_name": bidder_name,
                    "tender_id": tender_id,
                    "tender_title": eligibility_res.get("tender_title") or tender_id,
                    "filename": pdf_path.name,
                    "extraction": extracted,
                    "forensics": forens,
                    "registry_results": registry_results,
                    "eligibility": eligibility_res,
                    "score": score_res,
                    "recommendation": recom,
                    "recycled_document": {
                        "is_recycled": bool(duplicate_bids),
                        "prior_submissions": duplicate_bids
                    }
                }
            }

            database.insert_bid(conn, bid_row, commit=False)
            database.append_audit(conn, bidder_name, "BID_SUBMITTED", bid_id, {"filename": pdf_path.name, "tender_id": tender_id}, commit=False)
            database.append_audit(conn, "EXTRACTION_ENGINE", "EXTRACTION_COMPLETE", bid_id, extracted, commit=False)
            database.append_audit(conn, "FORENSIC_ENGINE", "FORENSIC_SCAN_COMPLETE", bid_id, forens, commit=False)
            database.append_audit(conn, "GOVT_REGISTRY_GATEWAY", "REGISTRY_LOOKUPS_COMPLETE", bid_id, {"results": registry_results}, commit=False)
            database.append_audit(conn, "ELIGIBILITY_ENGINE", "ELIGIBILITY_CHECK_COMPLETE", bid_id, eligibility_res, commit=False)
            if duplicate_bids:
                database.append_audit(conn, "FORENSIC_ENGINE", "RECYCLED_DOCUMENT_DETECTED", bid_id, {"prior_submissions": duplicate_bids}, commit=False)
            database.append_audit(conn, "RISK_SCORING_ENGINE", "SCORE_COMPUTED", bid_id, score_res, commit=False)

            # Also register in bidders directory
            database.upsert_bidder(conn, {
                "entity_name": bidder_name,
                "gstin": extracted.get("gstin"),
                "pan": extracted.get("pan"),
                "cin": extracted.get("cin"),
                "udyam_number": extracted.get("udyam"),
                "business_type": "Corporate" if extracted.get("cin") else "Enterprise",
                "msme_category": "MSME" if extracted.get("udyam") else "Large Enterprise"
            }, commit=False)

            conn.commit()
            print(f"  + Ingested bid: '{bidder_name}' | Score: {score_res['score']} | Risk: {score_res['risk_level']}")
            return bid_id

        print("\n--- Submitting 1: Clean Bid (Vantara Systems) ---")
        ingest_bid(vantara_pdf_path, "Vantara Systems Pvt Ltd", "GEM-2026-IT-00417", claimed_turnover=85000000.0, claimed_local=65.0)

        print("\n--- Submitting 2: Flagged Bid (North Star Traders) ---")
        ingest_bid(northstar_pdf_path, "North Star Traders", "GEM-2026-IT-00417", claimed_turnover=21000000.0, claimed_local=15.0)

        print("\n--- Submitting 3: Recycled Document / Collusion Trigger ---")
        ingest_bid(vantara_pdf_path, "Delta Infra Solutions Ltd", "GEM-2026-IT-00417", claimed_turnover=82000000.0, claimed_local=60.0)

        print("\n--- Verifying Audit Trail Cryptographic Hash Chain ---")
        verify_res = database.verify_audit_chain(conn)
        print("Audit Chain Verification Result:", verify_res)
        assert verify_res["ok"] is True, f"Audit chain verification failed: {verify_res}"
        print(" SUCCESS: All demo bids ingested with 100% verified audit log chain!")

    finally:
        database.release(conn, commit=True)


if __name__ == "__main__":
    reseed_demo()
