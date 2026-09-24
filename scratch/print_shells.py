import re
from pathlib import Path
import sys

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

text = Path("index.html").read_text(encoding="utf-8")

m = re.search(r'function renderOfficerShell\(\)\s*\{([\s\S]*?)(?:function [a-zA-Z0-9_]+\s*\(|\Z)', text)
if m:
    print("OFFICER SHELL:")
    for line in m.group(1).splitlines()[:60]:
        print(line)

m2 = re.search(r'function renderBidderShell\(\)\s*\{([\s\S]*?)(?:function [a-zA-Z0-9_]+\s*\(|\Z)', text)
if m2:
    print("\nBIDDER SHELL:")
    for line in m2.group(1).splitlines()[:60]:
        print(line)
