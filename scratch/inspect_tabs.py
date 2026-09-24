import re
from pathlib import Path

text = Path("index.html").read_text(encoding="utf-8")

# Search for activeTab or currentTab or view switching
tabs = re.findall(r'tab\s*===?\s*["\']([^"\']+)["\']', text)
print("Tabs referenced:", set(tabs))

officer_tabs = re.findall(r'officerTab\s*===?\s*["\']([^"\']+)["\']', text)
print("Officer tabs referenced:", set(officer_tabs))

bidder_tabs = re.findall(r'bidderTab\s*===?\s*["\']([^"\']+)["\']', text)
print("Bidder tabs referenced:", set(bidder_tabs))

# Check role switching
roles = re.findall(r'role\s*===?\s*["\']([^"\']+)["\']', text)
print("Roles referenced:", set(roles))

# Let's inspect sidebar items
sidebar_match = re.search(r'function renderSidebar\(\)\s*\{([\s\S]*?)\}', text)
if sidebar_match:
    print("\n--- renderSidebar snippet ---")
    print(sidebar_match.group(1)[:1200])

# Let's inspect officer shell
officer_shell = re.search(r'function renderOfficerShell\(\)\s*\{([\s\S]*?)\}', text)
if officer_shell:
    print("\n--- renderOfficerShell snippet ---")
    print(officer_shell.group(1)[:1200])
