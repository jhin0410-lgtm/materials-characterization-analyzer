# Scientific Evidence Ladder

## Purpose

Characterization datasets are not simply “usable” or “unusable”. A source can provide
strong evidence for file handling, detector representation, calibration, or method
behavior while still being insufficient for an exact-material or independent external
validation claim.

This project therefore represents scientific readiness as a monotonic L0-L8 ladder in
addition to the existing downstream-use contract.

```text
L0  software integration
L1  raw representation and byte identity
L2  acquisition/provenance integrity
L3  instrument/calibration validity
L4  method/algorithm validation
L5  material-domain validation
L6  independent external validation
L7  replicated multi-source support
L8  engineering decision readiness
```

A level can be `Supported` only if every lower level is also `Supported`. `Diagnostic`,
`Inconclusive`, or `Unsupported` at a lower level blocks higher-level Supported status.
This prevents scientific “ladder skipping”.

## Why this is separate from downstream use

`mca.downstream_use_contract` already answers a different question:

> Given the current scientific closeout and study design, what downstream use is
> permitted: display, descriptive, association, predictive, causal, or engineering?

The evidence ladder instead answers:

> Which scientific evidence prerequisites have actually been demonstrated for this
> particular source/result?

The ladder never authorizes downstream use by itself. Its handoff explicitly sets
`downstream_use_authorized=false` and `scientific_status_promoted=false`.

## Level semantics

### L0 — software integration

The source/result exercises the intended parser, analyzer, plotting, reporting, or
workflow path. This is software evidence, not measurement truth.

### L1 — raw representation and identity

The representation is raw or demonstrably lossless as required by the claim, and stable
byte identity/version is verified by checksum or equivalent immutable binding.

### L2 — acquisition/provenance integrity

Sample, acquisition, pattern/image/trace identity, and relevant processing lineage are
source- or operator-supported rather than inferred from file order, appearance, or
filenames.

### L3 — instrument/calibration validity

The instrument/detector/acquisition settings and any calibration required for the claim
are traceable. Examples include accelerating voltage, detector/pixel metadata, camera
length or reciprocal calibration, pattern center procedure, wavelength, or calibrated
process power where scientifically relevant.

### L4 — method/algorithm validation

The method is tested under a predeclared analysis contract with appropriate reference,
sensitivity, robustness, and/or numerical checks. This level does not automatically
establish the target material.

### L5 — material-domain validation

The evidence directly represents the declared target material/composition/domain.
Cross-material method datasets cannot satisfy this level for a different target.

### L6 — independent external validation

The validation evidence is independent of model/method development under the declared
independence dimensions. Different filenames or checksums alone do not prove sample,
acquisition, parent, creator, or development independence.

### L7 — replicated multi-source support

The result is reproduced across explicitly provenance-disjoint sources, samples,
acquisitions, instruments, facilities, or studies as required by the scientific claim.

### L8 — engineering decision readiness

Operational validation, decision thresholds, deployment/facility conditions, failure
modes, and engineering-use boundaries are supported. L8 is intentionally much stronger
than “the analysis code worked”.

## Current characterization examples

### FINDS SAED JPEG

The existing FINDS example is useful for exercising the SAED software and center/smoothing
sensitivity path. Because it is a lossy JPEG without raw detector identity, immutable
sample/acquisition lineage, material metadata, or reciprocal calibration, it can support
L0 software integration but must not be promoted into L1 raw-detector or material-aware
SAED validation.

### Calibrated cross-material electron diffraction

A raw/lossless electron-diffraction dataset on a non-Co3O4 material may be extremely
useful. If byte identity, acquisition provenance, calibration, and a frozen method
reference are demonstrated, it may support L0-L4. It still cannot satisfy L5 Co3O4
material-domain validation merely because the diffraction algorithm behaves correctly.

This is how BIR/MicroED, SerialRED, 3DED, 4D-STEM, or similar sources should be retained
as positive method evidence rather than discarded as “wrong material”.

### FHI D63268 Co3O4 TEM/SAED

The institutional record and associated publication provide strong exact-material and
instrument context. However, the current anonymous file links redirect to authentication,
so archive bytes/member checksums and archive-level acquisition/calibration mappings have
not been obtained.

The ladder is intentionally monotonic: article-level evidence suggesting an exact Co3O4
context cannot skip unverified L1-L3 prerequisites and directly mark L5 Supported. If the
authors/custodian provide the raw archives and provenance, those levels can be evaluated
in order.

### Development-coupled public Co3O4 TEM data

A source may be exactly Co3O4 and still fail independent external validation because it
was used for model development, labels, thresholding, or related selection. Once its
raw/provenance/method/material requirements are independently verified it may support
levels through L5, while L6 remains Inconclusive or Unsupported until development
non-use and content/provenance disjointness are established.

## Declaration contract

A declaration contains:

- `schema_version`
- stable `declaration_id`
- `subject`:
  - modality
  - source material domain
  - target material domain
  - claim scope
- checksum-bound `source_bindings`
- all L0-L8 assessments
- top-level limitations

Each level contains exactly:

- `assessment`: `Supported`, `Diagnostic`, `Inconclusive`, or `Unsupported`
- `evidence`: explicit evidence statements
- `limitations`

A Supported level requires non-empty evidence. Every declaration and evaluation receives
a deterministic canonical SHA-256.

## CLI

```powershell
python -m mca.evidence_ladder_cli `
  --declaration .\case_studies\my_source\evidence_ladder.json `
  --output .\outputs\my_source\evidence_ladder_assessment.json
```

The output path is immutable: an existing file is rejected.

## Handoff to the research agent

The assessment contains a compact handoff with:

- subject and source bindings
- highest contiguous Supported level
- first blocking level
- no scientific-status promotion
- no downstream-use authorization

A downstream research agent should use the first blocking level as an evidence gap. For
example:

```text
highest = L4 method/algorithm validation
first blocking = L5 material-domain validation
```

means the correct next research question is to acquire or generate *target-material*
evidence, not to rerun the same cross-material method benchmark and call it independent
validation.

Similarly:

```text
highest = L5 material-domain validation
first blocking = L6 independent external validation
```

means more same-development data do not solve the blocker; the next action should seek a
provenance- and development-disjoint validation cohort.

## Scientific boundary

The ladder must not be used to:

- infer raw status from a publication figure;
- infer acquisition IDs from filenames or row order;
- infer calibration from image appearance;
- promote a cross-material proxy to target-material validation;
- infer independence from file count;
- treat simulation as empirical measurement truth;
- treat L0 software success as scientific validation;
- treat L6 external validation as L7 replication without a disjointness contract;
- infer engineering readiness without operational validation.
