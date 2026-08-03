from pathlib import Path

path = Path("scripts/audit_co3o4_public_tem_candidates.py")
text = path.read_text(encoding="utf-8")
old = 'if counts["candidate_count"] != 9:'
new = 'if counts["candidate_count"] != 10:'
if old not in text:
    raise SystemExit("candidate-count anchor not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
