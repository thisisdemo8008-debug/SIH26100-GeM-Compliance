import pytest
from fastapi.testclient import TestClient

from backend import auctions
from backend.main import app


client = TestClient(app)


def test_list_auctions_all():
    res = auctions.list_auctions()
    assert res["total_count"] == len(auctions.TENURE_AUCTIONS)
    assert res["kpis"]["ongoing"] >= 3
    assert res["kpis"]["upcoming"] >= 2
    assert res["kpis"]["ended"] >= 2
    assert res["kpis"]["total_active_pipeline"] > 0


def test_list_auctions_filter_status():
    ongoing_res = auctions.list_auctions(status="ongoing")
    assert all(a["status"] == "ongoing" for a in ongoing_res["auctions"])
    assert len(ongoing_res["auctions"]) == ongoing_res["kpis"]["ongoing"]

    upcoming_res = auctions.list_auctions(status="upcoming")
    assert all(a["status"] == "upcoming" for a in upcoming_res["auctions"])

    ended_res = auctions.list_auctions(status="ended")
    assert all(a["status"] == "ended" for a in ended_res["auctions"])


def test_list_auctions_filter_tenure():
    res_36 = auctions.list_auctions(tenure_months=36)
    assert len(res_36["auctions"]) > 0
    assert all(a["tenure_months"] == 36 for a in res_36["auctions"])


def test_list_auctions_search():
    res = auctions.list_auctions(search="Valves")
    assert any("VALV" in a["auction_id"] for a in res["auctions"])


def test_get_auction_by_id():
    a = auctions.get_auction("CPCL-2026-VALV-089")
    assert a is not None
    assert a["auction_id"] == "CPCL-2026-VALV-089"
    assert a["tenure_months"] == 36
    assert "36 Months" in a["tenure_label"]
    assert a["status"] == "ongoing"

    unknown = auctions.get_auction("NON-EXISTENT-999")
    assert unknown is None


def test_api_auctions_endpoint():
    resp = client.get("/api/auctions")
    assert resp.status_code == 200
    data = resp.json()
    assert "auctions" in data
    assert "kpis" in data
    assert data["kpis"]["ongoing"] >= 1

    resp_filtered = client.get("/api/auctions?status=ongoing")
    assert resp_filtered.status_code == 200
    for a in resp_filtered.json()["auctions"]:
        assert a["status"] == "ongoing"


def test_api_auction_detail_endpoint():
    resp = client.get("/api/auctions/CPCL-2026-VALV-089")
    assert resp.status_code == 200
    item = resp.json()
    assert item["auction_id"] == "CPCL-2026-VALV-089"
    assert item["tenure_months"] == 36

    resp_404 = client.get("/api/auctions/NON-EXISTENT-ID")
    assert resp_404.status_code == 404
