"""Tests for Autonomous Synthetic Bid Injector & Simulation Mode ('Chaos / Live Attack Demo')."""

import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend import simulation, cartel

client = TestClient(app)


def setup_function():
    simulation.reset_simulation()


def teardown_function():
    simulation.reset_simulation()


def test_synthetic_attack_bid_properties():
    bids = simulation.build_synthetic_attack_bids(tender_id="GEM-2026-IT-004521")
    assert len(bids) == 3
    names = [b["company"] for b in bids]
    assert "Apex Syndicate Technologies Pvt Ltd" in names
    assert "Apex Infra Solutions LLP" in names
    assert "Zenith Cloud Matrix LLP" in names

    # All share identical file SHA-256
    hashes = {b["file_sha256"] for b in bids}
    assert len(hashes) == 1
    assert list(hashes)[0] == simulation.COLLUSION_ATTACK_SHA256

    # All share corporate PAN prefix AAACA
    pans = [b["pan"] for b in bids]
    assert all(p.startswith("AAACA") for p in pans)

    # All have valid report structures
    for b in bids:
        assert "score" in b["report"]
        assert "flags" in b["report"]["score"]
        assert "identical_document_sha256" in b["report"]["score"]["flags"]


def test_cartel_detection_on_synthetic_attack():
    bids = simulation.build_synthetic_attack_bids(tender_id="GEM-TEST-TENDER")
    # Pairwise comparison between Leader and Cover Bidder 1
    pair_res = cartel.compare_bid_pair(bids[0], bids[1])
    assert pair_res is not None
    assert "IDENTICAL_DOCUMENT_SHA256" in pair_res["flags"]
    assert "SAME_CORPORATE_GROUP_PAN_ROOT" in pair_res["flags"]
    assert "SHARED_CORPORATE_EMAIL_DOMAIN" in pair_res["flags"]
    assert pair_res["confidence"] >= 0.95

    # Pairwise comparison between Cover Bidder 1 and Cover Bidder 2
    pair_res_2 = cartel.compare_bid_pair(bids[1], bids[2])
    assert pair_res_2 is not None
    assert "IDENTICAL_DOCUMENT_SHA256" in pair_res_2["flags"]
    assert pair_res_2["confidence"] >= 0.95

    # Global network graph generation includes the 3 bids
    net = cartel.build_global_cartel_network(bids, filter_tender_id="GEM-TEST-TENDER")
    assert net["metrics"]["collusion_edges_count"] == 3
    assert net["metrics"]["fingerprints_count"] == 1
    assert net["metrics"]["pan_groups_count"] == 1


def test_simulation_api_lifecycle():
    # 1. Check initial status
    status_res = client.get("/api/simulation/status")
    assert status_res.status_code == 200
    assert status_res.json()["active"] is False
    assert status_res.json()["injected_count"] == 0

    # 2. Inject attack
    inject_res = client.post("/api/simulation/inject-attack", json={"tender_id": "GEM-2026-IT-004521"})
    assert inject_res.status_code == 200
    inject_data = inject_res.json()
    assert inject_data["ok"] is True
    assert inject_data["bids_injected_count"] == 3
    assert len(inject_data["telemetry_steps"]) == 3
    assert inject_data["shared_file_hash"] == simulation.COLLUSION_ATTACK_SHA256

    # 3. Status should now report active
    status_active = client.get("/api/simulation/status").json()
    assert status_active["active"] is True
    assert status_active["injected_count"] == 3

    # 4. Network graph endpoint reflects injected cartel edges
    graph_res = client.get("/api/cartel/network-graph?tender_id=GEM-2026-IT-004521")
    assert graph_res.status_code == 200
    graph_data = graph_res.json()
    assert graph_data["metrics"]["collusion_edges_count"] >= 3

    # 5. Reset simulation
    reset_res = client.post("/api/simulation/reset")
    assert reset_res.status_code == 200
    assert reset_res.json()["ok"] is True

    # 6. Status back to inactive
    status_clean = client.get("/api/simulation/status").json()
    assert status_clean["active"] is False
    assert status_clean["injected_count"] == 0


def test_physical_pdf_generation():
    files = simulation.generate_physical_attack_pdfs(tender_id="GEM-2026-IT-004521")
    assert len(files) == 3
    for f in files:
        path = simulation.Path(f["path"])
        assert path.exists()
        assert path.stat().st_size > 1000
