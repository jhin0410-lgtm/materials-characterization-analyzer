from pathlib import Path

path = Path("scripts/patch_co3o4_snapshot_aware_audit.py")
text = path.read_text(encoding="utf-8")
old = "'The directly extracted known snapshot contained 760 members and only three decodable images: Data/SEM/2.png, Data/SEM/3.png, and Data/SEM/4.png. All were 1536 x 1103 16-bit PNG images, with no deposited TEM, HRTEM, STEM, DM3, DM4, EMD, SER, TIFF, or TIF source file.',"
new = "'The directly extracted known snapshot contained 760 file members and only three decodable images: Data/SEM/2.png, Data/SEM/3.png, and Data/SEM/4.png. All were 1536 x 1103 16-bit PNG images, with no deposited TEM, HRTEM, STEM, DM3, DM4, EMD, SER, TIFF, or TIF source file.',"
if old not in text:
    raise SystemExit("member-evidence wording anchor not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
