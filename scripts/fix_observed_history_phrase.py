from pathlib import Path

path = Path("scripts/patch_co3o4_observed_snapshot_history.py")
text = path.read_text(encoding="utf-8")
old = "The changed UUID and SHA-256 demonstrate unstable public source identity."
new = "The changed file UUID and SHA-256 demonstrate unstable public source identity"
if old in text:
    path.write_text(
        text.replace(
            old,
            new + ", so stable immutable archive identity is unavailable.",
            1,
        ),
        encoding="utf-8",
    )
elif new not in text:
    raise SystemExit("observed-history wording anchor not found")
