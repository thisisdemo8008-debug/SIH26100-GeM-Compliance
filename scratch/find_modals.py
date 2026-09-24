import re
from pathlib import Path

text = Path("index.html").read_text(encoding="utf-8")
modals = re.findall(r'id=["\']([a-zA-Z0-9_]*Modal[a-zA-Z0-9_]*)["\']', text)
print("Modal IDs found:", set(modals))
