from fastapi.testclient import TestClient
from backend.main import app
from backend import copilot_rag

client = TestClient(app)


def test_knowledge_context_assembly():
    dummy_bid = {
        "id": "BID-TEST-001",
        "company": "Vantara Industrial Systems Ltd",
        "tenderCategory": "GEM-2026-IT-004521",
        "claimedTurnover": 95000000.0,
        "claimedLocalContent": 70.0,
        "gstin": "07AAACV1234F1ZR",
        "pan": "AAACV1234F",
        "udyam": "UDYAM-DL-01-0045218",
        "score": 92,
        "risk_level": "Low"
    }
    ctx = copilot_rag.build_bid_knowledge_context(dummy_bid)
    assert ctx["bid_id"] == "BID-TEST-001"
    assert ctx["company"] == "Vantara Industrial Systems Ltd"
    assert len(ctx["pages"]) == 6
    assert any("Audited Financial" in p["title"] for p in ctx["pages"])
    assert any("Manufacturer's Authorization" in p["title"] for p in ctx["pages"])
    assert any("Non-Collusion" in p["title"] for p in ctx["pages"])


def test_quick_prompts_generation():
    clean_bid = {"id": "BID-1", "company": "Alpha Corp", "risk_level": "Low", "flags": []}
    prompts_clean = copilot_rag.generate_quick_prompts(clean_bid)
    assert len(prompts_clean) >= 4
    assert any("MSME" in p["label"] for p in prompts_clean)

    flagged_bid = {"id": "BID-2", "company": "Beta Syndicate", "risk_level": "Critical", "flags": ["cartel_ring_detected"]}
    prompts_flagged = copilot_rag.generate_quick_prompts(flagged_bid)
    assert any("Section 3(3)" in p["label"] for p in prompts_flagged)
    assert any("GFR 173" in p["label"] for p in prompts_flagged)


def test_sovereign_rag_msme_query():
    bid = {
        "id": "BID-MSME",
        "company": "Micro Tech Solutions",
        "udyam": "UDYAM-MH-01-998877",
        "claimedTurnover": 12000000.0
    }
    res = copilot_rag.ask_copilot(bid, "Does this bidder qualify for MSME exemption on EMD?")
    assert "response" in res
    assert "Udyam" in res["response"] or "MSME" in res["response"]
    assert len(res["citations"]) >= 1
    assert any("UDYAM" in c.get("snippet", "") or "MSME" in c.get("clause", "") for c in res["citations"])
    assert res["confidence"] >= 0.90


def test_sovereign_rag_cartel_query():
    bid = {
        "id": "BID-CARTEL",
        "company": "North Star Traders",
        "risk_level": "Critical",
        "flags": ["SHARED_METADATA_FINGERPRINT", "COORDINATED_PRICING"],
        "forensics": {"producer": "ModifiedDesignPDFEngine v4.2"}
    }
    res = copilot_rag.ask_copilot(bid, "Explain why this bid is flagged for collusion under Section 3(3)")
    assert "response" in res
    assert "Competition Act" in res["response"]
    assert "GeM GTC Clause 18" in res["response"]
    assert len(res["citations"]) >= 1
    assert any(a.get("action") == "OPEN_SCN_MODAL" or "Notice" in a.get("label", "") for a in res["suggested_actions"])


def test_sovereign_rag_turnover_query():
    bid = {
        "id": "BID-FIN",
        "company": "Enterprise Systems Ltd",
        "claimedTurnover": 85000000.0
    }
    res = copilot_rag.ask_copilot(bid, "What is the audited annual turnover and UDIN status?")
    assert "UDIN" in res["response"]
    assert "Turnover" in res["response"]
    assert len(res["citations"]) >= 1


def test_copilot_api_endpoints():
    # 1. Quick Prompts
    prompts_res = client.get("/api/copilot/quick-prompts")
    assert prompts_res.status_code == 200
    data = prompts_res.json()
    assert "prompts" in data
    assert len(data["prompts"]) >= 3

    # 2. Chat with Bid
    chat_res = client.post("/api/copilot/chat", json={
        "query": "Check OEM authorization letter and warranty terms",
        "conversation_history": []
    })
    assert chat_res.status_code == 200
    chat_data = chat_res.json()
    assert "response" in chat_data
    assert "citations" in chat_data
    assert "confidence" in chat_data
    assert len(chat_data["citations"]) >= 1
    assert "OEM" in chat_data["response"] or "Authorization" in chat_data["response"]
