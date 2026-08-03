from pathlib import Path

path = Path("scripts/patch_co3o4_snapshot_aware_audit.py")
text = path.read_text(encoding="utf-8")
old = "script = replace_function(script, 'main', '__main__', main_function)"
new = """main_start = script.index('def main() -> int:')
main_end = script.index('\\n\\nif __name__ == \\\"__main__\\\":', main_start)
script = script[:main_start] + main_function.strip() + script[main_end:]"""
if old not in text:
    raise SystemExit("main-boundary patch anchor not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
