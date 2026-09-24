import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import hashlib
from fastapi.testclient import TestClient
from backend.main import app

c = TestClient(app)
rows = c.get("/api/audit").json()
print("Total audit rows:", len(rows))

def sha256_hex(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

prev = "GENESIS"
mismatches = 0
for idx, r in enumerate(rows):
    if r["prevHash"] != prev:
        print(f"Row {r['seq']}: prevHash mismatch! got {r['prevHash']} expected {prev}")
        mismatches += 1
        break
    
    # client JS does:
    # JSON.stringify({seq:entry.seq,timestamp:entry.timestamp,actor:entry.actor,action:entry.action,bidId:entry.bidId,details:entry.details,prevHash:entry.prevHash})
    payload = json.dumps({
        "seq": r["seq"],
        "timestamp": r["timestamp"],
        "actor": r["actor"],
        "action": r["action"],
        "bidId": r["bidId"],
        "details": r["details"],
        "prevHash": r["prevHash"]
    }, separators=(',', ':'), ensure_ascii=False)
    
    h = sha256_hex(payload)
    if h != r["hash"]:
        print(f"Row {r['seq']} ({r['action']}): hash mismatch! recomputed={h} != db={r['hash']}")
        print("  Payload:", payload[:250])
        mismatches += 1
        break
    prev = r["hash"]

if mismatches == 0:
    print("SUCCESS: ALL CLIENT HASHES MATCH PERFECTLY!")
