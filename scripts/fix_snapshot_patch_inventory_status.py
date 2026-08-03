from pathlib import Path

path = Path("scripts/patch_co3o4_snapshot_aware_audit.py")
text = path.read_text(encoding="utf-8")
old = "candidate['file_inventory_status'] = 'snapshot_exact_but_same_version_identity_unstable'"
new = "candidate['file_inventory_status'] = 'exact'"
if old not in text:
    raise SystemExit("inventory-status patch anchor not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
