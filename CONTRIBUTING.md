# Contributing

Contributions are welcome when they preserve the project's scientific boundaries, provenance requirements, and stable public interfaces.

## Before opening a change

1. Search existing issues and pull requests.
2. Keep the proposed change narrowly scoped.
3. Do not include proprietary, confidential, unpublished, personally identifiable, or ambiguously licensed data.
4. Use synthetic fixtures for software tests unless a real dataset is explicitly public, redistributable, and fully cited.
5. Do not add automatic material, phase, chemical-state, functional-group, reaction, or mechanism claims without an explicit scientific validation contract.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest -q
```

## Pull request requirements

A pull request should include:

- the problem being solved;
- files and public behavior affected;
- assumptions and compatibility boundaries;
- tests added or updated;
- commands run and their results;
- scientific limitations and unresolved metadata;
- generated-artifact handling;
- confirmation that unrelated files were not modified.

## Scientific validation

Software validation and scientific validation are separate.

A passing test suite confirms that code paths execute as expected on the tested fixtures. It does not prove that a method is suitable for a real material, instrument, sample preparation, acquisition condition, or engineering decision.

For real-data cases, document at minimum:

- source and license;
- sample identity and processing history;
- instrument and acquisition conditions;
- units and calibration;
- preprocessing and exclusions;
- comparability constraints;
- evidence classification: `Supported`, `Diagnostic`, `Inconclusive`, or `Unsupported`.

## Data and generated files

Do not commit downloaded raw datasets, private instrument exports, local outputs, caches, virtual environments, credentials, or temporary files. Public case studies should fetch external files reproducibly and record source identifiers and checksums rather than vendoring large source datasets.

## Release preparation

Changes intended for a versioned release must follow [`docs/release_checklist.md`](docs/release_checklist.md). In particular, package, runtime, citation, and changelog versions must match; the full test suite and distribution build must pass; and scientific evidence classifications must not be upgraded merely because software checks pass.
