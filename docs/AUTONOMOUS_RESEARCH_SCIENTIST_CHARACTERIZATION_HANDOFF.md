# Characterization evidence authority in the Autonomous Research Scientist Architecture

`materials-characterization-analyzer` is the characterization evidence authority for the larger Autonomous Research Scientist Architecture. It does not act as the global research orchestrator and it does not promote its own outputs into causal, predictive, or engineering truth.

The corresponding research orchestrator is `materials-data-analyzer`. The repositories remain independently testable and versioned. Their integration boundary is a portable, checksum-bound handoff rather than an in-process import of producer implementation details.

## Responsibility boundary

The characterization authority owns instrument- and modality-specific analysis, raw/acquisition/calibration provenance checks, feature extraction, validation evidence, and the monotonic L0-L8 characterization evidence ladder.

The research orchestrator owns research-goal decomposition, discrepancy diagnosis, hypothesis state, evidence-gap planning, source acquisition, analysis/simulation orchestration, explicit action authorization, authenticated epistemic transitions, recursive continuation, and bounded stopping.

Neither side may infer a stronger scientific claim solely because the other side accepted an artifact structurally.

## L0-L8 handoff binding

A handoff bundle may optionally carry a full scientific evidence-ladder assessment produced by `mca.evidence_ladder.evaluate_evidence_ladder`. The assessment remains a separate artifact from the empirical `source_manifest`, `analysis_manifest`, and `comparability_matrix` evidence references.

A hardened bundle build and validation performs all of the following before the ladder is accepted as characterization maturity metadata:

1. checksum- and size-bind the assessment file;
2. reconstruct the assessment from its embedded declaration rather than trusting producer-authored summary fields;
3. require exact canonical declaration and assessment hashes;
4. preserve the monotonic L0-L8 rule, so a higher level cannot be `Supported` after a lower unsupported level;
5. require the ladder declaration identifier to match the handoff `case_id`;
6. require ladder source-binding digests for `source_manifest`, `analysis_manifest`, and `comparability_matrix` to match the exact bundle evidence files;
7. require the declared characterization modality to be represented by the bundle instruments (or an explicit multi-modal subject for a multi-instrument bundle);
8. require `scientific_status_promoted=false` and `downstream_use_authorized=false`.

The validated summary exposes the exact highest contiguous supported level and first blocking level so a downstream autonomous planner can request the next missing evidence without inventing scientific progress.

## Evidence levels

The current ladder is:

- L0 software integration
- L1 raw representation identity
- L2 acquisition provenance integrity
- L3 instrument calibration validity
- L4 method/algorithm validation
- L5 target material/domain validation
- L6 independent external validation
- L7 replicated multisource support
- L8 engineering decision readiness

A first blocker at L6, for example, means that lower levels can remain useful while independent external validation is still required. It is not permission to label the result independently validated.

## Backward compatibility

Legacy handoff bundles remain schema `1.0` and contain no `scientific_evidence_ladder`. A ladder-enabled bundle is explicitly schema `1.1`. The explicit outer schema version is intentional: the original schema-1.0 manifest is closed-world, so adding a new field under the old version would make compatibility ambiguous and would cause strict pre-extension consumers to reject the bundle without a capability signal.

The current validator accepts both forms. Schema `1.0` is interpreted as the legacy no-ladder contract. Schema `1.1` requires the independently replayable ladder record and cannot silently degrade to schema `1.0` semantics.

## Scientific boundary

A validated ladder handoff establishes identity and deterministic assessment replay. It does **not** by itself establish identical physical aliquots, cross-modal scientific comparability, material truth, independence, replication, causality, predictive validity, or engineering release readiness.

Open evidence-acquisition work such as independent cobalt-oxide TEM validation and raw calibrated SAED validation therefore remains scientifically material. The architecture must plan around those blockers rather than close them by software convention.
