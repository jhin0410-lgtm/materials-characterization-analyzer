# Analyzer Readiness Registry

This case records the current evidence boundary for every public analyzer in one
versioned, fail-closed registry.

Run:

```bash
mca analyzer-readiness \
  --config case_studies/analyzer_readiness_registry/readiness_registry.json \
  --output outputs/analyzer-readiness
```

The output separates:

- software validation;
- real-data diagnostic execution;
- scientific validation;
- independent external-validation readiness;
- engineering-decision readiness.

The registry does not rank techniques or promote automatic candidates into
material, phase, composition, chemical-state, functional-group, reaction,
mechanism, segmentation-performance, crystallographic, causal, or engineering
claims.

## Current snapshot

All ten analyzer families have packaged baseline software and public real-data
diagnostic execution or method-suitability evidence.

No analyzer is currently marked ready for its strongest independent external
scientific claim, and none is marked ready for engineering decisions.

TEM and SAED are not the only scientifically bounded workflows. They have deeper
external-validation contracts because segmentation performance and
crystallographic correctness require explicit independent cohorts, labels,
calibration, references, and frozen protocols. The spectroscopy, diffraction,
microscopy, and thermal baselines also remain diagnostic until their
technique-specific reference and uncertainty evidence is obtained.
