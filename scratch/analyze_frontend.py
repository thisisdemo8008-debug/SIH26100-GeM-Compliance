import re
from pathlib import Path

html_path = Path("index.html")
text = html_path.read_text(encoding="utf-8")

views = re.findall(r'id=["\']view-([^"\']+)["\']', text)
print("Views (id=view-*):", set(views))

nav_items = re.findall(r'data-view=["\']([^"\']+)["\']', text)
print("Nav items (data-view):", set(nav_items))

functions = re.findall(r'function\s+([a-zA-Z0-9_]+)\s*\(', text)
print("Total JS functions:", len(functions))

key_fns = [fn for fn in functions if any(k in fn.lower() for k in ['render', 'load', 'show', 'tab', 'modal', 'cartel', 'copilot', 'dsc', 'auction', 'verify', 'audit'])]
print("Key functions count:", len(key_fns))
for f in key_fns[:35]:
    print(" -", f)

# Check all fetch calls
fetches = re.findall(r'fetch\s*\(\s*["\'`]([^"\'`?]+)', text)
print("\nUnique fetch endpoints in index.html:")
for ep in sorted(set(fetches)):
    print(" -", ep)
