# BIR-MicroED 300 keV SAED calibration-readiness assessment

## Purpose

Close the current BIR 300 keV source-audit stage at the point where additional
source bytes stop being the highest-value next action.

Previous verified evidence already establishes:

- the exact Zenodo record and dataset-level CC BY 4.0 reuse terms;
- six archive identities and checksums;
- a bounded central-directory inventory for `AVAAGA_300kV_293K.zip`;
- four `.tvips` members in that archive;
- a structurally valid 256-byte TVIPS general header in the selected `series1.tvips` member;
- source-native filename incompatibility with the documented RosettaSciIO `_000.tvips` loader gate.

The associated peer-reviewed methods report that the 300 kV diffraction cohort was
collected on a Tecnai F30 TEM equipped with a TVIPS TemCam XF416 CMOS detector,
using microprobe diffraction mode, a parallel beam, and a 100 µm selected-area
aperture. These facts strengthen instrument and measurement-mode provenance, but
they are cohort-level method facts rather than immutable per-file acquisition IDs.

## Why the source is still not ready for quantitative SAED indexing

The verified TVIPS header contains raw scalar fields including `ht=300`,
`pixelsize=15500`, `magtotal=0`, `binx=2`, `biny=2`, and
`frameheaderbytes=180`. Those fields are preserved as observations, not silently
converted into physical calibration.

Quantitative diffraction indexing still requires traceable evidence for:

1. pattern centre;
2. reciprocal-space scale / camera constant or an equivalent calibrated geometry;
3. exact sample/crystal and acquisition lineage;
4. a frozen phase/reflection/zone-axis reference protocol before validation.

The current public evidence does not yet close those gates. Therefore the next
requirement is authoritative or independently reproducible pattern-centre and
reciprocal calibration for an exact BIR 300 keV TVIPS acquisition.

## Run

This assessment reads only tracked evidence snapshots and the contract; it makes no
new network or source-byte request.

```bash
python scripts/assess_zenodo_bir_300kev_saed_calibration_readiness.py \
  --contract case_studies/zenodo_bir_300kev_saed_calibration_readiness/evidence_contract.json \
  --output outputs/zenodo_bir_300kev_saed_calibration_readiness/assessment.json
```

## Scientific closeout

Current evidence level: **Diagnostic**.

- instrument/detector/diffraction-mode context: supported at published cohort level;
- TVIPS internal format: supported for the selected member prefix;
- quantitative SAED indexing readiness: **Unsupported**;
- external-validation readiness: **Inconclusive**;
- engineering-decision readiness: **Unsupported**.

Do not download the remaining BIR archives, decode diffraction pixels, fit phase
assignments, or tune the SAED analyzer merely because more source bytes are
available. Those actions should resume only when a defined unresolved evidence
requirement makes them necessary.
