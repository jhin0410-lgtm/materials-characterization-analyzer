# Release Checklist

Use this checklist before creating a GitHub tag, release, package archive, or externally circulated snapshot.

## 1. Scope and repository state

- Confirm the release contains one coherent scope and no unrelated refactoring.
- Confirm the intended branch is based on the latest `main`.
- Review every changed and deleted file.
- Confirm no credentials, private keys, unpublished measurements, proprietary exports, personal information, local paths, or generated outputs are included.
- Confirm all external datasets retain their original citation and license information.

## 2. Version and citation consistency

The same public version must appear in:

- `pyproject.toml` under `[project].version`;
- `src/mca/__init__.py` as `__version__`;
- `CITATION.cff` as `version`;
- `CHANGELOG.md` as a dated release heading.

Run:

```bash
mca --version
pytest -q tests/test_release_metadata.py
```

Do not create a release when these values differ.

## 3. Software validation

Run from a clean environment:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
pytest -q
python -m build
```

Windows PowerShell activation:

```powershell
.\.venv\Scripts\Activate.ps1
```

Confirm:

- all tests pass;
- both a wheel and source distribution are produced under `dist/`;
- the wheel installs successfully;
- `mca --version` reports the intended version after wheel installation;
- public APIs, CLI commands, filenames, and output schemas are unchanged unless the release explicitly documents a migration.

## 4. Scientific validation

Software validation does not establish scientific validity.

For every scientific workflow or case affected by the release, confirm:

- sample identity and source provenance are recorded;
- composition, processing history, acquisition conditions, units, calibration, and preprocessing are not invented;
- exclusions and transformations are explicit and reproducible;
- automatic candidates remain distinct from phase, compound, chemical-state, functional-group, reaction, or mechanism assignments;
- comparability claims are supported by sample and measurement metadata;
- the closeout is classified as `Supported`, `Diagnostic`, `Inconclusive`, or `Unsupported` with the primary limitation stated.

Synthetic data may validate deterministic software behavior only.

## 5. Public data and artifacts

- Do not commit downloaded raw case-study data when the workflow can retrieve it from the authoritative repository.
- Verify source identifiers and checksums before analysis.
- Confirm short-lived CI artifacts contain no secrets or restricted data.
- Keep local outputs under ignored directories.
- Record generated-artifact retention and deletion behavior.

## 6. Release notes

Release notes must include:

- version and date;
- user-facing additions, changes, fixes, and removals;
- compatibility or migration information;
- commands and validation results;
- known warnings and failures;
- scientific limitations and evidence level;
- external dataset citations and license boundaries when relevant.

## 7. Final closeout

Record:

- files changed;
- implementation summary;
- commands executed;
- test and build results;
- warnings and unresolved failures;
- scientific evidence level and primary limitation;
- final `git status` or equivalent repository state;
- tag/release identifier and generated-artifact handling.
