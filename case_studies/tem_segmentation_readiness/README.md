# TEM Segmentation Readiness Consolidation

This case combines existing TEM segmentation evidence into one user-facing readiness decision. It does not rerun the source audits, download raw arrays, train a U-Net, run inference, or calculate segmentation metrics.

## Required evidence

Download or generate these existing summary files:

1. `training_data_readiness_summary.json`
   - produced by `public_cobalt_oxide_tem_training_data_audit`
2. `parent_overlap_audit_summary.json`
   - produced by `public_cobalt_oxide_tem_parent_overlap_audit`

Optional evidence:

3. `external_validation_candidate_summary.json`
   - produced by `dryad_hrtem_external_validation_candidate_assessment`
4. `dryad-acquisition-readiness.json`
   - produced by the Dryad pilot workflow even when authenticated array access is unavailable
5. `pilot_pair_audit_summary.json`
   - produced only after an authenticated real HDF5 and content-overlap audit completes

Each supplied JSON file is schema- and case-ID-validated, hashed with SHA-256, and recorded in the output manifest. Missing optional evidence remains unresolved and never becomes a passed gate.

## Run

```bash
mca tem-readiness \
  --training-summary path/to/training_data_readiness_summary.json \
  --parent-overlap-summary path/to/parent_overlap_audit_summary.json \
  --external-candidate-summary path/to/external_validation_candidate_summary.json \
  --pilot-readiness path/to/dryad-acquisition-readiness.json \
  --output outputs/tem-segmentation-readiness
```

After an authenticated Dryad pilot audit exists, add:

```bash
  --pilot-summary path/to/pilot_pair_audit_summary.json
```

The output directory must be absent or empty.

## Outputs

- `tem_segmentation_readiness_summary.json`
- `tem_segmentation_readiness_report.md`
- `tem_segmentation_readiness_manifest.json`

## Decision boundaries

The command reports separate gates for:

- software-only model-training experiments;
- readiness to freeze a predeclared in-domain evaluation protocol;
- independent performance claims;
- diagnostic cross-material stress testing;
- engineering release.

Under the currently verified public evidence, the expected result is:

```text
not_ready_for_scientific_model_performance_evaluation
```

The existing 256 image-label patches can support software experiments, but the source notebook's patch-level split is not parent-disjoint and no independent labeled cobalt-oxide external validation set is available. Retraining is therefore not the current scientific priority.

## Scientific closeout

**Conclusion level: Supported — for readiness only.**

The supported conclusion is that the current evidence is insufficient for an independent segmentation-performance claim. This is not a conclusion about the U-Net's true accuracy. Evidence that would change the readiness conclusion is a checksum-bound, predeclared, parent-disjoint cobalt-oxide validation set with immutable acquisition lineage, independent expert labels, and documented non-use in training, tuning, threshold selection, or model selection.
