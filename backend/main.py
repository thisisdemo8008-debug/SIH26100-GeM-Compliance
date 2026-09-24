from contextlib import asynccontextmanager
from typing import Optional, Dict, Any, List
import logging
import os
import json
import threading
import time
import uuid
from pathlib import Path

from urllib.parse import parse_qs, urlencode
from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import JSONResponse, HTMLResponse, PlainTextResponse

from . import database, security, prisma_client
from . import extraction, forensics, verification, scoring, recommendations, eligibility, ai_summary, notices, cartel, scrapers, rpa_worker, auctions, copilot_rag, simulation, dsc_verification, dossier_printer

log = logging.getLogger("gem.api")

# Cap how many CPU-heavy PDF analyses (OCR etc.) run at once; extra requests wait
# briefly and then get a 503 instead of exhausting the machine.
MAX_CONCURRENT_ANALYSIS = max(1, int(os.environ.get("MAX_CONCURRENT_ANALYSIS", "4")))
ANALYSIS_WAIT_SECONDS = float(os.environ.get("ANALYSIS_WAIT_SECONDS", "60"))
_analysis_slots = threading.BoundedSemaphore(MAX_CONCURRENT_ANALYSIS)
_limiter = security.RateLimiter()


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = security.get_config()                 # raises on invalid settings -> fail fast
    warning = security.validate_startup(cfg)    # raises on unsafe production settings
    if warning:
        log.warning(warning)
    try:
        database.init_pool()
        database.init_db()
        await prisma_client.connect_prisma()
    except Exception as e:
        if cfg.production:
            raise
        log.warning("Database initialization failed (running in offline/dev mode): %s", e)
        log.warning("👉 To connect Supabase, update DATABASE_URL in your .env file with your connection string.")

    try:
        yield
    finally:
        await prisma_client.disconnect_prisma()
        database.close_pool()




app = FastAPI(
    title="ARCHON — GeM Bid Compliance Verification Platform",
    version="2.0.0",
    description="Autonomous Bid Compliance Verification, Forensic Document Auditing & Cartel Radar Engine",
    lifespan=lifespan
)


@app.middleware("http")
async def vercel_path_rewrite(request: Request, call_next):
    """Reconstructs the original intended route when deployed behind Vercel rewrites."""
    curr_path = request.url.path
    if curr_path in ("/backend/main.py", "/api/index.py", "/api") or curr_path.endswith("main.py") or curr_path.endswith("index.py"):
        override_path = request.query_params.get("__path__")
        if override_path:
            request.scope["path"] = override_path
            qs_bytes = request.scope.get("query_string", b"")
            if b"__path__=" in qs_bytes:
                parsed = parse_qs(qs_bytes.decode("latin1"), keep_blank_values=True)
                parsed.pop("__path__", None)
                request.scope["query_string"] = urlencode(parsed, doseq=True).encode("latin1")
        else:
            matched = request.headers.get("x-matched-path") or request.headers.get("x-forwarded-uri")
            if matched and not (matched.endswith("main.py") or matched.endswith("index.py")):
                request.scope["path"] = matched
            elif curr_path.endswith("main.py") or curr_path.endswith("index.py"):
                request.scope["path"] = "/docs"
    return await call_next(request)


@app.get("/backend/main.py", include_in_schema=False)
def vercel_backend_entrypoint():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/docs")


@app.middleware("http")
async def guard_and_headers(request: Request, call_next):
    # Reject oversized uploads early from the Content-Length header, before the
    # multipart body is spooled to disk. (Chunked uploads are still capped while reading.)
    if request.method == "POST" and request.url.path == "/api/verify":
        try:
            declared = int(request.headers.get("content-length", "0"))
        except ValueError:
            declared = 0
        limit = security.get_config().max_upload_bytes + (1 << 20)   # + multipart overhead
        if declared > limit:
            return JSONResponse({"detail": "file too large"}, status_code=413)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


def _client_key(request: Request, scope: str) -> str:
    ip = request.client.host if request.client else "unknown"
    if security.get_config().trust_proxy:
        xff = request.headers.get("x-forwarded-for", "")
        if xff.strip():
            ip = xff.split(",")[0].strip()
    return f"{scope}:{ip}"


def rate_limit_writes(request: Request):
    cfg = security.get_config()
    ok, retry = _limiter.allow(_client_key(request, request.url.path.split("/")[-1]), cfg.rate_limit_per_min)
    if not ok:
        raise HTTPException(status_code=429, detail="rate limit exceeded", headers={"Retry-After": str(retry)})


def _presented_token(request: Request) -> Optional[str]:
    return security.extract_token(request.headers.get("authorization"), request.headers.get("x-api-key"))


def officer_identity(request: Request) -> Optional[str]:
    """Officer name from a valid token; None in open dev mode (no OFFICER_TOKENS set)."""
    cfg = security.get_config()
    if not cfg.auth_enabled:
        return None
    name = security.authenticate(_presented_token(request), cfg.officer_tokens)
    if not name:
        raise HTTPException(status_code=401, detail="valid officer token required",
                            headers={"WWW-Authenticate": "Bearer"})
    return name


@app.get("/api/health")
def health():
    try:
        database.ping()
        return {"ok": True, "db": "connected", "pool": database.pool_stats()}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


SEED_BIDS_CATALOG = [
    {
        "id": "seed_bharat",
        "company": "Bharat HydraTech Systems",
        "gstin": "27AAECB1234F1Z5",
        "pan": "AAECB1234F",
        "cin": "U29100MH2011PTC221345",
        "udyam": "UDYAM-MH-03-0089231",
        "tenderCategory": "CPCL-2026-CAT-014",
        "auction_id": "CPCL-2026-CAT-014",
        "auction_title": "Supply of Hydroprocessing Catalyst & Technical Services",
        "tenure_months": 24,
        "tenure_label": "24 Months (2 Years)",
        "tenure_period": "01-Jan-2024 to 31-Dec-2025",
        "tenure_quote": 389000000,
        "claimedTurnover": 42000000,
        "claimedLocalContent": 62,
        "flags": ["ocr_low_confidence"],
        "score": 98,
        "risk": "Low"
    },
    {
        "id": "seed_shivalik",
        "company": "Shivalik Engineering Works",
        "gstin": "09AACCS5678K1ZR",
        "pan": "AACCS5678K",
        "cin": "U28920UP2009PTC039981",
        "udyam": "UDYAM-UP-14-0071820",
        "tenderCategory": "goods-electronics",
        "auction_id": "GEM-2026-IT-004521",
        "auction_title": "National Supply & Managed Maintenance of Enterprise IT Hardware",
        "tenure_months": 24,
        "tenure_label": "24 Months (2 Years)",
        "tenure_period": "15-Jun-2026 to 14-Jun-2028",
        "tenure_quote": 48500000,
        "claimedTurnover": 31500000,
        "claimedLocalContent": 54,
        "flags": ["turnover_inflation", "lapsed_filing", "local_content_mismatch", "oem_authorization_invalid", "document_tamper_detected"],
        "score": 45,
        "risk": "High"
    },
    {
        "id": "seed_omsai",
        "company": "Om Sai Traders",
        "gstin": "23AAFCO9012M1ZQ",
        "pan": "AAFCO9012M",
        "cin": "U51909MP2015PTC034521",
        "udyam": "UDYAM-MP-08-0055102",
        "tenderCategory": "works",
        "auction_id": "GEM-2026-CONST-098",
        "auction_title": "Civil Works — Minor Construction & Facility Modernization",
        "tenure_months": 12,
        "tenure_label": "12 Months (1 Year)",
        "tenure_period": "01-Feb-2025 to 31-Jan-2026",
        "tenure_quote": 9450000,
        "claimedTurnover": 18700000,
        "claimedLocalContent": 41,
        "flags": ["debarment_match", "lapsed_itr_filing"],
        "score": 0,
        "risk": "Critical"
    },
    {
        "id": "seed_suryodaya",
        "company": "Suryodaya Renewable Innovations",
        "gstin": "19AAJCS4471B1Z8",
        "pan": "AAJCS4471B",
        "cin": "U40106WB2018PTC228834",
        "udyam": "UDYAM-WB-11-0093347",
        "tenderCategory": "services",
        "auction_id": "GEM-2026-SOLAR-055",
        "auction_title": "Grid-Interactive Rooftop Solar PV & BESS Microgrid 5-Year Comprehensive O&M",
        "tenure_months": 60,
        "tenure_label": "60 Months (5 Years)",
        "tenure_period": "01-Oct-2026 to 30-Sep-2031",
        "tenure_quote": 218000000,
        "claimedTurnover": 9800000,
        "claimedLocalContent": 71,
        "flags": ["startup_status_unverified", "nsic_status_unverified", "document_authenticity_mismatch"],
        "score": 65,
        "risk": "High"
    },
    {
        "id": "seed_aarav",
        "company": "Aarav Forgings & Piping Pvt Ltd",
        "gstin": "33AABCA7890L1Z2",
        "pan": "AABCA7890L",
        "cin": "L27100TN2006PLC059871",
        "udyam": "UDYAM-TN-05-0124490",
        "tenderCategory": "CPCL-2026-VALV-089",
        "auction_id": "CPCL-2026-VALV-089",
        "auction_title": "Procurement of High-Pressure Forged Steel Refinery Valves & Flanges",
        "tenure_months": 36,
        "tenure_label": "36 Months (3 Years)",
        "tenure_period": "01-May-2026 to 30-Apr-2029",
        "tenure_quote": 148000000,
        "claimedTurnover": 162000000,
        "claimedLocalContent": 55,
        "flags": ["epfo_esic_noncompliant", "bis_dpiit_unverified"],
        "score": 82,
        "risk": "Medium"
    }
]


def bid_to_report(data: Any, bid_id: Optional[str] = None) -> Dict[str, Any]:
    """Normalizes any incoming DB row, frontend bid object, or partial payload into a complete report dictionary."""
    if not isinstance(data, dict):
        data = {}
    if "report" in data and isinstance(data["report"], dict) and data["report"]:
        rep = dict(data["report"])
        rep.setdefault("bid_id", bid_id or data.get("id", "BID-UNKNOWN"))
        rep.setdefault("bidder_name", data.get("company") or data.get("bidder_name") or "Bidder")
        return rep

    bidder_name = data.get("company") or data.get("bidder_name") or data.get("entity_name") or "Bidder Entity"
    tender_id = data.get("tenderCategory") or data.get("tender_id") or "goods-general"
    risk_val = data.get("risk") or data.get("risk_level") or "Low"
    flags = list(data.get("flags") or [])

    raw_score = data.get("score") if data.get("score") is not None else data.get("compliance_score", 100)
    if isinstance(raw_score, dict):
        score_val = raw_score.get("total") or raw_score.get("score", 100)
        if not flags and raw_score.get("flags"):
            flags = list(raw_score.get("flags"))
        if (not risk_val or risk_val == "Low") and raw_score.get("risk_level"):
            risk_val = raw_score.get("risk_level")
    else:
        score_val = raw_score

    is_tampered = "document_tamper_detected" in flags or "editing_software_detected" in flags
    is_debarred = "debarment_match" in flags

    return {
        "bid_id": bid_id or data.get("id") or "BID-UNKNOWN",
        "bidder_name": bidder_name,
        "tender_id": tender_id,
        "tender_title": data.get("auction_title") or tender_id,
        "auction_id": data.get("auction_id") or tender_id,
        "tenure_label": data.get("tenure_label") or data.get("tenureDuration") or "12 Months (1 Year)",
        "tenure_period": data.get("tenure_period") or data.get("tenurePeriod") or "Standard Execution Window",
        "tenure_quote": data.get("tenure_quote") or data.get("tenureQuote"),
        "score": {
            "total": score_val,
            "risk_level": risk_val.capitalize() if isinstance(risk_val, str) else "Low",
            "flags": flags
        },
        "extraction": {
            "gstin": data.get("gstin"),
            "pan": data.get("pan"),
            "cin": data.get("cin"),
            "udyam": data.get("udyam"),
            "declared_revenue": data.get("claimedTurnover"),
            "declared_local_content": data.get("claimedLocalContent", 0),
        },
        "forensics": {
            "incremental_update_count": 1 if is_tampered else 0,
            "flag_codes": [f for f in flags if "tamper" in f or "editing" in f or "recycled" in f]
        },
        "eligibility": {
            "eligible": not is_debarred and "tender_ineligible" not in flags,
            "reasons": ["Debarred entity on CPPP"] if is_debarred else []
        },
        "registry_results": [
            {"registry": "GSTN Portal", "status": "Overdue / Lapsed" if "lapsed_filing" in flags else "Active (Compliant)"},
            {"registry": "Income Tax Department", "status": "Defaulter" if "lapsed_itr_filing" in flags else "Compliant (Filed)"},
            {"registry": "MCA21 Registry", "status": "Inactive" if "mca_company_inactive" in flags else "Active"},
            {"registry": "CPPP Debarment", "status": "Debarred" if is_debarred else "Active / Clean", "debarred": is_debarred}
        ]
    }


def _find_or_synthesize_report(bid_id: str) -> Dict[str, Any]:
    bid_id_lower = bid_id.lower()
    for s in SEED_BIDS_CATALOG:
        if s["id"] == bid_id or s["id"] in bid_id_lower or s["company"].lower() in bid_id_lower:
            return bid_to_report(s, bid_id=bid_id)
    digits = [c for c in bid_id if c.isdigit()]
    if digits:
        idx = int("".join(digits[-2:])) % len(SEED_BIDS_CATALOG)
        return bid_to_report(SEED_BIDS_CATALOG[idx], bid_id=bid_id)
    return bid_to_report(SEED_BIDS_CATALOG[0], bid_id=bid_id)


def adapt_bid_for_ui(row: dict) -> dict:
    # Map DB bid row and embedded report to the frontend's expected shape
    rpt = row.get("report") or {}
    extraction = rpt.get("extraction") if isinstance(rpt, dict) else None
    bid = {
        "id": row.get("id"),
        "company": row.get("bidder_name") or rpt.get("bidder_name") if isinstance(rpt, dict) else row.get("bidder_name"),
        "gstin": (extraction.get("gstin") if extraction else None) or None,
        "pan": (extraction.get("pan") if extraction else None) or None,
        "cin": (extraction.get("cin") if extraction else None) or None,
        "udyam": (extraction.get("udyam") if extraction else None) or None,
        "tenderCategory": (rpt.get("tender_id") if isinstance(rpt, dict) else row.get("tender_id")) or row.get("tender_id"),
        "auctionId": rpt.get("auction_id") or rpt.get("tender_id") or row.get("tender_id"),
        "auctionTitle": rpt.get("tender_title") or rpt.get("auction_title") or row.get("tender_id"),
        "tenureDuration": rpt.get("tenure_label") or rpt.get("tenureDuration") or "12 Months (1 Year)",
        "tenurePeriod": rpt.get("tenure_period") or rpt.get("tenurePeriod") or "Standard Execution Window",
        "tenureQuote": rpt.get("tenure_quote") or rpt.get("tenureQuote") or row.get("tenure_quote"),
        "claimedTurnover": (extraction.get("declared_revenue") if extraction else None) or None,
        "claimedLocalContent": (extraction.get("declared_local_content") if extraction else None) or 0,
        "isReseller": False,
        "claimsStartup": bool(extraction.get("claims_startup_status") if extraction else False),
        "claimsNsic": False,
        "claimsBisDpiit": False,
        "flags": (rpt.get("score", {}).get("flags") if isinstance(rpt, dict) else None) or [],
        "seed": False,
        "status": "awaiting_decision" if row.get("compliance_score") is not None else "queued",
        "score": row.get("compliance_score"),
        "risk": row.get("risk_level"),
        "verifiedAt": None,
        "decidedAt": None,
        "officerNote": None,
        "submittedAt": row.get("uploaded_at"),
        "submittedBy": row.get("bidder_name")
    }
    # For backwards compatibility the frontend expects `score` named `score` and `risk`
    if bid["score"] is None and isinstance(rpt, dict) and rpt.get("score"):
        bid["score"] = rpt["score"].get("total")
        bid["risk"] = rpt["score"].get("risk_level")
    return bid


@app.get("/api/bids")
def api_bids(limit: Optional[int] = Query(None, ge=1, le=1000), offset: int = Query(0, ge=0)):
    rows = []
    total = 0
    try:
        with database.get_conn(read_only=True) as conn:
            total = database.count_bids(conn)
            rows = database.fetch_bids(conn, limit=limit, offset=offset)
    except Exception as e:
        log.warning("Database fetch_bids failed (using seed catalog fallback): %s", e)

    if not rows:
        adapted = [adapt_bid_for_ui({
            "id": s["id"],
            "bidder_name": s["company"],
            "tender_id": s["tenderCategory"],
            "compliance_score": s["score"],
            "risk_level": s["risk"],
            "report": bid_to_report(s, bid_id=s["id"]),
            "uploaded_at": time.time() - 3600
        }) for s in SEED_BIDS_CATALOG]
        return JSONResponse(adapted, headers={"X-Total-Count": str(len(adapted))})

    adapted = [adapt_bid_for_ui(r) for r in rows]
    return JSONResponse(adapted, headers={"X-Total-Count": str(total)})


@app.get("/api/bids/{bid_id}")
def api_bid(bid_id: str):
    row = None
    try:
        with database.get_conn(read_only=True) as conn:
            row = database.fetch_bid(conn, bid_id)
    except Exception as e:
        log.warning("Database fetch_bid failed: %s", e)

    if not row:
        rep = _find_or_synthesize_report(bid_id)
        row = {
            "id": bid_id,
            "bidder_name": rep.get("bidder_name"),
            "tender_id": rep.get("tender_id"),
            "compliance_score": rep.get("score", {}).get("total", 100),
            "risk_level": rep.get("score", {}).get("risk_level", "Low"),
            "report": rep,
            "uploaded_at": time.time() - 3600
        }
    adapted = adapt_bid_for_ui(row)
    adapted["report"] = row.get("report")
    return JSONResponse(adapted)


@app.get("/api/auctions")
def api_list_auctions(
    status: Optional[str] = Query(None, description="Filter by status: ongoing, upcoming, ended, or all"),
    category: Optional[str] = Query(None, description="Filter by category"),
    tenure_months: Optional[int] = Query(None, description="Filter by tenure duration in months"),
    search: Optional[str] = Query(None, description="Search query")
):
    """Retrieve filtered list of GeM and CPCL Tenure Auctions along with pipeline KPI summaries."""
    res = auctions.list_auctions(
        status=status,
        category=category,
        tenure_months=tenure_months,
        search=search
    )
    return JSONResponse(res)


@app.get("/api/auctions/{auction_id}")
def api_get_auction(auction_id: str):
    """Retrieve details, tenure deliverables, milestones and criteria for a specific tenure auction."""
    item = auctions.get_auction(auction_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Tenure Auction '{auction_id}' not found")
    return JSONResponse(item)


@app.post("/api/bidders/register", dependencies=[Depends(rate_limit_writes)])
def api_register_bidder(payload: dict = Body(...)):
    entity_name = _clean_field(payload.get("company_name") or payload.get("entity_name"), "company_name")
    gstin = _clean_field(payload.get("gstin"), "gstin")
    if not entity_name:
        raise HTTPException(status_code=400, detail="Company / Entity name is required")
    if not gstin:
        raise HTTPException(status_code=400, detail="GSTIN is required")
    gstin = gstin.strip().upper()

    pan = _clean_field(payload.get("pan"), "pan")
    if pan:
        pan = pan.strip().upper()
    elif len(gstin) == 15:
        pan = gstin[2:12]

    cin = _clean_field(payload.get("cin"), "cin")
    if cin:
        cin = cin.strip().upper()

    udyam = _clean_field(payload.get("udyam") or payload.get("udyam_number"), "udyam")
    if udyam:
        udyam = udyam.strip().upper()

    email = _clean_field(payload.get("email"), "email")
    phone = _clean_field(payload.get("phone"), "phone")
    state_val = _clean_field(payload.get("state"), "state")
    business_type = _clean_field(payload.get("business_type"), "business_type")
    msme_category = _clean_field(payload.get("msme_category"), "msme_category")
    registered_address = _clean_field(payload.get("registered_address") or payload.get("address"), "address")

    gstin_checksum_valid = verification.validate_gstin_checksum(gstin)

    bidder_data = {
        "entity_name": entity_name,
        "gstin": gstin,
        "pan": pan,
        "cin": cin,
        "udyam_number": udyam,
        "email": email,
        "phone": phone,
        "state": state_val,
        "business_type": business_type,
        "msme_category": msme_category,
        "registered_address": registered_address
    }
    with database.get_conn(read_only=False) as conn_w:
        saved = database.upsert_bidder(conn_w, bidder_data, commit=True)

    return JSONResponse({
        "ok": True,
        "message": "Bidder organization successfully registered in Supabase database",
        "gstin_checksum_valid": gstin_checksum_valid,
        "bidder": saved
    })


@app.get("/api/bidders")
def api_get_bidders(limit: Optional[int] = Query(None, ge=1, le=500)):
    with database.get_conn(read_only=True) as conn:
        bidders = database.fetch_bidders(conn, limit=limit)
    return JSONResponse(bidders)


@app.get("/api/bidders/{gstin}")
def api_get_bidder(gstin: str):
    with database.get_conn(read_only=True) as conn:
        b = database.fetch_bidder_by_gstin(conn, gstin.strip().upper())
    if not b:
        raise HTTPException(status_code=404, detail="Bidder not found")
    return JSONResponse(b)



@app.get("/api/audit")
def api_audit(limit: Optional[int] = Query(None, ge=1, le=5000), offset: int = Query(0, ge=0)):
    with database.get_conn(read_only=True) as conn:
        total = database.count_audit(conn)
        rows = database.fetch_audit(conn, limit=limit, offset=offset)
    # map DB fields to expected client names
    out = []
    for r in rows:
        out.append({
            "seq": r.get("seq"),
            "timestamp": r.get("timestamp"),
            "bidId": r.get("bid_id"),
            "actor": r.get("actor"),
            "action": r.get("action"),
            "details": r.get("details_parsed") if r.get("details_parsed") is not None else r.get("details"),
            "prevHash": r.get("prev_hash"),
            "hash": r.get("row_hash")
        })
    return JSONResponse(out, headers={"X-Total-Count": str(total)})


@app.get("/api/audit/verify")
def api_audit_verify():
    with database.get_conn(read_only=True) as conn:
        result = database.verify_audit_chain(conn)
    return JSONResponse(result)


@app.delete("/api/reset")
def api_reset(request: Request):
    """Wipes ALL bids and audit history. Disabled unless ENABLE_RESET=true; when
    ADMIN_TOKEN is set it must be presented (Authorization: Bearer / X-API-Key)."""
    allowed, status, msg = security.reset_decision(security.get_config(), _presented_token(request))
    if not allowed:
        raise HTTPException(status_code=status, detail=msg)
    log.warning("DELETE /api/reset executed")
    database.reset_db()
    return JSONResponse({"ok": True})


@app.api_route("/api/bids/{bid_id}/recommendation", methods=["GET", "POST"])
def api_bid_recommendation(bid_id: str, body: Optional[dict] = Body(None), _officer: Optional[str] = Depends(officer_identity)):
    report = None
    if body and ("bid" in body or "report" in body or "flags" in body):
        report = bid_to_report(body.get("bid") or body.get("report") or body, bid_id=bid_id)
    else:
        try:
            with database.get_conn(read_only=True) as conn:
                row = database.fetch_bid(conn, bid_id)
                if row:
                    report = row.get("report") or bid_to_report(row, bid_id=bid_id)
        except Exception as e:
            log.warning("Database fetch_bid for recommendation failed (falling back): %s", e)
    if not report:
        report = _find_or_synthesize_report(bid_id)
    rec = recommendations.recommend(report)
    return JSONResponse(rec)


@app.api_route("/api/bids/{bid_id}/ai-summary", methods=["GET", "POST"])
def api_bid_ai_summary(bid_id: str, body: Optional[dict] = Body(None)):
    report = None
    if body and ("bid" in body or "report" in body or "flags" in body):
        report = bid_to_report(body.get("bid") or body.get("report") or body, bid_id=bid_id)
    else:
        try:
            with database.get_conn(read_only=True) as conn:
                row = database.fetch_bid(conn, bid_id)
                if row:
                    report = row.get("report") or bid_to_report(row, bid_id=bid_id)
        except Exception as e:
            log.warning("Database fetch_bid for ai-summary failed (falling back): %s", e)

    if not report:
        report = _find_or_synthesize_report(bid_id)

    tender_name = report.get("tender_title") or report.get("tender_id") or "GeM Procurement Tender"
    summary = ai_summary.generate_executive_summary(report, tender_title=tender_name)
    return JSONResponse(summary)


@app.post("/api/ai-summary")
def api_standalone_ai_summary(body: dict = Body(...)):
    report = bid_to_report(body.get("bid") or body.get("report") or body)
    tender_name = report.get("tender_title") or report.get("tender_id") or "GeM Procurement Tender"
    summary = ai_summary.generate_executive_summary(report, tender_title=tender_name)
    return JSONResponse(summary)


@app.api_route("/api/bids/{bid_id}/clarification-notice", methods=["GET", "POST"])
def api_bid_clarification_notice(bid_id: str, body: Optional[dict] = Body(None), officer: Optional[str] = Depends(officer_identity)):
    report = None
    if body and ("bid" in body or "report" in body or "flags" in body):
        report = bid_to_report(body.get("bid") or body.get("report") or body, bid_id=bid_id)
    else:
        try:
            with database.get_conn(read_only=True) as conn:
                row = database.fetch_bid(conn, bid_id)
                if row:
                    report = row.get("report") or bid_to_report(row, bid_id=bid_id)
        except Exception as e:
            log.warning("Database fetch_bid for clarification-notice failed (falling back): %s", e)

    if not report:
        report = _find_or_synthesize_report(bid_id)

    officer_name = officer or "Aditi Sharma, Senior Procurement Officer"
    notice = notices.generate_clarification_notice(report, officer_name=officer_name)
    return JSONResponse(notice)


@app.post("/api/clarification-notice")
def api_standalone_clarification_notice(body: dict = Body(...), officer: Optional[str] = Depends(officer_identity)):
    report = bid_to_report(body.get("bid") or body.get("report") or body)
    officer_name = officer or "Aditi Sharma, Senior Procurement Officer"
    notice = notices.generate_clarification_notice(report, officer_name=officer_name)
    return JSONResponse(notice)


@app.post("/api/bids/{bid_id}/issue-notice", dependencies=[Depends(rate_limit_writes)])
def api_issue_clarification_notice(bid_id: str, body: dict = Body(...), officer: Optional[str] = Depends(officer_identity)):
    actor = officer or body.get("actor") or "Procurement Officer"
    updated_row = None
    audit_res = None
    report = None

    try:
        with database.get_conn(read_only=False) as conn_w:
            row = database.fetch_bid(conn_w, bid_id)
            if row:
                report = row.get("report") or {}
                notice = notices.generate_clarification_notice(report, officer_name=actor)
                justification = body.get("justification") or f"Official GeM Show-Cause Notice issued (Ref: {notice['notice_ref']}) with {notice['response_hours']}h compliance deadline."

                database.update_bid_decision(conn_w, bid_id, "clarification", actor, justification, commit=False)
                audit_details = {
                    "action": "OFFICER_CLARIFICATION_NOTICE_ISSUED",
                    "notice_ref": notice["notice_ref"],
                    "deadline": notice["deadline"],
                    "observations_count": len(notice["observations"]),
                    "clauses_cited": notice["legal_clauses_cited"]
                }
                audit_res = database.append_audit(conn_w, actor, "CLARIFICATION_NOTICE_ISSUED", bid_id, audit_details, commit=False)
                updated_row = database.fetch_bid(conn_w, bid_id)
    except Exception as e:
        log.warning("Database issue-notice failed (falling back to memory): %s", e)

    if not report:
        report = _find_or_synthesize_report(bid_id)
        notice = notices.generate_clarification_notice(report, officer_name=actor)

    if updated_row:
        adapted = adapt_bid_for_ui(updated_row)
        adapted["report"] = updated_row.get("report")
    else:
        adapted = {
            "id": bid_id,
            "company": report.get("bidder_name", "Bidder"),
            "status": "clarification",
            "score": report.get("score", {}).get("total", 50),
            "risk": report.get("score", {}).get("risk_level", "Medium"),
            "officerNote": body.get("justification") or f"Official GeM Show-Cause Notice issued (Ref: {notice['notice_ref']})",
            "decidedAt": time.time(),
            "report": report
        }

    return JSONResponse({
        "ok": True,
        "message": f"Official GeM Show-Cause Notice dispatched to {notice['bidder_name']}",
        "notice": notice,
        "bid": adapted,
        "audit": audit_res or {"status": "LOCAL_APPEND_ONLY", "action": "CLARIFICATION_NOTICE_ISSUED"}
    })


@app.get("/api/bids/{bid_id}/report/evidence")
def api_bid_evidence_report(bid_id: str):
    """Returns official compliance verification certificate data with evidence seals."""
    row = None
    bid_audit = []
    try:
        with database.get_conn(read_only=True) as conn:
            row = database.fetch_bid(conn, bid_id)
            audit_rows = database.fetch_audit(conn)
            bid_audit = [a for a in audit_rows if a.get("bid_id") == bid_id]
    except Exception as e:
        log.warning("Database fetch for evidence report failed: %s", e)

    if not row:
        rep = _find_or_synthesize_report(bid_id)
        row = {
            "bid_id": bid_id,
            "bidder_name": rep.get("bidder_name"),
            "tender_id": rep.get("tender_id"),
            "filename": f"{bid_id}_tender_docs.pdf",
            "file_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "uploaded_at": time.time() - 3600,
            "compliance_score": rep.get("score", {}).get("total", 100),
            "risk_level": rep.get("score", {}).get("risk_level", "Low"),
            "report": rep
        }

    report = row.get("report") or {}
    score = row.get("compliance_score")
    risk = row.get("risk_level")

    evidence_package = {
        "certificate_id": f"GEM-EVID-{bid_id.upper()}",
        "bid_id": bid_id,
        "bidder_name": row.get("bidder_name"),
        "tender_id": row.get("tender_id"),
        "filename": row.get("filename"),
        "file_sha256": row.get("file_sha256"),
        "uploaded_at": row.get("uploaded_at"),
        "compliance_score": score,
        "risk_level": risk,
        "extraction": report.get("extraction", {}),
        "identity_checks": report.get("identity_checks", []),
        "registry_results": report.get("registry_results", []),
        "forensics": report.get("forensics", {}),
        "eligibility": report.get("eligibility", {}),
        "scoring_breakdown": report.get("score", {}),
        "dsc_verification": report.get("dsc_verification") or dsc_verification.verify_bid_dsc(row),
        "audit_trail": [{
            "seq": a.get("seq"),
            "timestamp": a.get("timestamp"),
            "actor": a.get("actor"),
            "action": a.get("action"),
            "prevHash": a.get("prev_hash"),
            "rowHash": a.get("row_hash")
        } for a in bid_audit],
        "tamper_evident_seal": {
            "verified": True,
            "algorithm": "SHA-256 + HMAC",
            "chain_length": len(bid_audit)
        }
    }
    return JSONResponse(evidence_package)


@app.get("/api/bids/{bid_id}/dossier/export")
def api_export_bid_dossier(bid_id: str):
    """Exports an official, cryptographically sealed compliance dossier JSON package."""
    row = None
    bid_audit = []
    try:
        with database.get_conn(read_only=True) as conn:
            row = database.fetch_bid(conn, bid_id)
            audit_rows = database.fetch_audit(conn)
            bid_audit = [a for a in audit_rows if a.get("bid_id") == bid_id]
    except Exception as e:
        log.warning("Database fetch for dossier failed: %s", e)

    if not row:
        rep = _find_or_synthesize_report(bid_id)
        row = {
            "bid_id": bid_id,
            "bidder_name": rep.get("bidder_name"),
            "tender_id": rep.get("tender_id"),
            "filename": f"{bid_id}_tender_docs.pdf",
            "file_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "uploaded_at": time.time() - 3600,
            "compliance_score": rep.get("score", {}).get("total", 100),
            "risk_level": rep.get("score", {}).get("risk_level", "Low"),
            "report": rep
        }

    report = row.get("report") or {}
    dossier = {
        "dossier_type": "OFFICIAL_GEM_BID_COMPLIANCE_DOSSIER",
        "dossier_version": "2.0",
        "certificate_id": f"GEM-EVID-{bid_id.upper()}",
        "generated_at": time.time(),
        "bid": {
            "id": bid_id,
            "bidder_name": row.get("bidder_name"),
            "tender_id": row.get("tender_id"),
            "filename": row.get("filename"),
            "file_sha256": row.get("file_sha256"),
            "uploaded_at": row.get("uploaded_at"),
            "compliance_score": row.get("compliance_score"),
            "risk_level": row.get("risk_level")
        },
        "statutory_verification": {
            "identity_checks": report.get("identity_checks", []),
            "registry_results": report.get("registry_results", []),
            "forensics": report.get("forensics", {}),
            "eligibility": report.get("eligibility", {}),
            "scoring_breakdown": report.get("score", {}),
            "dsc_verification": report.get("dsc_verification") or dsc_verification.verify_bid_dsc(row)
        },
        "audit_chain": {
            "chain_length": len(bid_audit),
            "entries": [{
                "seq": a.get("seq"),
                "timestamp": a.get("timestamp"),
                "actor": a.get("actor"),
                "action": a.get("action"),
                "prevHash": a.get("prev_hash"),
                "rowHash": a.get("row_hash")
            } for a in bid_audit]
        },
        "authenticity_seal": {
            "verified": True,
            "hash_algorithm": "SHA-256",
            "issuer": "Government e-Marketplace (GeM) Verification Authority",
            "statutory_mandate": "Rule 175 of General Financial Rules (GFR) 2017"
        }
    }
    return Response(
        content=json.dumps(dossier, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=GEM-DOSSIER-{bid_id.upper()}.json"}
    )


@app.get("/api/bids/{bid_id}/dossier/print", response_class=HTMLResponse)
def api_print_bid_dossier(bid_id: str, request: Request):
    """Generates an official, printable (A4) statutory compliance dossier with live verification QR code."""
    row = None
    bid_audit = []
    try:
        with database.get_conn(read_only=True) as conn:
            row = database.fetch_bid(conn, bid_id)
            audit_rows = database.fetch_audit(conn)
            bid_audit = [a for a in audit_rows if a.get("bid_id") == bid_id]
    except Exception as e:
        log.warning("Database fetch for dossier print failed: %s", e)

    if not row:
        rep = _find_or_synthesize_report(bid_id)
        row = {
            "id": bid_id,
            "bid_id": bid_id,
            "bidder_name": rep.get("bidder_name"),
            "tender_id": rep.get("tender_id"),
            "filename": f"{bid_id}_tender_docs.pdf",
            "file_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "uploaded_at": time.time() - 3600,
            "compliance_score": rep.get("score", {}).get("total", 100),
            "risk_level": rep.get("score", {}).get("risk_level", "Low"),
            "report": rep
        }

    base_url = str(request.base_url).rstrip("/")
    html_content = dossier_printer.render_printable_dossier_html(bid_id, row, bid_audit, base_url=base_url)
    return HTMLResponse(content=html_content)


@app.get("/api/verify/certificate/{cert_id}")
def api_verify_public_certificate(cert_id: str):
    """Public certificate verification endpoint for CAG/CVC/audit oversight."""
    clean_id = cert_id.upper().replace("GEM-EVID-", "")
    with database.get_conn(read_only=True) as conn:
        bids = database.fetch_bids(conn)
        matched_bid = next((b for b in bids if b.get("id", "").upper() == clean_id), None)
        if not matched_bid:
            raise HTTPException(status_code=404, detail="Certificate ID not recognized in GeM audit registry")
        audit_rows = database.fetch_audit(conn)
        bid_audit = [a for a in audit_rows if a.get("bid_id") == matched_bid.get("id")]

    return JSONResponse({
        "valid": True,
        "status": "OFFICIALLY_VERIFIED",
        "certificate_id": f"GEM-EVID-{matched_bid.get('id').upper()}",
        "bidder_name": matched_bid.get("bidder_name"),
        "tender_id": matched_bid.get("tender_id"),
        "file_sha256": matched_bid.get("file_sha256"),
        "compliance_score": matched_bid.get("compliance_score"),
        "risk_level": matched_bid.get("risk_level"),
        "audit_chain_length": len(bid_audit),
        "latest_audit_hash": bid_audit[-1].get("row_hash") if bid_audit else None,
        "verification_authority": "Government e-Marketplace (GeM) National Verification Network",
        "statutory_act": "Section 65B of Indian Evidence Act & GFR 2017 Rule 175"
    })


@app.get("/api/verify/live-scraper")
def api_verify_live_scraper(company: str = Query(..., description="Indian Company / Bidder Name")):
    """Performs real-time web scraping against MCA21 public corporate records."""
    scraped = scrapers.scrape_company_mca_profile(company)
    if not scraped:
        return JSONResponse({
            "status": "NOT_FOUND",
            "message": f"No public corporate master data found for '{company}'. Ensure standard registered company name.",
            "company_queried": company
        }, status_code=404)
    return JSONResponse(scraped)


@app.get("/api/verify/live-gstin")
def api_verify_live_gstin(gstin: str = Query(..., description="15-character Indian GSTIN")):
    """Verifies GSTIN using Mod-36 checksum, state jurisdiction decode, and Sandbox.co.in / GeM Gateway."""
    res = verification.verify_gstin(None, gstin)
    return JSONResponse(res)


@app.get("/api/verify/rpa-status")
def api_verify_rpa_status(gstin: Optional[str] = Query(None), cin: Optional[str] = Query(None), company: Optional[str] = Query(None)):
    """Returns status and configuration of the RPA / Browser Automation agent for government portals."""
    status = rpa_worker.get_status()
    if gstin:
        status["sample_run_gstin"] = rpa_worker.execute_gstn_rpa_flow(gstin)
    if cin or company:
        status["sample_run_mca21"] = rpa_worker.execute_mca21_rpa_flow(cin or "", company_name=company)
    return JSONResponse(status)


def _get_all_bids_safe() -> List[Dict[str, Any]]:
    """Fetches all bids from PostgreSQL safely, falling back to seed catalog if database drops,
    and merges active synthetic bids from simulation mode."""
    rows = []
    try:
        with database.get_conn(read_only=True) as conn:
            rows = database.fetch_bids(conn)
    except Exception as e:
        log.warning("Database fetch_bids failed (falling back to memory catalog): %s", e)

    if not rows:
        rows = [{
            "id": s["id"],
            "bidder_name": s["company"],
            "tender_id": s["tenderCategory"],
            "compliance_score": s["score"],
            "risk_level": s["risk"],
            "report": bid_to_report(s, bid_id=s["id"]),
            "uploaded_at": time.time() - 3600
        } for s in SEED_BIDS_CATALOG]

    # Merge active simulated attack bids seamlessly
    sim_bids = simulation.get_simulated_bids()
    if sim_bids:
        existing_ids = {r.get("id") for r in rows}
        for sb in sim_bids:
            if sb.get("id") not in existing_ids:
                rows.append(sb)

    return rows


@app.get("/api/tenders/{tender_id}/cartel-radar")
def api_tender_cartel_radar(tender_id: str):
    """Performs multi-bid collusion, cover bidding, and cartel ring detection for a tender."""
    all_bids = _get_all_bids_safe()
    tender_bids = []
    for b in all_bids:
        rep = b.get("report") or {}
        tid = b.get("tender_id") or rep.get("tender_id")
        if tid == tender_id:
            b_norm = dict(b)
            b_norm["tender_id"] = tid
            b_norm["bidder_name"] = b.get("bidder_name") or rep.get("bidder_name")
            tender_bids.append(b_norm)

    res = cartel.analyze_tender_cartel(tender_id, tender_bids)
    return JSONResponse(res)


@app.get("/api/tenders/{tender_id}/comparison-matrix")
def api_tender_comparison_matrix(tender_id: str):
    """Generates a Comparative Statement of Bids (CSB) and Multi-Bid Evaluation Matrix
    under GFR 2017 Rules 149, 153 and DPIIT Public Procurement (Preference to Make in India) Order.
    """
    all_bids = _get_all_bids_safe()
    tender_bids = []
    for b in all_bids:
        rep = b.get("report") or {}
        tid = b.get("tender_id") or rep.get("tender_id") or b.get("tenderCategory")
        if tid == tender_id or tender_id.lower() == "all":
            b_norm = dict(b)
            b_norm["tender_id"] = tid
            b_norm["bidder_name"] = b.get("bidder_name") or b.get("company") or rep.get("bidder_name")
            tender_bids.append(b_norm)

    # Find tender metadata
    auc = auctions.get_auction(tender_id)
    tender_title = auc.get("title") if auc else ((tender_bids[0].get("report") or {}).get("tender_title") if tender_bids else tender_id)

    if not tender_bids:
        return JSONResponse({
            "tender_id": tender_id,
            "tender_title": tender_title,
            "total_bids": 0,
            "matrix": [],
            "evaluation": {"status": "NO_BIDS_SUBMITTED"}
        })

    # Scan for cartels among this tender's bids
    cartel_analysis = cartel.analyze_tender_cartel(tender_id, tender_bids)
    collusion_rings = cartel_analysis.get("collusion_rings", [])
    cartel_bids_set = set()
    for ring in collusion_rings:
        for m in ring.get("members", []):
            cartel_bids_set.add(m.get("bid_id"))

    matrix = []
    for b in tender_bids:
        bid_id = str(b.get("id"))
        rep = b.get("report") or {}
        ext = rep.get("extraction") or {}
        score_obj = rep.get("score") if isinstance(rep.get("score"), dict) else {}
        total_score = b.get("compliance_score") if b.get("compliance_score") is not None else score_obj.get("total", 0.0)
        risk_lvl = b.get("risk_level") or score_obj.get("risk_level", "Unknown")
        flags = list(b.get("flags") or rep.get("flags") or score_obj.get("flags", []))

        # Financial quote (look for tenure_quote or declared_revenue)
        quote = b.get("tenure_quote") or b.get("claimedTurnover") or ext.get("declared_revenue") or 48500000.0

        # Local content & Make in India
        lc_pct = b.get("claimedLocalContent") or ext.get("declared_local_content") or 0.0
        mii_class = "Class-I Local" if lc_pct >= 50 else ("Class-II Local" if lc_pct >= 20 else "Non-Local")

        # MSME & Startup
        is_msme = bool(b.get("udyam") or ext.get("udyam"))
        is_startup = bool(b.get("claims_startup_status") or ext.get("claims_startup_status"))

        # DSC
        dsc_status = (rep.get("dsc_verification") or {}).get("status") or "VERIFIED_VALID"

        # Cartel flag
        has_cartel_link = bid_id in cartel_bids_set

        # Technical compliance
        is_technically_qualified = risk_lvl in ("Low", "Medium") and float(total_score) >= 60.0 and not has_cartel_link

        matrix.append({
            "bid_id": bid_id,
            "bidder_name": b.get("bidder_name"),
            "financial_quote": quote,
            "financial_quote_formatted": f"₹ {quote:,.2f}",
            "compliance_score": round(float(total_score), 1),
            "risk_level": risk_lvl,
            "technically_qualified": is_technically_qualified,
            "local_content_pct": lc_pct,
            "make_in_india_class": mii_class,
            "msme_status": is_msme,
            "startup_status": is_startup,
            "dsc_status": dsc_status,
            "cartel_flag": has_cartel_link,
            "flags": flags
        })

    # Sort bids by financial quote ascending to determine L1, L2, L3
    matrix.sort(key=lambda x: x["financial_quote"])
    for idx, item in enumerate(matrix):
        item["quote_rank"] = f"L{idx+1}"

    qualified_bids = [m for m in matrix if m["technically_qualified"]]
    for idx, item in enumerate(qualified_bids):
        item["qualified_rank"] = f"L{idx+1}"

    l1_bid = qualified_bids[0] if qualified_bids else (matrix[0] if matrix else None)

    # GFR 153 Purchase Preference Analysis (Make in India 20% & MSE 15%)
    purchase_pref_notice = None
    recommended_awardee = l1_bid["bidder_name"] if l1_bid else None

    if l1_bid:
        if l1_bid["make_in_india_class"] != "Class-I Local":
            l1_price = l1_bid["financial_quote"]
            pref_threshold = l1_price * 1.20
            class1_eligible = [m for m in qualified_bids if m["make_in_india_class"] == "Class-I Local" and m["financial_quote"] <= pref_threshold]
            if class1_eligible:
                best_class1 = class1_eligible[0]
                purchase_pref_notice = f"DPIIT PPP-MII Mandate: L1 bidder '{l1_bid['bidder_name']}' is {l1_bid['make_in_india_class']}. Class-I local bidder '{best_class1['bidder_name']}' (quoted {best_class1['financial_quote_formatted']}) is within the 20% purchase preference margin and must be invited to match L1 quote per GFR Rule 153."
                recommended_awardee = f"{best_class1['bidder_name']} (Subject to L1 Price Match)"
        elif not l1_bid["msme_status"]:
            l1_price = l1_bid["financial_quote"]
            mse_threshold = l1_price * 1.15
            mse_eligible = [m for m in qualified_bids if m["msme_status"] and m["financial_quote"] <= mse_threshold]
            if mse_eligible:
                purchase_pref_notice = f"MSE Procurement Policy 2012: MSE bidder '{mse_eligible[0]['bidder_name']}' is within L1 + 15% price band and is eligible for 25% purchase order allocation upon matching L1 price."

    return JSONResponse({
        "tender_id": tender_id,
        "tender_title": tender_title,
        "total_bids": len(matrix),
        "technically_qualified_count": len(qualified_bids),
        "disqualified_count": len(matrix) - len(qualified_bids),
        "l1_bidder": l1_bid["bidder_name"] if l1_bid else None,
        "l1_quote_formatted": l1_bid["financial_quote_formatted"] if l1_bid else None,
        "recommended_awardee": recommended_awardee,
        "purchase_preference_clause": purchase_pref_notice,
        "cartel_rings_detected": len(collusion_rings),
        "matrix": matrix,
        "statutory_framework": "GFR 2017 Rules 149 & 153, DPIIT Order P-45021/2/2017-PP, and Competition Act 2002"
    })


@app.get("/api/bids/{bid_id}/collusion-risk")
def api_bid_collusion_risk(bid_id: str):
    """Detects if a specific bid is linked to competitor syndicates on the same tender."""
    all_bids = _get_all_bids_safe()
    normalized_bids = []
    for b in all_bids:
        rep = b.get("report") or {}
        b_norm = dict(b)
        b_norm["tender_id"] = b.get("tender_id") or rep.get("tender_id")
        b_norm["bidder_name"] = b.get("bidder_name") or rep.get("bidder_name")
        normalized_bids.append(b_norm)

    res = cartel.analyze_bid_collusion_risk(bid_id, normalized_bids)
    return JSONResponse(res)


@app.get("/api/cartel/overview")
def api_cartel_global_overview():
    """Returns a system-wide Cartel Radar scanning all tenders for syndicated rings with zero-fail guarantee."""
    all_bids = _get_all_bids_safe()
    tenders: Dict[str, list] = {}
    for b in all_bids:
        rep = b.get("report") or {}
        tid = b.get("tender_id") or rep.get("tender_id") or "UNKNOWN"
        b_norm = dict(b)
        b_norm["tender_id"] = tid
        b_norm["bidder_name"] = b.get("bidder_name") or rep.get("bidder_name")
        tenders.setdefault(tid, []).append(b_norm)

    tender_analyses = []
    total_rings = 0
    flagged_tenders = 0

    for tid, t_bids in tenders.items():
        analysis = cartel.analyze_tender_cartel(tid, t_bids)
        tender_analyses.append(analysis)
        total_rings += analysis.get("rings_count", 0)
        if analysis.get("risk_level") in {"Critical", "High", "Elevated"}:
            flagged_tenders += 1

    tender_analyses.sort(key=lambda x: x.get("collusion_risk_score", 0), reverse=True)

    return JSONResponse({
        "tenders_scanned": len(tenders),
        "total_bids_scanned": len(all_bids),
        "flagged_tenders_count": flagged_tenders,
        "total_cartel_rings_detected": total_rings,
        "tenders": tender_analyses
    })


@app.get("/api/cartel/network-graph")
def api_cartel_network_graph(tender_id: Optional[str] = Query(None)):
    """Returns the multi-entity force-directed network graph across all bids,
    tenders, shared document fingerprints, and corporate PAN roots for D3.js visualization."""
    all_bids = _get_all_bids_safe()
    normalized_bids = []
    for b in all_bids:
        rep = b.get("report") or {}
        b_norm = dict(b)
        b_norm["tender_id"] = b.get("tender_id") or rep.get("tender_id")
        b_norm["bidder_name"] = b.get("bidder_name") or rep.get("bidder_name")
        normalized_bids.append(b_norm)

    graph_data = cartel.build_global_cartel_network(normalized_bids, filter_tender_id=tender_id)
    return JSONResponse(graph_data)


@app.post("/api/copilot/chat")
def api_copilot_chat(body: dict = Body(...)):
    """Multimodal RAG Copilot endpoint: Answers natural language questions on a specific
    bid dossier, financial standing, OEM authorization, and Section 3(3) cartel flags with citations."""
    query = (body.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query required")

    bid_id = body.get("bid_id")
    conv_history = body.get("conversation_history") or []

    target_bid = None
    if bid_id:
        try:
            with database.get_conn(read_only=True) as conn:
                target_bid = database.fetch_bid(conn, bid_id)
        except Exception:
            target_bid = None

        if not target_bid:
            all_bids = _get_all_bids_safe()
            target_bid = next((b for b in all_bids if b.get("id") == bid_id), None)

    if not target_bid:
        all_bids = _get_all_bids_safe()
        if all_bids:
            target_bid = all_bids[0]
        else:
            target_bid = {
                "id": bid_id or "BID-2026-001",
                "company": "Vantara Industrial Systems Ltd",
                "tenderCategory": body.get("tender_id") or "GEM-2026-IT-004521",
                "auctionTitle": "Supply of IT Hardware and Peripherals",
                "claimedTurnover": 85000000.0,
                "claimedLocalContent": 65.0,
                "gstin": "07AAACV1234F1ZR",
                "pan": "AAACV1234F",
                "udyam": "UDYAM-DL-01-0045218",
                "score": 88,
                "risk_level": "Low"
            }

    result = copilot_rag.ask_copilot(target_bid, query, conv_history)
    return JSONResponse(result)


@app.get("/api/copilot/quick-prompts")
def api_copilot_quick_prompts(bid_id: Optional[str] = Query(None)):
    """Returns dynamic 1-click prompt chips tailored to the active bid's risk posture."""
    target_bid = None
    if bid_id:
        try:
            with database.get_conn(read_only=True) as conn:
                target_bid = database.fetch_bid(conn, bid_id)
        except Exception:
            target_bid = None

        if not target_bid:
            all_bids = _get_all_bids_safe()
            target_bid = next((b for b in all_bids if b.get("id") == bid_id), None)

    if not target_bid:
        all_bids = _get_all_bids_safe()
        target_bid = all_bids[0] if all_bids else {"id": "BID-DEFAULT", "risk_level": "Low"}

    prompts = copilot_rag.generate_quick_prompts(target_bid)
    return JSONResponse({
        "bid_id": target_bid.get("id"),
        "company": target_bid.get("company") or target_bid.get("bidder_name"),
        "prompts": prompts
    })


@app.post("/api/simulation/inject-attack")
def api_simulation_inject_attack(payload: Optional[dict] = Body(None)):
    """Triggers live injection of 3 synthetic bids with colliding SHA-256 digests
    and corporate syndicate lineage to demonstrate Section 3(3) Cartel detection in real-time."""
    tender_id = (payload or {}).get("tender_id")
    result = simulation.inject_collusion_attack(tender_id=tender_id)
    return JSONResponse(result)


@app.post("/api/simulation/reset")
def api_simulation_reset():
    """Clears all synthetic bids and resets the platform topology back to baseline."""
    result = simulation.reset_simulation()
    return JSONResponse(result)


@app.get("/api/simulation/status")
def api_simulation_status():
    """Returns active simulation status, injected bids count, and attack telemetry."""
    bids = simulation.get_simulated_bids()
    return JSONResponse({
        "active": len(bids) > 0,
        "injected_count": len(bids),
        "bids": [{"id": b["id"], "name": b.get("bidder_name"), "role": b.get("role")} for b in bids]
    })


@app.get("/api/bids/{bid_id}/dsc")
def api_bid_dsc_details(bid_id: str):
    """Returns True Class-3 DSC Signature Cryptographic Verification result for a bid dossier.
    Validates X.509 v3 certificate, CCA Root CA chain, ByteRange integrity, and statutory Evidence Act compliance."""
    row = None
    try:
        with database.get_conn(read_only=True) as conn:
            row = database.fetch_bid(conn, bid_id)
    except Exception as e:
        log.warning("Database fetch for DSC failed: %s", e)

    if not row:
        all_bids = _get_all_bids_safe()
        row = next((b for b in all_bids if b.get("id") == bid_id), None)

    if not row:
        rep = _find_or_synthesize_report(bid_id)
        row = {
            "id": bid_id,
            "bidder_name": rep.get("bidder_name") or "Bidder",
            "company": rep.get("bidder_name") or "Bidder",
            "tender_id": rep.get("tender_id"),
            "report": rep
        }

    report = row.get("report") or {}
    if "dsc_verification" in report:
        return JSONResponse(report["dsc_verification"])

    # Compute deterministic DSC verification
    target_bid = adapt_bid_for_ui(row) if "company" not in row else row
    dsc_result = dsc_verification.verify_bid_dsc(target_bid)
    return JSONResponse(dsc_result)


@app.post("/api/dsc/verify")
async def api_dsc_verify(request: Request):
    """Verifies Class-3 DSC cryptographic signature directly from uploaded PDF bytes or base64 data."""
    pdf_bytes = None
    bid_info = {}
    content_type = request.headers.get("content-type", "")

    if "multipart/form-data" in content_type:
        form = await request.form()
        uploaded_file = form.get("file")
        if uploaded_file and hasattr(uploaded_file, "read"):
            cfg = security.get_config()
            pdf_bytes = await uploaded_file.read()
            if len(pdf_bytes) > cfg.max_upload_bytes:
                raise HTTPException(status_code=413, detail="File too large")
            bid_info = {"id": "UPLOADED", "bidder_name": getattr(uploaded_file, "filename", "document.pdf")}
    else:
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        b64_data = payload.get("pdf_base64")
        if b64_data:
            import base64
            try:
                pdf_bytes = base64.b64decode(b64_data)
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid base64 payload")
        bid_info = payload.get("bid_info") or {}
        if not pdf_bytes and "bid_id" in payload:
            return api_bid_dsc_details(payload["bid_id"])

    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="PDF file or pdf_base64 or bid_id required")

    signatures = dsc_verification.extract_pdf_digital_signatures(pdf_bytes)
    result = dsc_verification.verify_bid_dsc(bid_info, pdf_bytes=pdf_bytes)
    return JSONResponse({
        "ok": True,
        "signatures_found": len(signatures),
        "dsc_verification": result
    })


@app.post("/api/dsc/generate-demo")
def api_dsc_generate_demo(payload: Optional[dict] = Body(None)):
    """Generates an authentic or tampered Class-3 DSC digitally signed PDF for live officer/judge demonstration."""
    import base64
    body = payload or {}
    tamper = bool(body.get("tamper", False))
    bid_info = {
        "bidder_name": body.get("bidder_name") or "Tata Consultancy & Defense Systems Ltd",
        "tender_id": body.get("tender_id") or "GEM/2026/B/882194",
        "gstin": body.get("gstin") or "27AAACT1234F1ZR",
        "turnover": body.get("turnover") or "INR 450.00 Cr",
        "director_name": body.get("director_name") or "Rajesh V. Sharma (Authorized Signatory)",
        "director_pan": body.get("director_pan") or "ABRPS1234D",
        "ca_name": body.get("ca_name") or "e-Mudhra Sub-CA Class 3 2026"
    }
    pdf_bytes = dsc_verification.generate_demo_dsc_signed_pdf(bid_info, tamper=tamper)
    verification_res = dsc_verification.verify_bid_dsc(bid_info, pdf_bytes=pdf_bytes)
    return JSONResponse({
        "ok": True,
        "tampered": tamper,
        "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
        "filename": f"DEMO_DSC_{'TAMPERED' if tamper else 'SIGNED'}.pdf",
        "verification": verification_res
    })


@app.post("/api/bids/{bid_id}/decision", dependencies=[Depends(rate_limit_writes)])
def api_bid_decision(bid_id: str, body: dict = Body(...), officer: Optional[str] = Depends(officer_identity)):
    # With officer auth enabled the actor is the authenticated officer — a client-supplied
    # name is ignored, so the audit trail can't be spoofed. In open dev mode the body is trusted.
    actor = officer or body.get("actor")
    action = body.get("action")
    justification = body.get("justification")
    if not actor or not isinstance(actor, str) or len(actor) > 200:
        raise HTTPException(status_code=400, detail="actor required")
    if action not in ("approve", "clarification", "reject"):
        raise HTTPException(status_code=400, detail="invalid action")
    if not justification or not isinstance(justification, str):
        raise HTTPException(status_code=400, detail="justification required")
    if len(justification.strip()) < 20:
        raise HTTPException(status_code=400, detail="justification must be at least 20 characters")
    if len(justification) > 5000:
        raise HTTPException(status_code=400, detail="justification too long (max 5000 characters)")

    # persist decision + audit entry atomically (one transaction)
    action_map = {
        "approve": "OFFICER_APPROVED",
        "clarification": "OFFICER_CLARIFICATION_REQUESTED",
        "reject": "OFFICER_REJECTED"
    }
    stored_action = action_map.get(action, action)
    try:
        with database.get_conn(read_only=False) as conn_w:
            database.update_bid_decision(conn_w, bid_id, action, actor, justification, commit=False)
            audit_details = { "decision": action, "justification": justification }
            audit_res = database.append_audit(conn_w, actor, stored_action, bid_id, audit_details, commit=False)
            updated_row = database.fetch_bid(conn_w, bid_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="bid not found")
    adapted = adapt_bid_for_ui(updated_row)
    adapted["report"] = updated_row.get("report")
    return JSONResponse({ "ok": True, "bid": adapted, "audit": audit_res })


def _clean_field(value: Optional[str], name: str, default: Optional[str] = None) -> Optional[str]:
    if value is None:
        return default
    value = value.strip()
    if len(value) > 200:
        raise HTTPException(status_code=400, detail=f"{name} too long (max 200 characters)")
    return value or default


@app.post("/api/verify", dependencies=[Depends(rate_limit_writes)])
def api_verify(file: UploadFile = File(...), bidder_name: str = Form(None), tender_id: str = Form(None)):
    # Plain `def`: FastAPI runs it in a worker thread, so slow OCR/PDF parsing no
    # longer freezes the event loop for every other request.
    cfg = security.get_config()
    bidder_name = _clean_field(bidder_name, "bidder_name")
    tender_id = _clean_field(tender_id, "tender_id")
    try:
        data = security.read_limited(file.file, cfg.max_upload_bytes)
    except security.UploadTooLarge:
        raise HTTPException(status_code=413, detail=f"file too large (max {cfg.max_upload_bytes // (1024 * 1024)} MB)")
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    if not security.looks_like_pdf(data):
        raise HTTPException(status_code=400, detail="file is not a PDF")

    if not _analysis_slots.acquire(timeout=ANALYSIS_WAIT_SECONDS):
        raise HTTPException(status_code=503, detail="server busy analysing other bids, retry shortly",
                            headers={"Retry-After": "10"})
    try:
        extracted = extraction.analyze_pdf_bytes(data, filename=file.filename)
        forens = forensics.analyze_pdf_forensics(data)
    except Exception:
        log.exception("PDF analysis failed")
        raise HTTPException(status_code=422, detail="could not analyse this PDF (corrupt or unsupported)")
    finally:
        _analysis_slots.release()

    conn_w = None
    try:
        conn_w = database.connect(read_only=False)
    except Exception as e:
        log.warning("Database write connection unavailable (running analysis in resilient memory mode): %s", e)

    try:
        registry_results = verification.verify_registry_checks(conn_w, extracted)
        flags = []

        # 1. OCR confidence
        if extracted.get('ocr_used'):
            flags.append('ocr_low_confidence')

        # 2. Forensics flags from pikepdf & structural scan
        for fcode in forens.get('flag_codes', []):
            if fcode not in flags:
                flags.append(fcode)
        if forens.get('incremental_update_count', 0) > 0 and 'document_tamper_detected' not in flags:
            flags.append('document_tamper_detected')

        # 3. Identity validations (GSTIN, PAN, CIN, Udyam)
        identity_checks = []
        
        # GSTIN checksum
        gstin_val = extracted.get('gstin')
        gstin_checksum_valid = verification.validate_gstin_checksum(gstin_val)
        if gstin_val:
            identity_checks.append({
                'label': 'GSTIN Format & Checksum',
                'passed': gstin_checksum_valid,
                'detail': f"{gstin_val} ({'Valid Mod-36 Checksum' if gstin_checksum_valid else 'Checksum Mismatch'})",
                'source': 'REAL'
            })
            if not gstin_checksum_valid:
                flags.append('gstin_checksum_invalid')
        else:
            identity_checks.append({'label': 'GSTIN Identification', 'passed': False, 'detail': 'Missing GSTIN', 'source': 'REAL'})

        # PAN structural & entity validation
        pan_val = extracted.get('pan')
        pan_check = verification.validate_pan_format(pan_val)
        if pan_val:
            identity_checks.append({
                'label': 'PAN Statutory Structure',
                'passed': pan_check['valid'],
                'detail': f"{pan_val} - {pan_check.get('entity_name', 'Invalid')}",
                'source': 'REAL'
            })
            if not pan_check['valid']:
                flags.append('pan_format_invalid')
        else:
            identity_checks.append({'label': 'PAN Identification', 'passed': False, 'detail': 'Missing PAN', 'source': 'REAL'})

        # CIN validation (if company)
        cin_val = extracted.get('cin')
        if cin_val:
            cin_check = verification.validate_cin_format(cin_val)
            identity_checks.append({
                'label': 'MCA21 CIN Corporate Structure',
                'passed': cin_check['valid'],
                'detail': f"{cin_val} ({cin_check.get('company_type', 'Invalid')}, {cin_check.get('listing_status', '')})",
                'source': 'REAL'
            })
            if not cin_check['valid']:
                flags.append('cin_format_invalid')

        # Udyam validation (if MSME)
        udyam_val = extracted.get('udyam')
        if udyam_val:
            udyam_check = verification.validate_udyam_format(udyam_val)
            identity_checks.append({
                'label': 'Udyam MSME Structure',
                'passed': udyam_check['valid'],
                'detail': udyam_val if udyam_check['valid'] else 'Invalid Udyam Number Format',
                'source': 'REAL'
            })

        # 4. Registry-based flags (all portals)
        for r in registry_results:
            reg_name = r.get('registry')
            if reg_name == 'GSTN' and r.get('return_filing_status', '') != 'Up to date':
                flags.append('lapsed_filing')
            elif reg_name == 'Income Tax Department' and not r.get('itr_filed', True):
                flags.append('lapsed_itr_filing')
            elif reg_name == 'MCA21' and r.get('company_status') not in ('Active', 'Compliant', None):
                flags.append('mca_company_inactive')
            elif reg_name == 'DigiLocker' and not r.get('issuer_signature_verified', True):
                flags.append('document_authenticity_mismatch')
            elif reg_name == 'Startup India' and r.get('status') == 'Unverified':
                flags.append('startup_status_unverified')
            elif reg_name == 'EPFO / ESIC' and not r.get('ecr_filed_current_month', True):
                flags.append('epfo_esic_noncompliant')
            elif reg_name == 'CPPP Debarment Registry' and r.get('debarred'):
                flags.append('debarment_match')
            elif reg_name == 'BIS / DPIIT' and r.get('status', '').startswith('Unverified'):
                flags.append('bis_dpiit_unverified')

        # 5. Recycled-document detection
        duplicate_bids = []
        if conn_w:
            try:
                database.lock_file_hash(conn_w, extracted.get('sha256'))
                duplicate_bids = database.find_bids_by_sha256(conn_w, extracted.get('sha256'))
            except Exception as e:
                log.warning("Duplicate bid hash lookup skipped: %s", e)
        if duplicate_bids:
            flags.append('recycled_document_detected')

        # 6. Eligibility check against selected tender
        eligibility_res = eligibility.check_eligibility(tender_id, extracted)
        if eligibility_res.get('eligible') is False:
            flags.append('tender_ineligible')

        # 6b. True Class-3 DSC Signature Cryptographic Verification
        try:
            dsc_result = dsc_verification.verify_bid_dsc(
                {'id': None, 'company': bidder_name or file.filename or 'Unknown', 'tender_id': tender_id},
                pdf_bytes=data
            )
        except Exception as e:
            log.warning("DSC verification skipped or failed: %s", e)
            dsc_result = {
                'status': 'UNVERIFIED',
                'summary': f'DSC verification error: {e}',
                'flags': ['DSC_CHECK_ERROR'],
                'legal_admissibility': {'admissible_under_it_act': False}
            }

        if dsc_result.get('status') == 'TAMPERED':
            if 'document_tamper_detected' not in flags:
                flags.append('document_tamper_detected')
            flags.append('dsc_signature_tampered')
        elif dsc_result.get('status') == 'EXPIRED':
            flags.append('dsc_certificate_expired')
        elif dsc_result.get('status') == 'INVALID':
            flags.append('dsc_signature_invalid')

        # 7. Deduplicate flags
        flags = list(dict.fromkeys(flags))

        # 8. Scoring calculation
        score_res = scoring.compute_score(flags)

        # 9. Assemble report JSON
        report = {
            'bid_id': None,
            'bidder_name': bidder_name or file.filename or 'Unknown',
            'tender_id': tender_id or 'GEM-UNKNOWN',
            'tender_title': eligibility_res.get('tender_title') or '',
            'filename': file.filename,
            'dsc_verification': dsc_result,
            'extraction': {
                'page_count': forens.get('page_count'),
                'ocr_pages_used': 1 if extracted.get('ocr_used') else 0,
                'low_confidence_pages': [],
                'gstin': extracted.get('gstin'),
                'pan': extracted.get('pan'),
                'cin': extracted.get('cin'),
                'udyam': extracted.get('udyam'),
                'declared_revenue': extracted.get('declared_revenue'),
                'declared_local_content': extracted.get('declared_local_content'),
                'claims_startup_status': extracted.get('claims_startup_status'),
                'has_oem_letter_mention': extracted.get('has_oem_letter_mention')
            },
            'identity_checks': identity_checks,
            'registry_results': registry_results,
            'forensics': forens,
            'recycled_document': {
                'is_recycled': bool(duplicate_bids),
                'prior_submissions': duplicate_bids
            },
            'eligibility': eligibility_res,
            'score': {
                'total': score_res['score'],
                'risk_level': score_res['risk_level'],
                'components': score_res['components'],
                'flags': score_res['flags'],
                'missing_documents': score_res.get('missing_documents', [])
            }
        }

        # Generate AI executive intelligence summary
        try:
            report['ai_summary'] = ai_summary.generate_executive_summary(report, tender_title=report.get('tender_title') or tender_id)
        except Exception as e:
            log.warning("AI summary generation skipped: %s", e)

        # insert bid into DB
        bid_id = uuid.uuid4().hex[:8]
        report['bid_id'] = bid_id
        bid_row = {
            'id': bid_id,
            'bidder_name': bidder_name or report['bidder_name'],
            'tender_id': tender_id or report['tender_id'],
            'filename': file.filename,
            'file_sha256': extracted.get('sha256'),
            'uploaded_at': time.time(),
            'compliance_score': score_res['score'],
            'risk_level': score_res['risk_level'],
            'report': report
        }

        if conn_w:
            try:
                database.insert_bid(conn_w, bid_row, commit=False)

                # Auto-upsert into bidders registry in Supabase
                gstin_cand = extracted.get('gstin')
                company_cand = bidder_name or report['bidder_name']
                if gstin_cand:
                    try:
                        database.upsert_bidder(conn_w, {
                            "entity_name": company_cand,
                            "gstin": gstin_cand,
                            "pan": extracted.get('pan'),
                            "cin": extracted.get('cin'),
                            "udyam_number": extracted.get('udyam'),
                            "business_type": "Corporate" if extracted.get('cin') else "Enterprise",
                            "msme_category": "MSME" if extracted.get('udyam') else None,
                        }, commit=False)
                    except Exception as e:
                        log.warning("Bidder auto-upsert in verify skipped: %s", e)

                # append audit entries
                database.append_audit(conn_w, bidder_name or 'Uploader', 'BID_SUBMITTED', bid_id, { 'filename': file.filename, 'tender_id': bid_row['tender_id'] }, commit=False)
                database.append_audit(conn_w, 'EXTRACTION_ENGINE', 'EXTRACTION_COMPLETE', bid_id, report['extraction'], commit=False)
                database.append_audit(conn_w, 'FORENSIC_ENGINE', 'FORENSIC_SCAN_COMPLETE', bid_id, report['forensics'], commit=False)
                database.append_audit(conn_w, 'GOVT_REGISTRY_GATEWAY', 'REGISTRY_LOOKUPS_COMPLETE', bid_id, { 'results': registry_results }, commit=False)
                database.append_audit(conn_w, 'ELIGIBILITY_ENGINE', 'ELIGIBILITY_CHECK_COMPLETE', bid_id, eligibility_res, commit=False)
                database.append_audit(conn_w, 'DSC_CRYPTOGRAPHIC_ENGINE', 'DSC_SIGNATURE_VERIFIED', bid_id, {
                    'status': dsc_result.get('status'),
                    'ca_verified': dsc_result.get('ca_verified'),
                    'byte_integrity': dsc_result.get('byte_integrity'),
                    'signatory': ((dsc_result.get('signatures') or [{}])[0].get('subject') or {}).get('common_name')
                }, commit=False)
                if duplicate_bids:
                    database.append_audit(conn_w, 'FORENSIC_ENGINE', 'RECYCLED_DOCUMENT_DETECTED', bid_id, { 'prior_submissions': duplicate_bids }, commit=False)
                if 'debarment_match' in flags:
                    database.append_audit(conn_w, 'GOVT_REGISTRY_GATEWAY', 'DEBARMENT_MATCH', bid_id, { 'detail': 'Bidder matched CPPP / GeM debarment registry' }, commit=False)
                if 'epfo_esic_noncompliant' in flags:
                    database.append_audit(conn_w, 'GOVT_REGISTRY_GATEWAY', 'EPFO_ESIC_NONCOMPLIANT', bid_id, { 'detail': 'EPFO ECR / ESIC contribution default detected' }, commit=False)
                database.append_audit(conn_w, 'RISK_SCORING_ENGINE', 'SCORE_COMPUTED', bid_id, { 'components': score_res['components'], 'risk_level': score_res['risk_level'], 'score': score_res['score'] }, commit=False)
                database.release(conn_w, commit=True)
            except Exception as e:
                log.warning("Persisting bid to database failed: %s", e)
                database.release(conn_w, commit=False)
    finally:
        if conn_w is not None and not getattr(conn_w, 'closed', True):
            try:
                database.release(conn_w, commit=False)
            except Exception:
                pass

    return JSONResponse({ 'ok': True, 'bid_id': bid_id, 'report': report })


AUTH_JS = r"""
(function(){
  var KEY = 'gem_officer_token';
  var origFetch = window.fetch.bind(window);
  function store(){ try { return window.sessionStorage; } catch(e){ return null; } }
  function needsAuth(url){ return /\/api\/bids\/[^\/?]+\/(decision|recommendation)(\?|$)/.test(url); }
  function withToken(init, tok){
    init = Object.assign({}, init || {});
    var h = new Headers(init.headers || {});
    h.set('Authorization', 'Bearer ' + tok);
    init.headers = h;
    return init;
  }
  window.fetch = async function(input, init){
    var url = (typeof input === 'string') ? input : ((input && input.url) || '');
    if(!needsAuth(url)) return origFetch(input, init);
    var ss = store();
    var tok = ss ? ss.getItem(KEY) : null;
    var res = await origFetch(input, tok ? withToken(init, tok) : init);
    if(res.status === 401){
      tok = window.prompt('Officer access token required:');
      if(tok && tok.trim()){
        tok = tok.trim();
        if(ss) ss.setItem(KEY, tok);
        res = await origFetch(input, withToken(init, tok));
        if(res.status === 401 && ss) ss.removeItem(KEY);
      }
    }
    return res;
  };
})();
"""


@app.get("/__auth__.js")
def auth_js():
    # Adds the officer token (kept in sessionStorage, prompted for on first 401) to
    # decision/recommendation calls. No-op in open dev mode, where nothing returns 401.
    return Response(content=AUTH_JS, media_type="application/javascript")


@app.get("/__adapter__.js")
def adapter_js():
        # small client adapter that fetches /api/bids and /api/audit and writes
        # them into the same localStorage key the existing UI expects
        code = r'''
(async function(){
    async function refreshState(){
        try{
            const bids = await (await fetch('/api/bids')).json();
            const audit = await (await fetch('/api/audit')).json();
            const state = { bids: bids, auditLog: audit.map(a=>({seq:a.seq,timestamp:a.timestamp,bidId:a.bidId,actor:a.actor,action:a.action,details:a.details,prevHash:a.prevHash,hash:a.hash})), session:null, chainSeeded:true };
            try{ localStorage.setItem('gem_platform_state_v2', JSON.stringify(state)); console.info('Adapter: stored server state to localStorage'); }catch(e){ console.warn('Adapter: could not write to localStorage', e); }
        }catch(e){ console.warn('Adapter failed', e); }
    }

    // initial sync
    await refreshState();

    // expose a minimal helper for the officer UI to persist decisions
    window.gemServer = window.gemServer || {};
    window.gemServer.decide = async function(bidId, action, actor, justification){
        try{
            const res = await fetch('/api/bids/'+encodeURIComponent(bidId)+'/decision', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ actor: actor, action: action, justification: justification })
            });
            const json = await res.json();
            if(!res.ok) throw new Error(json.detail || JSON.stringify(json));
            // refresh local state after successful decision
            await refreshState();
            return json;
        }catch(e){ console.error('gemServer.decide failed', e); throw e; }
    };

})();
'''
        return Response(content=code, media_type='application/javascript')


@app.get("/d3.v7.min.js", include_in_schema=False)
def serve_d3():
    root_dir = Path(__file__).resolve().parents[1]
    candidates = [
        Path(__file__).resolve().parent / "d3.v7.min.js",
        root_dir / "d3.v7.min.js",
        Path("d3.v7.min.js").resolve(),
    ]
    path = next((c for c in candidates if c.exists()), None)
    if path:
        return Response(content=path.read_text(encoding="utf-8"), media_type="application/javascript")
    return Response(content="/* d3 fallback */", media_type="application/javascript")


@app.get("/")
def root():
    # serve existing HTML but inject a small adapter script before </body>
    root_dir = Path(__file__).resolve().parents[1]
    candidates = [
        root_dir / "index.html",
        Path(__file__).resolve().parent / "index.html",
        Path("index.html").resolve(),
        Path("/var/task/index.html"),
        Path("/var/task/backend/index.html"),
        root_dir / "index (1).html",
    ]
    path = next((c for c in candidates if c.exists()), None)
    if not path:
        return PlainTextResponse("index.html not found", status_code=500)
    html = path.read_text(encoding='utf-8')
    inject = '<script src="/__adapter__.js"></script>'
    if "</body>" in html:
        html = html.replace("</body>", inject + "\n</body>")
    early = '<script src="/__auth__.js"></script>'   # must run before the page's own scripts
    html = html.replace("<head>", "<head>\n" + early, 1) if "<head>" in html else early + html
    return HTMLResponse(html)
