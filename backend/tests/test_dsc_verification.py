import base64
from fastapi.testclient import TestClient
from backend.main import app
from backend import dsc_verification

client = TestClient(app)


def test_generate_and_verify_clean_dsc_pdf():
    bid_info = {
        "bidder_name": "Bharat Electronics & Quantum Secure Ltd",
        "tender_id": "GEM/2026/B/882194",
        "gstin": "29AAACB1234F1Z5",
        "turnover": "INR 350.00 Cr",
        "director_name": "Dr. Aniruddh K. Sengupta",
        "director_pan": "AAFPS1234E",
        "ca_name": "e-Mudhra Sub-CA Class 3 2026"
    }

    # Generate real cryptographically signed PDF
    pdf_bytes = dsc_verification.generate_demo_dsc_signed_pdf(bid_info, tamper=False)
    assert len(pdf_bytes) > 1000
    assert b"%PDF" in pdf_bytes

    # Extract signature and certificates
    sigs = dsc_verification.extract_pdf_digital_signatures(pdf_bytes)
    assert len(sigs) == 1

    sig = sigs[0]
    assert sig["signature_type"] == "PKCS#7 / CMS (adbe.pkcs7.detached)"
    assert sig["byte_integrity"] == "VERIFIED_AUTHENTIC"
    assert sig["cca_licensed"] is True
    assert "Class-3" in sig["dsc_class"]
    assert sig["non_repudiation_enabled"] is True
    assert sig["is_active_window"] is True

    # High-level bid verification
    res = dsc_verification.verify_bid_dsc(bid_info, pdf_bytes=pdf_bytes)
    assert res["status"] == "VERIFIED_VALID"
    assert res["ca_verified"] is True
    assert res["byte_integrity"] == "VERIFIED_AUTHENTIC"
    assert res["legal_admissibility"]["admissible_under_it_act"] is True
    assert "Section 65B" in res["legal_admissibility"]["evidence_act_admissibility"]


def test_generate_and_detect_tampered_dsc_pdf():
    bid_info = {
        "bidder_name": "Corrupt Syndicate Defense Corp",
        "tender_id": "GEM/2026/B/882194",
        "gstin": "07AAACV1234F1ZR",
        "turnover": "INR 990.00 Cr",
        "director_name": "Vikram Sethi",
        "director_pan": "ABRPS1234D",
        "ca_name": "Capricorn Sub-CA Class 3"
    }

    # Generate tampered PDF (modifies post-signing byte stream)
    tampered_pdf = dsc_verification.generate_demo_dsc_signed_pdf(bid_info, tamper=True)
    assert len(tampered_pdf) > 1000

    sigs = dsc_verification.extract_pdf_digital_signatures(tampered_pdf)
    assert len(sigs) == 1

    sig = sigs[0]
    assert sig["byte_integrity"] == "TAMPERED_POST_SIGNING"

    res = dsc_verification.verify_bid_dsc(bid_info, pdf_bytes=tampered_pdf)
    assert res["status"] == "TAMPERED"
    assert "DOCUMENT_ALTERED_POST_SIGNING" in res["flags"]
    assert res["legal_admissibility"]["admissible_under_it_act"] is False


def test_unsigned_pdf_and_fallback():
    # Regular PDF without signature
    dummy_pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
    sigs = dsc_verification.extract_pdf_digital_signatures(dummy_pdf)
    assert len(sigs) == 0

    # Deterministic fallback for known seed bid
    seed_bid = {
        "id": "BID-2026-001",
        "company": "Vantara Industrial Systems Ltd",
        "tender_id": "GEM-2026-IT-004521",
        "score": 88
    }
    res = dsc_verification.verify_bid_dsc(seed_bid, pdf_bytes=None)
    assert res["status"] == "VERIFIED_VALID"
    assert res["ca_verified"] is True
    assert res["legal_admissibility"]["admissible_under_it_act"] is True


def test_api_bid_dsc_endpoint():
    # Test GET /api/bids/{bid_id}/dsc
    resp = client.get("/api/bids/BID-2026-001/dsc")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "VERIFIED_VALID"
    assert data["ca_verified"] is True
    assert "legal_admissibility" in data


def test_api_dsc_generate_demo_and_verify():
    # Test POST /api/dsc/generate-demo (Clean)
    gen_resp = client.post("/api/dsc/generate-demo", json={"tamper": False})
    assert gen_resp.status_code == 200
    gen_data = gen_resp.json()
    assert gen_data["ok"] is True
    assert gen_data["tampered"] is False
    assert "pdf_base64" in gen_data
    assert gen_data["verification"]["status"] == "VERIFIED_VALID"

    # Test POST /api/dsc/verify with the generated base64
    verify_resp = client.post("/api/dsc/verify", json={"pdf_base64": gen_data["pdf_base64"]})
    assert verify_resp.status_code == 200
    ver_data = verify_resp.json()
    assert ver_data["ok"] is True
    assert ver_data["signatures_found"] == 1
    assert ver_data["dsc_verification"]["status"] == "VERIFIED_VALID"

    # Test POST /api/dsc/generate-demo (Tampered)
    gen_tampered = client.post("/api/dsc/generate-demo", json={"tamper": True})
    assert gen_tampered.status_code == 200
    t_data = gen_tampered.json()
    assert t_data["tampered"] is True
    assert t_data["verification"]["status"] == "TAMPERED"
