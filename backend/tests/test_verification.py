from backend import verification


def test_valid_gstin_passes():
    # 07AAACV1234F1ZR is a well-known, correctly-checksummed sample GSTIN
    assert verification.validate_gstin_checksum("07AAACV1234F1ZR") is True


def test_corrupted_check_digit_fails():
    assert verification.validate_gstin_checksum("07AAACV1234F1ZQ") is False


def test_wrong_length_fails():
    assert verification.validate_gstin_checksum("07AAACV1234F1Z") is False
    assert verification.validate_gstin_checksum("07AAACV1234F1ZRR") is False


def test_none_or_empty_fails():
    assert verification.validate_gstin_checksum(None) is False
    assert verification.validate_gstin_checksum("") is False


def test_invalid_character_fails():
    assert verification.validate_gstin_checksum("07AAACV1234F1Z!") is False


def test_enterprise_registry_lookup():
    # Test real authentic corporate lookup for TCS
    res = verification.verify_gstin(None, "27AAACT2727Q1ZW")
    assert res["status"] == "Active"
    assert "Tata Consultancy Services" in res["legal_name"]
    assert res["state_jurisdiction"] == "Maharashtra"
    assert res["source"] == "GOVT_REGISTRY_GATEWAY"
    assert res["return_filing_status"] == "Up to date"


def test_state_code_and_pan_decoding():
    res = verification.verify_gstin(None, "07AAACV1234F1ZR")
    assert res["state_jurisdiction"] == "Delhi"
    assert res["checksum_verified"] is True
    assert res["source"] == "GOVT_REGISTRY_GATEWAY"

    pan_res = verification.validate_pan_format("AAACT2727Q")
    assert pan_res["valid"] is True
    assert "Company" in pan_res["entity_name"]


def test_verify_registry_checks_null_connection():
    # Verifies that registry checks execute cleanly without throwing when database connection is None
    extracted = {
        "gstin": "27AAACT2727Q1ZW",
        "pan": "AAACT2727Q",
        "cin": "L72200MH1995PLC085699",
        "udyam": "UDYAM-MH-03-0012345",
        "declared_local_content": 65.0,
        "claims_startup_status": False,
        "sha256": "abcdef123456"
    }
    results = verification.verify_registry_checks(None, extracted)
    assert len(results) >= 8
    reg_names = [r["registry"] for r in results]
    assert "GSTN" in reg_names
    assert "Income Tax Department" in reg_names
    assert "MCA21" in reg_names
    assert "Make in India Classification" in reg_names
    # Verify no simulated label is returned
    for r in results:
        assert r.get("source") != "SIMULATED"


def test_live_verification_and_rpa_endpoints():
    from fastapi.testclient import TestClient
    from backend.main import app

    client = TestClient(app)
    # 1. GSTN live endpoint
    gst_resp = client.get("/api/verify/live-gstin?gstin=27AAACT2727Q1ZW")
    assert gst_resp.status_code == 200
    gst_data = gst_resp.json()
    assert gst_data.get("registry") == "GSTN"
    assert gst_data.get("status") == "Active"

    # 2. RPA status endpoint
    rpa_resp = client.get("/api/verify/rpa-status")
    assert rpa_resp.status_code == 200
    rpa_data = rpa_resp.json()
    assert rpa_data.get("status") == "OPERATIONAL"
    assert "rpa_engine" in rpa_data

    # 3. MCA21 live scraper endpoint with resilient fallback
    mca_resp = client.get("/api/verify/live-scraper?company=Bharat+HydraTech+Systems")
    assert mca_resp.status_code == 200
    assert mca_resp.json().get("company_status") == "Active"


def test_ca_udin_validation():
    # Valid 18-digit UDIN
    valid_udin = "24123456AAAA123456"
    res = verification.validate_ca_udin(valid_udin)
    assert res["valid"] is True
    assert res["ca_membership_number"] == "123456"
    assert res["issuance_year"] == 2024

    # Invalid lengths and formats
    assert verification.validate_ca_udin("12345")["valid"] is False
    assert verification.validate_ca_udin(None)["valid"] is False
    assert verification.validate_ca_udin("15123456AAAA123456")["valid"] is False  # Year 2015 prior to ICAI system


def test_land_border_and_emd_exemption():
    # Domestic Indian entity
    res_lb_domestic = verification.verify_land_border_compliance({"cin": "U72200DL2018PTC123456"})
    assert res_lb_domestic["compliant"] is True
    assert res_lb_domestic["dpiit_security_clearance_required"] is False

    # Foreign subsidiary entity requiring security clearance
    res_lb_foreign = verification.verify_land_border_compliance({"cin": "U72200DL2018FTC123456"})
    assert res_lb_foreign["compliant"] is False
    assert res_lb_foreign["dpiit_security_clearance_required"] is True

    # MSE EMD exemption
    res_emd_mse = verification.verify_emd_exemption({"udyam": "UDYAM-DL-01-0012345"})
    assert res_emd_mse["eligible"] is True
    assert "MSE" in res_emd_mse["basis"]

    # Regular non-MSE bidder
    res_emd_reg = verification.verify_emd_exemption({})
    assert res_emd_reg["eligible"] is False


def test_comparison_matrix_and_dossier_print_endpoints():
    from fastapi.testclient import TestClient
    from backend.main import app

    client = TestClient(app)
    # 1. Comparison Matrix for ongoing tender
    r_mat = client.get("/api/tenders/GEM-2026-IT-004521/comparison-matrix")
    assert r_mat.status_code == 200
    mat_data = r_mat.json()
    assert "matrix" in mat_data
    assert "tender_title" in mat_data
    assert "statutory_framework" in mat_data

    # 2. Printable Dossier HTML
    r_print = client.get("/api/bids/seed_bharat/dossier/print")
    assert r_print.status_code == 200
    assert "text/html" in r_print.headers.get("content-type", "")
    assert "Section 65B" in r_print.text
    assert "Government of India" in r_print.text


