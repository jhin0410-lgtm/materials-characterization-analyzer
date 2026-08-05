# Frozen TEM and SAED Evaluation Protocol

This protocol must be completed before viewing analyzer outputs on an accepted candidate.

## Common contract

Record and freeze:

- evaluation question;
- target material and acquisition domain;
- source files and SHA-256;
- sample and acquisition grouping;
- inclusion and exclusion rules;
- allowed preprocessing;
- software version and configuration;
- primary metrics;
- uncertainty method;
- sensitivity analyses;
- failure thresholds;
- scientific claim ceiling.

No candidate result may be used to change the evaluated model or primary parameters.

## TEM segmentation protocol

### Eligibility

- raw or demonstrably lossless TEM/HRTEM;
- target-domain definition stated;
- parent/sample/acquisition disjointness verified;
- at least two independent samples or acquisitions;
- no use in training, threshold selection, early stopping, or model selection.

### Annotation

- two independent domain-competent labelers;
- labelers blinded to model prediction;
- written particle/background/overlap/boundary definition;
- separate recording of ambiguous regions;
- adjudication by a predefined rule;
- labeler agreement reported before consensus collapse.

### Frozen preprocessing

Explicitly state whether each operation is prohibited or allowed:

- cropping;
- resizing;
- intensity normalization;
- flat-field correction;
- denoising;
- contrast adjustment;
- artifact removal;
- patching;
- exclusion of majority-background regions.

No silent operation is allowed.

### Metrics

Report at minimum:

- Dice or IoU at image and acquisition level;
- precision and recall;
- object-count or particle-size bias when scientifically meaningful;
- per-sample distribution rather than pooled pixels alone;
- confidence intervals or bootstrap intervals grouped by acquisition;
- complete failure-case inventory.

### Claim ceiling

Cross-material data can support only a domain-shift diagnostic. It cannot establish cobalt-oxide in-domain performance.

## SAED protocol

### Eligibility

- static selected-area diffraction;
- source-bound accelerating voltage;
- detector and pixel geometry;
- traceable centre;
- traceable reciprocal calibration;
- at least two independent patterns or acquisitions;
- frozen reference assignments or independent reference structures.

### Frozen primary analysis

State before execution:

- centre source and uncertainty;
- radial bounds;
- smoothing method and parameter;
- background method;
- peak prominence and distance;
- calibration equation and units;
- candidate-to-reference matching tolerance;
- handling of unmatched rings;
- primary output fields.

### Sensitivity analysis

Predeclare perturbations for:

- centre position;
- smoothing;
- background subtraction;
- prominence;
- radial bounds;
- calibration uncertainty.

Sensitivity outputs are not an excuse to select the best-looking result after execution.

### Metrics

When reference evidence permits, report:

- ring detection precision and recall;
- radial-position error;
- calibrated d-spacing error;
- matched and unmatched reflection counts;
- per-pattern rather than pooled performance;
- uncertainty propagated from centre and calibration.

### Claim ceiling

Without traceable calibration, report pixel-space or radius-space diagnostics only. Do not claim d-spacing accuracy, phase identity, reflection assignment, or zone axis from analyzer output alone.

## Scientific closeout

Classify the result as:

- **Supported**
- **Diagnostic**
- **Inconclusive**
- **Unsupported**

For every closeout state:

- result;
- evidence level;
- strongest evidence;
- primary limitation;
- evidence that would change the conclusion;
- suitability for exploration, engineering decisions, or scientific claims.

Passing software tests does not upgrade scientific evidence.
