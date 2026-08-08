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

Snapshot date: **2026-08-09**.

All ten analyzer families have packaged baseline software and public real-data
diagnostic execution or method-suitability evidence. The current scientific
evidence distribution remains deliberately unchanged:

- `Diagnostic`: 8 analyzers — XRD, SEM, EDS, Raman, XPS, FTIR, TGA, DSC;
- `Inconclusive`: 2 analyzers — TEM and SAED;
- independent external-validation ready: 0;
- engineering-decision ready: 0.

Recent TEM and SAED source work increases provenance depth without promoting
scientific readiness. TEM now has multiple bounded public archive/native-format
and access-readiness audits, but still lacks an independent in-domain Co3O4
cohort with authoritative acquisition lineage and blinded segmentation truth.

SAED now includes a checksum-bound SrTiO3 chain that reaches the actual
2048 x 2048 float64 diffraction pixels and final-publication provenance. The
23 K, 91 K and 172 K temperature semantics are supported, and source-pattern
family correspondence to Nature Figure 1d is diagnostic. Individual
source-TIFF-to-panel identity, source-pixel reciprocal calibration, pattern
centre, acquisition independence and complete reflection truth remain
inconclusive. Separate BIR 300 keV evidence supports source/instrument and TVIPS
format context but does not close those calibration gaps.

TEM and SAED are not the only scientifically bounded workflows. They have deeper
external-validation contracts because segmentation performance and
crystallographic correctness require explicit independent cohorts, labels,
calibration, references, and frozen protocols. The spectroscopy, diffraction,
microscopy, and thermal baselines also remain diagnostic until their
technique-specific reference and uncertainty evidence is obtained.

The next useful scientific advance is therefore not to add another analyzer or
collect more unqualified source files. It is to select one technique for which a
traceable independent reference can support a narrow, predeclared validation
claim and close that case end to end.
