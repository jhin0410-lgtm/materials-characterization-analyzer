# README Demo Images

This folder stores representative demo result images used by the project README. The full `outputs/` directory is intentionally not committed; only selected README-ready images are preserved here.

All images are generated from synthetic/demo inputs in `data/demo/`. They are not real experimental result images and should be described as synthetic/demo output only.

## Image Sources

| Image | Source output | Demo command |
| --- | --- | --- |
| `xrd_result.png` | `outputs/xrd_pattern_with_peaks.png` | `python -m mca.cli analyze-all --xrd data/demo/synthetic_xrd.csv --sem data/demo/synthetic_sem.png --eds data/demo/synthetic_eds.csv --microns-per-pixel 0.05 --output outputs` |
| `sem_overlay.png` | `outputs/sem_overlay.png` | `python -m mca.cli analyze-all --xrd data/demo/synthetic_xrd.csv --sem data/demo/synthetic_sem.png --eds data/demo/synthetic_eds.csv --microns-per-pixel 0.05 --output outputs` |
| `eds_composition_chart.png` | `outputs/eds_composition_bar_chart.png` | `python -m mca.cli analyze-all --xrd data/demo/synthetic_xrd.csv --sem data/demo/synthetic_sem.png --eds data/demo/synthetic_eds.csv --microns-per-pixel 0.05 --output outputs` |

If these images are regenerated, copy only the representative README images into this folder and leave local run artifacts under the ignored `outputs/` directory.
