from pathlib import Path

path = Path("scripts/patch_co3o4_observed_snapshot_history.py")
text = path.read_text(encoding="utf-8")
old = "The changed UUID and SHA-256 demonstrate unstable public source identity."
new = "The changed file UUID and SHA-256 demonstrate unstable public source identity."
if old not in text:
    raise SystemExit("observed-history wording anchor not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
