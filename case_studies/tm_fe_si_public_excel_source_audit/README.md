# TM-Fe-Si public Excel source audit

## Purpose

This case freezes a source-and-schema audit for the uploaded 13-workbook subset of the public TM-Fe-Si dataset before any new feature extraction, normalization, phase inference, or cross-repository modeling is attempted.

The public source is:

- Data in Brief article DOI `10.1016/j.dib.2022.108868`;
- Mendeley Data DOI `10.17632/gp8rkw2k6v.2` (version 2, CC BY 4.0).

The uploaded subset contains one six-composition XRD workbook and paired dc-magnetization / isothermal M-H workbooks for Ti, Zr, Hf, V, Nb, and Ta nominal compositions. The full public dataset also contains SEM/EDS evidence, but those files are not present in the uploaded 13-workbook subset and are therefore outside this audit.

## Measurement context preserved

The publication describes 1.5 g polycrystalline samples prepared at nominal `TM:Fe:Si = 7:52:41`, arc melted under Ar, remelted several times, annealed at 1050 °C for one day, and air cooled.

- XRD: room-temperature powdered material, Shimadzu XRD-7000L, Cu-Kα radiation, Bragg-Brentano geometry.
- dc magnetization: bulk material, 100 Oe; 50–400 K on Quantum Design VersaLab VSM; high-temperature 400–800 K on Tamakawa TM-VSM33483-HGC.
- M-H: bulk material on VersaLab VSM from -30 to +30 kOe at 50, 100, 200, 300, and 400 K.

## Important audit findings

The workbook XML `dimension_ref` is not a reliable data-range proxy because formatted blank cells extend several worksheets. `source_audit_snapshot.json` therefore records actual non-empty ranges observed from the workbook content.

The XRD workbook contains six `(2θ, intensity)` pairs from 20 to 90 degrees. The associated publication explicitly states that the origin of each XRD pattern was shifted by an integer value for clarity. Consequently, absolute XRD intensity magnitude is not comparable across the six compositions from this figure-data workbook. No offset is silently removed.

The dc workbooks are not schema-identical: Ti contains only `T (K)` and `M (emu/g)`, while Zr/Hf/V/Nb/Ta also contain `dM/dT`. Those derivative values are stored as values rather than workbook formulas, so their derivation is not encoded in the Excel files.

Zr and Hf include the high-temperature magnetization segment. Because the source publication states that 50–400 K and 400–800 K were measured using different VSM instruments, the complete Zr/Hf temperature trajectories must preserve this instrument-segment provenance.

M-H trajectories have unequal row counts. Curves must be keyed by their physical H coordinate and temperature, never joined or trimmed by spreadsheet row number.

## Cross-modal identity boundary

The source describes XRD on powdered material and magnetometry on bulk material. It does not provide a specimen identifier that proves the exact physical object was measured in both modalities. The strongest defensible shared identity for this subset is therefore the nominal composition plus common preparation/batch family, not exact specimen identity.

This distinction is required for the future MCA → MDA handoff. Stable IDs must encode nominal composition/preparation identity and must not be inferred from row order or filename position.

## Scientific closeout

- workbook access/schema audit: **Supported**;
- article-level source/version/license and measurement context: **Supported**;
- exact specimen identity across XRD and VSM: **Inconclusive**;
- absolute XRD intensity comparability across compositions: **Unsupported**;
- XRD peak-position descriptive evidence: **Diagnostic candidate**;
- magnetic-property descriptive evidence: **Diagnostic candidate**;
- predictive, causal, or engineering-decision use: **Unsupported / not authorized**.

This dataset is suitable as a real descriptive cross-repository case, not as evidence for a predictive materials model.

## Next step

Freeze a narrow MCA XRD handoff contract that preserves the integer-offset limitation and nominal-composition/preparation identity. Only after that producer contract is frozen should MDA consume it with a consumer-owned magnetic-property table through the existing `mda-characterization-import` policy path.

No raw workbook is committed by this case.
