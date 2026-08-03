from __future__ import annotations

import json
from pathlib import Path

ROOT = Path('.')
AUDIT_SCRIPT = ROOT / 'scripts' / 'audit_co3o4_public_tem_candidates.py'
AUDIT_CONFIG = ROOT / 'case_studies' / 'co3o4_public_tem_candidate_audit' / 'case_config.json'
REGISTRY_CONFIG = ROOT / 'case_studies' / 'tem_external_validation_candidate_registry' / 'case_config.json'
REGISTRY_README = ROOT / 'case_studies' / 'tem_external_validation_candidate_registry' / 'README.md'
AUDIT_README = ROOT / 'case_studies' / 'co3o4_public_tem_candidate_audit' / 'README.md'
TESTS = ROOT / 'tests' / 'test_tem_external_validation_candidate_registry.py'


def replace_function(text: str, name: str, next_name: str, replacement: str) -> str:
    start = text.index(f'def {name}(')
    end = text.index(f'\ndef {next_name}(', start)
    return text[:start] + replacement.rstrip() + '\n\n' + text[end + 1:]


script = AUDIT_SCRIPT.read_text(encoding='utf-8')

mendeley_function = r'''
def _mendeley_inventory(config: dict[str, Any]) -> tuple[dict[str, Any], str]:
    expected = config["sources"]["mendeley_palygorskite_co3o4"]
    dataset_id = expected["dataset_id"]
    version = expected["version"]
    base = "https://data.mendeley.com/public-api"
    snapshot = _fetch_json(f"{base}/datasets/{dataset_id}/snapshot/{version}")
    if expected["doi"].casefold() not in json.dumps(snapshot).casefold():
        raise RuntimeError("Mendeley DOI mismatch")
    if not _contains_cc_by_4(snapshot):
        raise RuntimeError("Mendeley CC BY 4.0 licence not resolved")

    payload = _fetch_json(
        f"{base}/datasets/{dataset_id}/files?"
        + urllib.parse.urlencode({"folder_id": "root", "version": version}),
        "application/vnd.mendeley-public-dataset.1+json, application/json",
    )
    if isinstance(payload, dict):
        payload = payload.get("results") or payload.get("files") or payload.get("items") or []
    if not isinstance(payload, list):
        raise RuntimeError("Mendeley file response is not a list")

    observed_files: list[dict[str, Any]] = []
    for item in payload:
        content = item.get("content_details") or {}
        observed_files.append(
            {
                "file_id": item.get("id") or item.get("file_id"),
                "name": item.get("filename") or item.get("name") or "",
                "bytes": int(content.get("size", item.get("size", 0)) or 0),
                "sha256": (
                    content.get("sha256_hash")
                    or content.get("sha256")
                    or item.get("sha256_hash")
                    or item.get("sha256")
                    or ""
                ).casefold(),
                "last_modified_date": item.get("last_modified_date"),
            }
        )

    archive_name = expected["archive_name"]
    archive = next(
        (item for item in observed_files if item["name"] == archive_name),
        None,
    )
    if archive is None:
        raise RuntimeError("Mendeley archive missing")
    if not isinstance(archive["file_id"], str) or not archive["file_id"].strip():
        raise RuntimeError("Mendeley archive routing file_id missing")
    if archive["bytes"] <= 0:
        raise RuntimeError("Mendeley archive byte count must be positive")
    if re.fullmatch(r"[0-9a-f]{64}", archive["sha256"]) is None:
        raise RuntimeError("Mendeley archive SHA-256 is invalid")

    known_snapshots = expected.get("known_snapshots", [])
    matching_snapshot = next(
        (
            item
            for item in known_snapshots
            if item["name"] == archive["name"]
            and item["bytes"] == archive["bytes"]
            and item["sha256"] == archive["sha256"]
        ),
        None,
    )
    provenance = expected["provenance_policy"]
    identity_stable = (
        matching_snapshot is not None
        and not provenance["same_version_identity_drift_observed"]
    )
    endpoint = (
        "https://data.mendeley.com/public-files/datasets/"
        f"{dataset_id}/files/{archive['file_id']}/file_downloaded"
    )
    return (
        {
            "dataset_id": dataset_id,
            "version": version,
            "doi": expected["doi"],
            "title": snapshot.get("name") or snapshot.get("title"),
            "license_verified": True,
            "source_identity_basis": [
                "dataset_id",
                "version",
                "archive filename",
                "archive byte count",
                "archive SHA-256",
                "extracted representation",
            ],
            "observed_archive": archive,
            "known_snapshot_match": matching_snapshot is not None,
            "source_identity_stable_for_version": identity_stable,
            "same_version_identity_drift_observed": provenance[
                "same_version_identity_drift_observed"
            ],
            "observed_download_file_id": archive["file_id"],
            "file_id_used_only_for_download_routing": True,
            "files": observed_files,
        },
        endpoint,
    )
'''
script = replace_function(script, '_mendeley_inventory', '_inspect_archive', mendeley_function)

inspect_function = r'''
def _inspect_archive(
    archive_path: Path,
    extracted: Path,
    config: dict[str, Any],
) -> dict[str, Any]:
    expected = config["sources"]["mendeley_palygorskite_co3o4"]
    baseline = expected["known_wrong_modality_representation"]
    extracted.mkdir(parents=True, exist_ok=False)
    subprocess.run(
        ["unar", "-quiet", "-output-directory", str(extracted), str(archive_path)],
        check=True,
    )
    members = sorted(path for path in extracted.rglob("*") if path.is_file())
    relative = [path.relative_to(extracted).as_posix() for path in members]
    if any(name.startswith("/") or ".." in Path(name).parts for name in relative):
        raise RuntimeError("archive contains unsafe member paths")

    images: list[dict[str, Any]] = []
    for path in members:
        try:
            with Image.open(path) as image:
                images.append(
                    {
                        "path": path.relative_to(extracted).as_posix(),
                        "format": image.format,
                        "mode": image.mode,
                        "size": [image.width, image.height],
                        "frames": getattr(image, "n_frames", 1),
                    }
                )
        except Exception:
            continue

    tem_pattern = re.compile(r"(^|[/_. -])(hrtem|tem)([/_. -]|$)", re.IGNORECASE)
    stem_pattern = re.compile(r"(^|[/_. -])stem([/_. -]|$)", re.IGNORECASE)
    tem_paths = [name for name in relative if tem_pattern.search(name)]
    stem_paths = [name for name in relative if stem_pattern.search(name)]
    detector_suffixes = {".dm3", ".dm4", ".emd", ".ser", ".tif", ".tiff"}
    detector_members = [
        name for name in relative if Path(name).suffix.casefold() in detector_suffixes
    ]

    observed_paths = sorted(item["path"] for item in images)
    baseline_images_match = (
        observed_paths == sorted(baseline["image_members"])
        and all(item["format"] == baseline["image_format"] for item in images)
        and all(item["mode"] == baseline["image_mode"] for item in images)
        and all(item["size"] == baseline["image_size"] for item in images)
        and all(item["frames"] == 1 for item in images)
    )
    baseline_match = (
        len(members) == baseline["member_count"]
        and baseline_images_match
        and not tem_paths
        and not stem_paths
        and not detector_members
    )
    return {
        "archive_member_count": len(members),
        "suffix_counts": dict(
            sorted(Counter(Path(name).suffix.casefold() or "<none>" for name in relative).items())
        ),
        "decodable_image_count": len(images),
        "decodable_images": images,
        "tem_or_hrtem_member_count": len(tem_paths),
        "stem_member_count": len(stem_paths),
        "microscopy_detector_file_count": len(detector_members),
        "tem_or_stem_candidate_paths": sorted(set(tem_paths + stem_paths)),
        "microscopy_detector_members": detector_members,
        "known_wrong_modality_representation_match": baseline_match,
    }
'''
script = replace_function(script, '_inspect_archive', 'run', inspect_function)

run_function = r'''
def run(config_path: Path, output: Path) -> dict[str, Any]:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("output directory must be absent or empty")
    output.mkdir(parents=True, exist_ok=True)
    transient = output / "_transient"
    transient.mkdir()
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        zenodo = _zenodo_inventory(config)
        mendeley, endpoint = _mendeley_inventory(config)
        observed_archive = mendeley["observed_archive"]
        archive_path = transient / observed_archive["name"]
        _download(
            endpoint,
            archive_path,
            observed_archive["bytes"],
            observed_archive["sha256"],
        )
        representation = _inspect_archive(archive_path, transient / "extracted", config)
        candidate_tem_content = bool(
            representation["tem_or_hrtem_member_count"]
            or representation["stem_member_count"]
            or representation["microscopy_detector_file_count"]
        )
        if candidate_tem_content:
            result = "source_representation_changed_manual_review_required"
        elif (
            mendeley["source_identity_stable_for_version"]
            and representation["known_wrong_modality_representation_match"]
        ):
            result = "assessed_public_records_do_not_expose_tem_validation_arrays"
        else:
            result = "source_identity_changed_but_current_archive_remains_wrong_modality"

        inventory = {
            "schema_version": "1.0",
            "case_id": config["case_id"],
            "audit_date": config["audit_date"],
            "zenodo": zenodo,
            "mendeley": mendeley,
        }
        summary = {
            "schema_version": "1.0",
            "case_id": config["case_id"],
            "result": result,
            **representation,
            "mendeley_known_snapshot_match": mendeley["known_snapshot_match"],
            "mendeley_source_identity_stable_for_version": mendeley[
                "source_identity_stable_for_version"
            ],
            "mendeley_same_version_identity_drift_observed": mendeley[
                "same_version_identity_drift_observed"
            ],
            "mendeley_observed_archive_bytes": observed_archive["bytes"],
            "mendeley_observed_archive_sha256": observed_archive["sha256"],
            "source_binaries_retained": False,
            "model_inference_performed": False,
            "annotation_performed": False,
            "manual_review_required": candidate_tem_content,
            "external_validation_ready": False,
            "scientific_closeout": {
                "status": "Supported" if not candidate_tem_content else "Inconclusive",
                "strongest_evidence": (
                    "The Zenodo record exposes only one spreadsheet. The current Mendeley "
                    "archive was verified against its API-declared byte count and SHA-256, "
                    "then inspected after extraction."
                ),
                "primary_limitation": (
                    "The same Mendeley DOI/version has exhibited archive-identity drift, and "
                    "the audit establishes only what is present in the current public snapshot."
                ),
                "not_suitable_for": [
                    "TEM segmentation inference",
                    "model retraining",
                    "external performance claims",
                    "engineering release",
                ],
            },
        }
        (output / "official_source_inventory.json").write_text(
            json.dumps(inventory, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (output / "co3o4_public_tem_candidate_audit_summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return summary
    finally:
        shutil.rmtree(transient, ignore_errors=True)
'''
script = replace_function(script, 'run', '_verify_registry', run_function)

main_function = r'''
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--registry-output", type=Path)
    args = parser.parse_args()
    summary = run(args.config, args.output)
    if args.registry_output is not None:
        _verify_registry(args.registry_output)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 2 if summary["manual_review_required"] else 0
'''
script = replace_function(script, 'main', '__main__', main_function)
AUDIT_SCRIPT.write_text(script, encoding='utf-8')

config = json.loads(AUDIT_CONFIG.read_text(encoding='utf-8'))
mendeley = config['sources']['mendeley_palygorskite_co3o4']
mendeley.pop('archive', None)
mendeley['archive_name'] = 'Data.rar'
mendeley['known_snapshots'] = [
    {
        'observed_date': '2026-08-03',
        'name': 'Data.rar',
        'bytes': 16250421,
        'sha256': 'e3af684f7892877ee073e54e54a230d969d661193c807703a3b083fbdc4e42e9',
        'observed_file_id': '251b0061-cc22-48b4-bc3d-8bba56f8a030',
        'file_id_role': 'download_routing_only',
    }
]
mendeley['provenance_policy'] = {
    'same_version_identity_drift_observed': True,
    'file_id_is_download_routing_only': True,
    'current_api_declared_bytes_and_sha256_must_match_download': True,
    'identity_drift_blocks_external_validation': True,
}
mendeley['known_wrong_modality_representation'] = {
    'member_count': 760,
    'image_members': ['Data/SEM/2.png', 'Data/SEM/3.png', 'Data/SEM/4.png'],
    'image_format': 'PNG',
    'image_mode': 'I;16',
    'image_size': [1536, 1103],
}
for key in (
    'expected_member_count',
    'expected_image_members',
    'expected_image_format',
    'expected_image_mode',
    'expected_image_size',
):
    mendeley.pop(key, None)
AUDIT_CONFIG.write_text(json.dumps(config, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

registry = json.loads(REGISTRY_CONFIG.read_text(encoding='utf-8'))
candidate = next(
    item for item in registry['candidates']
    if item['candidate_id'] == 'mendeley_kkk76z8g8z_current_public_archive'
)
candidate['file_inventory_status'] = 'snapshot_exact_but_same_version_identity_unstable'
candidate['source_evidence'] = [
    'A checksum-bound version-1 snapshot of Data.rar was verified at 16250421 bytes with SHA-256 e3af684f7892877ee073e54e54a230d969d661193c807703a3b083fbdc4e42e9; the API file UUID is download-routing metadata only.',
    'Subsequent direct audits of the same DOI and version returned changed file UUID and SHA-256 values, so the public source does not currently provide stable immutable archive identity.',
    'The directly extracted known snapshot contained 760 members and only three decodable images: Data/SEM/2.png, Data/SEM/3.png, and Data/SEM/4.png. All were 1536 x 1103 16-bit PNG images, with no deposited TEM, HRTEM, STEM, DM3, DM4, EMD, SER, TIFF, or TIF source file.',
]
candidate['next_validation_step'] = (
    'Exclude from TEM segmentation validation. Reconsider only after an immutable repository '
    'release provides stable archive identity and checksum-bound TEM/HRTEM source files with '
    'sample/acquisition lineage and target-model non-use evidence.'
)
REGISTRY_CONFIG.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

for path in (AUDIT_README, REGISTRY_README):
    text = path.read_text(encoding='utf-8')
    if path == AUDIT_README:
        old = 'Mendeley file UUIDs are treated as mutable download-routing metadata, not scientific source identity. Reproducible source identity is bound to the versioned dataset, archive filename, byte count, SHA-256, and extracted representation.'
        new = (
            'Mendeley file UUIDs are treated as mutable download-routing metadata, not scientific '
            'source identity. Because repeated direct audits of the same DOI/version returned changed '
            'file UUID and SHA-256 values, the workflow verifies the current API-declared bytes and '
            'SHA-256 against the actual download, records identity drift as a blocker, and inspects the '
            'current representation without promoting it to an immutable validation source.'
        )
        text = text.replace(old, new)
        text = text.replace(
            'fails if the record, licence, archive filename, byte count, SHA-256, or extracted representation changes;',
            'fails on record/licence errors, verifies the current API-declared archive bytes and SHA-256, and records same-version identity drift;',
        )
    else:
        old = 'Mendeley file UUIDs are treated as mutable download-routing metadata; archive content identity is bound to filename, bytes, SHA-256, and extracted representation.'
        new = (
            'Mendeley file UUIDs are treated as mutable download-routing metadata. Repeated direct '
            'audits also observed SHA-256 drift for the same DOI/version, so stable source identity '
            'remains unresolved and independently blocks external validation.'
        )
        text = text.replace(old, new)
    path.write_text(text, encoding='utf-8')

tests = TESTS.read_text(encoding='utf-8')
tests = tests.replace(
    '    assert "download-routing metadata" in mendeley["source_evidence"]\n',
    '    assert "download-routing metadata" in mendeley["source_evidence"]\n'
    '    assert "changed file UUID and SHA-256" in mendeley["source_evidence"]\n'
    '    assert "stable immutable archive identity" in mendeley["source_evidence"]\n',
    1,
)
TESTS.write_text(tests, encoding='utf-8')
