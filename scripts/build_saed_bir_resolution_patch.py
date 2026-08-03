from __future__ import annotations

from pathlib import Path

ROOT = Path('.')
PARTS = ROOT / 'scripts' / '_patch_parts'


def concatenate(names: list[str], target: Path) -> None:
    text = '\n'.join(
        (PARTS / name).read_text(encoding='utf-8').rstrip('\n')
        for name in names
    ) + '\n'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding='utf-8')


concatenate(
    [f'saed_resolution_source_{index:02d}.txt' for index in range(4)],
    ROOT / 'src' / 'mca' / 'saed_bir_metadata_resolution.py',
)
concatenate(
    [f'saed_resolution_test_{index:02d}.txt' for index in range(2)],
    ROOT / 'tests' / 'test_saed_bir_metadata_resolution.py',
)

cli_path = ROOT / 'src' / 'mca' / 'cli_entry.py'
cli = cli_path.read_text(encoding='utf-8')
import_old = 'from .saed_bir_metadata_audit import cli_main as saed_bir_metadata_audit_main\n'
import_new = (
    import_old
    + 'from .saed_bir_metadata_resolution import '
    + 'cli_main as saed_bir_metadata_resolution_main\n'
)
if 'saed_bir_metadata_resolution_main' not in cli:
    if import_old not in cli:
        raise SystemExit('CLI import anchor not found')
    cli = cli.replace(import_old, import_new, 1)

dispatch_old = (
    '    if args and args[0] == "saed-bir-metadata-audit":\n'
    '        return saed_bir_metadata_audit_main(args[1:])\n'
)
dispatch_new = (
    dispatch_old
    + '    if args and args[0] == "saed-bir-metadata-resolution":\n'
    + '        return saed_bir_metadata_resolution_main(args[1:])\n'
)
if 'args[0] == "saed-bir-metadata-resolution"' not in cli:
    if dispatch_old not in cli:
        raise SystemExit('CLI dispatch anchor not found')
    cli = cli.replace(dispatch_old, dispatch_new, 1)

help_old = (
    '            "saed-bir-metadata-audit, saed-validation-intake, xps, ftir, thermal "\n'
)
help_new = (
    '            "saed-bir-metadata-audit, saed-bir-metadata-resolution, "\n'
    '            "saed-validation-intake, xps, ftir, thermal "\n'
)
if 'saed-bir-metadata-resolution, ' not in cli:
    if help_old not in cli:
        raise SystemExit('CLI help anchor not found')
    cli = cli.replace(help_old, help_new, 1)
cli_path.write_text(cli, encoding='utf-8')

case_dir = ROOT / 'case_studies' / 'saed_bir_metadata_resolution'
case_dir.mkdir(parents=True, exist_ok=True)
readme = """# BIR-MicroED 200 keV Metadata Resolution

This case converts the unresolved BIR-MicroED source gates into a strict,
machine-readable request and response contract. It consumes only the
checksum-bound output of `mca saed-bir-metadata-audit`.

## Generate the request package

```bash
mca saed-bir-metadata-resolution \
  --audit-output outputs/saed_bir_200kev_metadata_audit \
  --output outputs/saed_bir_metadata_resolution
```

The output includes a correspondence-ready Markdown request and a JSON response
template. The template requests authoritative representation, preprocessing,
member checksum, sample/acquisition lineage, centre, reciprocal calibration,
detector geometry, and analyzer-development non-use evidence.

## Assess a completed response

```bash
mca saed-bir-metadata-resolution \
  --audit-output outputs/saed_bir_200kev_metadata_audit \
  --response completed_author_response.json \
  --output outputs/saed_bir_author_response_assessment
```

A structurally valid unresolved or negative response is preserved as
`metadata_response_received_but_source_not_ready`. A complete positive response
reaches only `metadata_response_ready_for_bounded_download_verification` and
emits a draft `saed_validation_intake_handoff_template.json`.

## Scientific boundary

This command never downloads the archive, verifies member bytes, opens MRC
arrays, estimates a centre, infers calibration, runs the analyzer, or supports
crystallographic or engineering claims. Even a positive metadata response does
not set `archive_download_authorized`, `saed_validation_intake_ready`, or
`predeclared_external_evaluation_ready` to true. Synthetic positive fixtures
validate software behavior only.
"""
(case_dir / 'README.md').write_text(readme, encoding='utf-8')
