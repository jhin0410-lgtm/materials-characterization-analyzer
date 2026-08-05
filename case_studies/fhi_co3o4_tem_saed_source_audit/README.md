# FHI Co3O4 TEM/SAED source audit

This case audits the institutional AC/CATLAB raw-data record `D63268` associated with the open-access Nature Catalysis article **Local solid-state processes adjust the selectivity in catalytic oxidation reactions on cobalt oxides**.

The record is the highest-priority public candidate currently identified for the unresolved cobalt-oxide TEM and SAED evidence lines because it combines:

- exact phase-pure `Co3O4` material identity;
- an institutional Max Planck raw-data archive;
- general TEM, operando bright-field TEM, HRTEM and SAED files;
- sample number `S32564`;
- a peer-reviewed article reporting the microscope, accelerating voltage, detector and operando holder;
- an article-level description of SAED centre finding, distortion correction and reciprocal-space analysis.

## Bounded audit

The live audit downloads only:

- `TEM.zip` — general TEM characterization;
- `OTEM_2.zip` — beam-damage studies, HRTEM and SAED.

The source archives are held only in a transient directory. Every archive member is streamed to verify its declared ZIP size and CRC and to compute SHA-256 without extraction. The final workflow artifact contains only:

- the observed archive hashes and sizes;
- a member-level path, size, CRC, SHA-256, suffix and representation inventory;
- filename-based TEM, HRTEM, SAED and calibration cues;
- a diagnostic scientific closeout;
- a checksum manifest for the metadata-only evidence.

The workflow rejects unsafe paths, duplicate normalized paths, symlinks, encrypted members, unsupported compression, oversized archives or members and excessive compression ratios.

## Run

```bash
python scripts/audit_fhi_co3o4_tem_saed.py \
  --config case_studies/fhi_co3o4_tem_saed_source_audit/case_config.json \
  --output outputs/fhi_co3o4_tem_saed_source_audit
```

The output directory must be absent or empty.

## Scientific boundary

The institutional record does not expose archive checksums or a versioned file manifest on its public page. The audit therefore supports the identity of the **observed download snapshot**, not immutable source identity across time.

This case does not authorize:

- image preprocessing or annotation;
- TEM segmentation inference or performance evaluation;
- SAED parameter tuning, calibrated d-spacing evaluation or phase indexing;
- U-Net retraining;
- scientific generalization or engineering decisions.

External validation remains blocked until source-authoritative checksums or a versioned manifest, member-level acquisition lineage, at least two independent samples or acquisitions, reuse authorization, independent TEM labels or traceable SAED centres and reciprocal calibration, and analyzer-development non-use are resolved.
