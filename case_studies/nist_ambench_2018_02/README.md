# NIST AM-Bench 2018-02 Optical-Metrology Producer Case

## Purpose

This case gives `materials-characterization-analyzer` ownership of the characterization side of the existing NIST AM-Bench process–characterization example.

It exports ten trace-level, source-reported transverse-cross-section measurements as a versioned characterization handoff bundle. Laser power, scan speed, and derived process descriptors are deliberately excluded and remain the responsibility of `materials-data-analyzer`.

## Official sources

- Benchmark description: `https://www.nist.gov/ambench/amb2018-02-description`
- Transverse cross-section results: `https://www.nist.gov/ambench/chal-amb2018-02-mp-xsection`
- Public Data Repository record: `https://doi.org/10.18434/mds2-3830`
- Associated publication: `https://doi.org/10.1007/s40192-020-00169-1`

The tracked numeric table was manually transcribed from the official NIST results page. Raw optical micrographs are not redistributed or parsed by this case.

## Measurement scope

- Material: IN625
- System: NIST Additive Manufacturing Metrology Testbed (`AMMT`)
- Specimens: ten individual laser traces
- Characterization: polished transverse cross sections measured in the NIST microscope-control metrology mode
- Exported features per trace:
  - melt-pool width mean;
  - melt-pool width within-measurement standard deviation;
  - melt-pool depth mean;
  - melt-pool depth within-measurement standard deviation.

The exporter reproduces the rounded NIST case-level width/depth means and between-trace standard deviations before writing the bundle.

## Run

```bash
python scripts/export_nist_ambench_2018_02_optical_metrology_bundle.py \
  --config case_studies/nist_ambench_2018_02/case_config.json \
  --output outputs/nist-ambench-2018-02-optical-metrology
```

The output directory must be absent or empty. Existing files are preserved and the command stops rather than overwriting them.

## Outputs

```text
outputs/nist-ambench-2018-02-optical-metrology/
├── case_source_manifest.json
├── case_analysis_manifest.json
├── comparability_matrix.csv
├── characterization_features_long.csv
├── sample_context.csv
├── characterization_handoff_bundle.json
├── case_summary.json
└── case_report.md
```

Expected bundle counts:

- 10 samples;
- 10 measurements;
- 40 feature records;
- 40 source SHA-256 values;
- 40 preprocessing identifiers;
- one instrument: `optical_microscopy_metrology`.

## Repository boundary

Producer-owned fields:

- trace-level optical-metrology values;
- measurement method and source type;
- source hash and preprocessing provenance;
- `sample_id`, `case_id`, trace number, material, and system identity context;
- scientific limitations.

Consumer-owned fields:

- corrected actual laser power;
- scan speed;
- line-energy descriptor;
- process–characterization integration and descriptive case summaries.

The consumer must verify that overlapping identity columns agree before joining an external process table.

## Scientific closeout

**Evidence level: Diagnostic**

Supported:

- ten explicit AMMT trace IDs are exported through the stable feature contract;
- case and trace mappings are preserved;
- source-reported metrology values and within-measurement standard deviations are retained;
- source and preprocessing provenance are complete;
- the producer bundle can be independently validated by a consumer repository.

Not supported:

- independent remeasurement of the raw optical micrographs;
- validation of the NIST microscope-control procedure;
- causal separation of laser power and scan-speed effects;
- prediction, process optimization, transfer to other alloys or systems, or engineering release decisions.
