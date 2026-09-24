import time
from typing import Any, Dict, List, Optional

TENURE_AUCTIONS: List[Dict[str, Any]] = [
    {
        "auction_id": "CPCL-2026-VALV-089",
        "title": "Procurement of High-Pressure Forged Steel Refinery Valves & Flanges — CPCL Manali Refinery",
        "department": "CPCL Manali Refinery",
        "category": "refinery-valves",
        "status": "ongoing",
        "tenure_months": 36,
        "tenure_label": "36 Months (3 Years)",
        "tenure_start_date": "01-May-2026",
        "tenure_end_date": "30-Apr-2029",
        "tenure_extension_terms": "Renewable up to 12 months based on annual SLA rating >= 90%",
        "estimated_value": 150000000,
        "estimated_value_formatted": "Rs 15.00 Cr",
        "bidding_start": "10-Apr-2026 09:00 IST",
        "bidding_deadline": "25-Apr-2026 17:00 IST",
        "bids_count": 3,
        "current_lowest_bid": 148000000,
        "current_lowest_formatted": "Rs 14.80 Cr",
        "min_turnover": 150000000,
        "min_local_content": 50,
        "requires_epfo": True,
        "requires_bis": True,
        "requires_startup_proof": False,
        "milestones": [
            {"period": "Q1 2026", "deliverable": "Initial batch forged valves delivery & metallurgical test certs"},
            {"period": "Year 1-2", "deliverable": "Scheduled refinery shutdown valve replacements & on-site pressure testing"},
            {"period": "Year 3", "deliverable": "Comprehensive AMC spares inventory handover & warranty closeout"}
        ],
        "scope_summary": "Supply, installation, hydrostatic pressure testing, and multi-year AMC spares for refinery grade gate, globe, and check valves."
    },
    {
        "auction_id": "GEM-2026-IT-004521",
        "title": "National Supply & Managed Maintenance of Enterprise IT Hardware & Networking",
        "department": "Ministry of Electronics & Information Technology",
        "category": "goods-electronics",
        "status": "ongoing",
        "tenure_months": 24,
        "tenure_label": "24 Months (2 Years)",
        "tenure_start_date": "15-Jun-2026",
        "tenure_end_date": "14-Jun-2028",
        "tenure_extension_terms": "Extendable by 6 months on mutual consent",
        "estimated_value": 50000000,
        "estimated_value_formatted": "Rs 5.00 Cr",
        "bidding_start": "01-Apr-2026 10:00 IST",
        "bidding_deadline": "10-May-2026 15:00 IST",
        "bids_count": 5,
        "current_lowest_bid": 48500000,
        "current_lowest_formatted": "Rs 4.85 Cr",
        "min_turnover": 5000000,
        "min_local_content": 30,
        "requires_epfo": False,
        "requires_bis": True,
        "requires_startup_proof": False,
        "milestones": [
            {"period": "Month 1-3", "deliverable": "Staged deployment of 1,200 desktop workstations & rack servers"},
            {"period": "Year 1", "deliverable": "Quarterly preventative maintenance & switch firmware updates"},
            {"period": "Year 2", "deliverable": "24-month SLA compliance audit & residual warranty transfer"}
        ],
        "scope_summary": "Provisioning of 1,200 desktop workstations, rack servers, managed L3 switches, and 24-month on-site warranty support."
    },
    {
        "auction_id": "CPCL-2026-TURN-003",
        "title": "Refinery Turnaround Piping & Structural Fabrication Services — CPCL Chennai Complex",
        "department": "CPCL Chennai Complex",
        "category": "turnaround",
        "status": "ongoing",
        "tenure_months": 12,
        "tenure_label": "12 Months (1 Year)",
        "tenure_start_date": "01-Jul-2026",
        "tenure_end_date": "30-Jun-2027",
        "tenure_extension_terms": "Fixed tenure (Shutdown turnaround window)",
        "estimated_value": 50000000,
        "estimated_value_formatted": "Rs 5.00 Cr",
        "bidding_start": "12-Apr-2026 10:00 IST",
        "bidding_deadline": "02-May-2026 18:00 IST",
        "bids_count": 2,
        "current_lowest_bid": 49200000,
        "current_lowest_formatted": "Rs 4.92 Cr",
        "min_turnover": 50000000,
        "min_local_content": 50,
        "requires_epfo": True,
        "requires_bis": False,
        "requires_startup_proof": False,
        "milestones": [
            {"period": "Month 1-2", "deliverable": "Mobilization of skilled welders, NDT level-II technicians & safety gears"},
            {"period": "Month 3-6", "deliverable": "Unit shutdown piping spool pre-fabrication and hydro-testing"},
            {"period": "Month 7-12", "deliverable": "Post-startup flange leak inspections & hydro-test sign-offs"}
        ],
        "scope_summary": "Execution of turnaround pipe spool fabrication, hydrotesting, bolt-tensioning, and NDT inspection across CDU/VDU units."
    },
    {
        "auction_id": "GEM-2026-MSME-011",
        "title": "MSME-Reserved: Modular Ergonomic Workstations & Office Fixtures",
        "department": "Department of Administrative Reforms (DARPG)",
        "category": "goods-general",
        "status": "ongoing",
        "tenure_months": 12,
        "tenure_label": "12 Months (1 Year)",
        "tenure_start_date": "01-Aug-2026",
        "tenure_end_date": "31-Jul-2027",
        "tenure_extension_terms": "Renewable for 1 additional year under identical pricing",
        "estimated_value": 8500000,
        "estimated_value_formatted": "Rs 85.00 Lakh",
        "bidding_start": "15-Apr-2026 10:00 IST",
        "bidding_deadline": "20-May-2026 12:00 IST",
        "bids_count": 6,
        "current_lowest_bid": 8150000,
        "current_lowest_formatted": "Rs 81.50 Lakh",
        "min_turnover": 0,
        "min_local_content": 25,
        "requires_epfo": False,
        "requires_bis": False,
        "requires_startup_proof": True,
        "milestones": [
            {"period": "Phase 1", "deliverable": "Ergonomic layout signoff and material delivery"},
            {"period": "Phase 2", "deliverable": "Modular installation and acoustic testing for 4 departmental zones"}
        ],
        "scope_summary": "Modular partitions, height-adjustable desks, and acoustic paneling across 4 departmental regional complexes."
    },
    {
        "auction_id": "CPCL-2026-ELEC-027",
        "title": "Supply & Installation of HT/LT Switchgear & Transformers — CPCL Nagapattinam Refinery",
        "department": "CPCL Nagapattinam Refinery",
        "category": "switchgear",
        "status": "upcoming",
        "tenure_months": 36,
        "tenure_label": "36 Months (3 Years)",
        "tenure_start_date": "01-Sep-2026",
        "tenure_end_date": "31-Aug-2029",
        "tenure_extension_terms": "Renewable for 1 additional year for routine substation AMC",
        "estimated_value": 80000000,
        "estimated_value_formatted": "Rs 8.00 Cr",
        "bidding_start": "15-May-2026 10:00 IST",
        "bidding_deadline": "15-Jun-2026 17:00 IST",
        "bids_count": 0,
        "current_lowest_bid": None,
        "current_lowest_formatted": "Bidding not opened",
        "min_turnover": 80000000,
        "min_local_content": 50,
        "requires_epfo": True,
        "requires_bis": True,
        "requires_startup_proof": False,
        "milestones": [
            {"period": "Year 1", "deliverable": "Type testing and delivery of 33kV/11kV gas-insulated switchgear units"},
            {"period": "Year 2", "deliverable": "Substation installation, relay coordination & energization"},
            {"period": "Year 3", "deliverable": "36-month preventive maintenance & thermal imaging inspections"}
        ],
        "scope_summary": "33kV/11kV gas-insulated switchgear units, 5 MVA power transformers, protection relays, and 3-year preventative maintenance."
    },
    {
        "auction_id": "GEM-2026-SOLAR-055",
        "title": "Grid-Interactive Rooftop Solar PV & BESS Microgrid 5-Year Comprehensive O&M",
        "department": "Ministry of New and Renewable Energy (MNRE)",
        "category": "solar-microgrid",
        "status": "upcoming",
        "tenure_months": 60,
        "tenure_label": "60 Months (5 Years)",
        "tenure_start_date": "01-Oct-2026",
        "tenure_end_date": "30-Sep-2031",
        "tenure_extension_terms": "Option to extend for 2 years upon 98% generation availability",
        "estimated_value": 225000000,
        "estimated_value_formatted": "Rs 22.50 Cr",
        "bidding_start": "01-Jun-2026 11:00 IST",
        "bidding_deadline": "30-Jun-2026 16:00 IST",
        "bids_count": 0,
        "current_lowest_bid": None,
        "current_lowest_formatted": "Bidding not opened",
        "min_turnover": 120000000,
        "min_local_content": 50,
        "requires_epfo": True,
        "requires_bis": True,
        "requires_startup_proof": False,
        "milestones": [
            {"period": "Month 1-6", "deliverable": "5 MW solar array erection and 2 MWh BESS commissioning"},
            {"period": "Year 2-4", "deliverable": "Continuous telemetry monitoring and monthly guaranteed CUF audits"},
            {"period": "Year 5", "deliverable": "Battery state-of-health re-certification and handover"}
        ],
        "scope_summary": "5 MW cumulative rooftop solar with 2 MWh Battery Energy Storage System (BESS), IoT telemetry, and 60-month performance guarantee."
    },
    {
        "auction_id": "CPCL-2026-PIPE-102",
        "title": "Intelligent Pigging & Ultrasonic In-Line Inspection (ILI) for Subsea Pipelines",
        "department": "CPCL Cauvery Basin / Marine Terminal",
        "category": "services",
        "status": "upcoming",
        "tenure_months": 24,
        "tenure_label": "24 Months (2 Years)",
        "tenure_start_date": "01-Nov-2026",
        "tenure_end_date": "31-Oct-2028",
        "tenure_extension_terms": "Performance based extension up to 12 months",
        "estimated_value": 110000000,
        "estimated_value_formatted": "Rs 11.00 Cr",
        "bidding_start": "15-Jun-2026 14:00 IST",
        "bidding_deadline": "15-Jul-2026 17:00 IST",
        "bids_count": 0,
        "current_lowest_bid": None,
        "current_lowest_formatted": "Bidding not opened",
        "min_turnover": 100000000,
        "min_local_content": 20,
        "requires_epfo": True,
        "requires_bis": False,
        "requires_startup_proof": False,
        "milestones": [
            {"period": "Year 1", "deliverable": "Pre-run geometry cleaning pig run and subsea pipeline baseline mapping"},
            {"period": "Year 2", "deliverable": "Ultrasonic wall loss inspection, anomaly classification and remnant life calculation"}
        ],
        "scope_summary": "High-resolution magnetic flux leakage (MFL) and ultrasonic wall-thickness mapping across 42 km of crude oil transfer lines."
    },
    {
        "auction_id": "CPCL-2026-CAT-014",
        "title": "Supply of Hydroprocessing Catalyst & Technical Services — CPCL Cauvery Basin Refinery",
        "department": "CPCL Cauvery Basin Refinery",
        "category": "catalyst-services",
        "status": "ended",
        "tenure_months": 24,
        "tenure_label": "24 Months (2 Years)",
        "tenure_start_date": "01-Jan-2024",
        "tenure_end_date": "31-Dec-2025",
        "tenure_extension_terms": "Completed contract tenure",
        "estimated_value": 400000000,
        "estimated_value_formatted": "Rs 40.00 Cr",
        "bidding_start": "01-Nov-2023",
        "bidding_deadline": "15-Dec-2023",
        "bids_count": 4,
        "current_lowest_bid": 389000000,
        "current_lowest_formatted": "Rs 38.90 Cr",
        "awarded_bidder": "M/s Bharat HydraTech Systems (Joint Venture)",
        "awarded_amount": 389000000,
        "awarded_amount_formatted": "Rs 38.90 Cr",
        "awarded_compliance_score": 98,
        "awarded_date": "15-Feb-2026",
        "min_turnover": 400000000,
        "min_local_content": 20,
        "requires_epfo": False,
        "requires_bis": True,
        "requires_startup_proof": False,
        "milestones": [
            {"period": "Cycle 1", "deliverable": "Catalyst batch supply and reactor loading protocol"},
            {"period": "Cycle 2", "deliverable": "Mid-term activity testing and spent catalyst safe recycling"}
        ],
        "scope_summary": "Catalyst batch supply, loading supervision, start-up kinetics benchmarking, and spent catalyst recycling."
    },
    {
        "auction_id": "GEM-2026-CONST-098",
        "title": "Civil Works — Minor Construction & Facility Modernization",
        "department": "Central Public Works Department (CPWD)",
        "category": "civil-works",
        "status": "ended",
        "tenure_months": 12,
        "tenure_label": "12 Months (1 Year)",
        "tenure_start_date": "01-Feb-2025",
        "tenure_end_date": "31-Jan-2026",
        "tenure_extension_terms": "Completed contract tenure",
        "estimated_value": 10000000,
        "estimated_value_formatted": "Rs 1.00 Cr",
        "bidding_start": "01-Dec-2024",
        "bidding_deadline": "10-Jan-2025",
        "bids_count": 5,
        "current_lowest_bid": 9450000,
        "current_lowest_formatted": "Rs 94.50 Lakh",
        "awarded_bidder": "M/s Shivalik Infrastructure Works",
        "awarded_amount": 9450000,
        "awarded_amount_formatted": "Rs 94.50 Lakh",
        "awarded_compliance_score": 92,
        "awarded_date": "20-Jan-2026",
        "min_turnover": 10000000,
        "min_local_content": 20,
        "requires_epfo": True,
        "requires_bis": False,
        "requires_startup_proof": False,
        "milestones": [
            {"period": "H1", "deliverable": "Structural civil reinforcement and drainage culvert casting"},
            {"period": "H2", "deliverable": "Road resurfacing, finishing works and final handover"}
        ],
        "scope_summary": "Perimeter fencing, drainage paving, and administrative wing seismic retrofitting."
    },
    {
        "auction_id": "GEM-2025-MED-044",
        "title": "Automated Medical Lab Diagnostic Reagents & Analyzer Maintenance",
        "department": "AIIMS Procurement Directorate",
        "category": "services",
        "status": "ended",
        "tenure_months": 36,
        "tenure_label": "36 Months (3 Years)",
        "tenure_start_date": "01-Jan-2023",
        "tenure_end_date": "31-Dec-2025",
        "tenure_extension_terms": "Concluded successfully with zero downtime penalty",
        "estimated_value": 65000000,
        "estimated_value_formatted": "Rs 6.50 Cr",
        "bidding_start": "01-Nov-2022",
        "bidding_deadline": "15-Dec-2022",
        "bids_count": 3,
        "current_lowest_bid": 62000000,
        "current_lowest_formatted": "Rs 6.20 Cr",
        "awarded_bidder": "M/s Vantara Diagnostics & Bio-Systems",
        "awarded_amount": 62000000,
        "awarded_amount_formatted": "Rs 6.20 Cr",
        "awarded_compliance_score": 100,
        "awarded_date": "18-Dec-2025",
        "min_turnover": 30000000,
        "min_local_content": 50,
        "requires_epfo": True,
        "requires_bis": True,
        "requires_startup_proof": False,
        "milestones": [
            {"period": "Year 1-3", "deliverable": "Continuous cold-chain supply and 99.5% analyzer uptime SLA"}
        ],
        "scope_summary": "Continuous reagent cold-chain supply, closed-system biochemistry analyzer leasing, and 99.5% uptime SLA."
    }
]


def list_auctions(
    status: Optional[str] = None,
    category: Optional[str] = None,
    tenure_months: Optional[int] = None,
    search: Optional[str] = None
) -> Dict[str, Any]:
    """Return filtered tenure auctions along with aggregate KPI metrics."""
    filtered = list(TENURE_AUCTIONS)

    if status and status.lower() != "all":
        st = status.lower().strip()
        filtered = [a for a in filtered if a.get("status") == st]

    if category and category.lower() != "all":
        cat = category.lower().strip()
        filtered = [a for a in filtered if a.get("category") == cat]

    if tenure_months is not None and tenure_months > 0:
        filtered = [a for a in filtered if a.get("tenure_months") == tenure_months]

    if search and search.strip():
        q = search.lower().strip()
        filtered = [
            a for a in filtered
            if q in a.get("auction_id", "").lower()
            or q in a.get("title", "").lower()
            or q in a.get("department", "").lower()
            or q in a.get("scope_summary", "").lower()
        ]

    # Aggregate metrics across the full catalog
    ongoing_count = sum(1 for a in TENURE_AUCTIONS if a.get("status") == "ongoing")
    upcoming_count = sum(1 for a in TENURE_AUCTIONS if a.get("status") == "upcoming")
    ended_count = sum(1 for a in TENURE_AUCTIONS if a.get("status") == "ended")
    total_active_pipeline = sum(a.get("estimated_value", 0) for a in TENURE_AUCTIONS if a.get("status") == "ongoing")

    return {
        "auctions": filtered,
        "total_count": len(filtered),
        "kpis": {
            "ongoing": ongoing_count,
            "upcoming": upcoming_count,
            "ended": ended_count,
            "total_active_pipeline": total_active_pipeline,
            "total_active_pipeline_formatted": f"Rs {total_active_pipeline / 10000000:.2f} Cr"
        }
    }


def get_auction(auction_id: str) -> Optional[Dict[str, Any]]:
    """Fetch an auction by ID."""
    auction_id_clean = auction_id.strip().upper()
    for a in TENURE_AUCTIONS:
        if a["auction_id"].upper() == auction_id_clean:
            return dict(a)
    return None
