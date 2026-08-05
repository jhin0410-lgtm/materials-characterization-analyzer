# FHI Co3O4 TEM/SAED source audit

This case audits the institutional AC/CATLAB record `D63268` associated with the open-access Nature Catalysis article **Local solid-state processes adjust the selectivity in catalytic oxidation reactions on cobalt oxides**.

The record remains the highest-priority exact-material candidate identified for the unresolved cobalt-oxide TEM and SAED evidence lines because it combines:

- phase-pure `Co3O4` material identity;
- an institutional Max Planck `RAW DATA` record;
- listed general TEM, operando bright-field TEM, HRTEM and SAED archives;
- sample number `S32564`;
- a peer-reviewed article reporting the microscope, accelerating voltage, detector and operando holder;
- an article-level description of SAED centre finding, distortion correction and reciprocal-space analysis.

## Observed access state

The public record page displays `Open Access` and lists:

- `TEM.zip` — general TEM characterization;
- `OTEM_2.zip` — beam-damage studies, HRTEM and SAED.

However, the live anonymous requests to both listed `/send/...` links redirect to the repository `/login` page and return an HTML login form. The workflow therefore records:

```text
institutional_exact_material_record_confirmed_but_anonymous_source_download_requires_authentication
```

No credentials are supplied, guessed or bypassed. The audit does not claim that the listed archives were downloaded, hashed or inspected.

## Run

```bash
python scripts/audit_fhi_co3o4_tem_saed.py \
  --config case_studies/fhi_co3o4_tem_saed_source_audit/case_config.json \
  --output outputs/fhi_co3o4_tem_saed_source_audit
```

The output directory must be absent or empty.

Current metadata-only outputs are:

- `fhi_co3o4_tem_saed_audit_summary.json`;
- `fhi_co3o4_tem_saed_download_probe.csv`;
- `fhi_co3o4_tem_saed_audit_report.md`;
- `fhi_co3o4_tem_saed_audit_manifest.json`.

If the repository later permits an anonymous ZIP response, the same implementation can apply the bounded archive checks before publishing any member inventory. Those checks reject unsafe paths, duplicate normalized paths, symlinks, encrypted members, unsupported compression, oversized archives or members and excessive compression ratios. Source arrays remain transient and excluded from evidence artifacts.

## Scientific boundary

Supported:

- institutional record identity;
- exact `Co3O4` material context;
- listed file names, roles and declared sizes;
- the observed authentication blocker.

Not yet supported:

- archive or member identity and checksums;
- native-detector versus raster representation;
- member-level sample and acquisition lineage;
- independent TEM segmentation labels;
- traceable SAED centre and reciprocal calibration;
- data-specific reuse authorization;
- analyzer-development non-use.

This case does not authorize image preprocessing, annotation, TEM inference, SAED parameter tuning, phase indexing, U-Net retraining, scientific generalization or engineering decisions.
