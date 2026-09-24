import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
text = Path("index.html").read_text(encoding="utf-8")

pos1 = text.find("async function verifyChain()")
if pos1 != -1:
    print("--- verifyChain implementation ---")
    print(text[pos1:pos1+1500])

pos2 = text.find("function wireAuditTab()")
if pos2 != -1:
    print("\n--- wireAuditTab implementation ---")
    print(text[pos2:pos2+1500])
