from __future__ import annotations

from pathlib import Path


def replace_exact(path: Path, old: str, new: str, expected_count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected_count:
        raise SystemExit(f"{path}: expected {expected_count} occurrences, found {count}: {old[:80]!r}")
    path.write_text(text.replace(old, new), encoding="utf-8")


def replace_between(path: Path, start_marker: str, end_marker: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    path.write_text(text[:start] + replacement + text[end:], encoding="utf-8")


contract = Path("src/mca/tem_external_validation_pilot_contract.py")
io = Path("src/mca/tem_external_validation_pilot_io.py")
engine = Path("src/mca/tem_external_validation_pilot_engine.py")
resolver = Path("scripts/resolve_dryad_pilot_file_metadata.py")
workflow = Path(".github/workflows/dryad-hrtem-pilot-pair-audit.yml")
config = Path("case_studies/dryad_hrtem_pilot_pair_audit/case_config.json")
tests = Path("tests/test_dryad_hrtem_pilot_pair_audit.py")
readme = Path("case_studies/dryad_hrtem_pilot_pair_audit/README.md")
changelog = Path("CHANGELOG.md")

replace_exact(
    contract,
    'SOURCE_DOI = "10.7941/D1SP93"\nPILOT_PAIR_ID = "au_5nm_260kx_450e"\n',
    'SOURCE_DOI = "10.7941/D1SP93"\nSOURCE_VERSION_ID = 247105\nPILOT_PAIR_ID = "au_5nm_260kx_450e"\n',
)
replace_exact(
    contract,
    '    license: str\n    api_file_endpoint_template: str\n',
    '    license: str\n    source_version_id: int\n    api_file_endpoint_template: str\n',
)
replace_exact(
    contract,
    '            license=_text(source, "license"),\n            api_file_endpoint_template=_text(source, "api_file_endpoint_template"),\n',
    '            license=_text(source, "license"),\n            source_version_id=int(source["source_version_id"]),\n            api_file_endpoint_template=_text(source, "api_file_endpoint_template"),\n',
)
replace_exact(
    contract,
    '        if self.labeler_count <= 0:\n            raise ValueError("labeler_count must be positive.")\n',
    '        if self.source_version_id <= 0:\n            raise ValueError("source_version_id must be positive.")\n        if self.labeler_count <= 0:\n            raise ValueError("labeler_count must be positive.")\n',
)

new_validate_public = '''def validate_public_config(config: PilotAuditConfig) -> None:
    expected = {
        "case_id": CASE_ID,
        "repository": "Dryad",
        "doi": SOURCE_DOI,
        "published_date": "2023-07-31",
        "version_label": "2023-07-31",
        "license": "CC0-1.0",
        "source_version_id": SOURCE_VERSION_ID,
        "api_file_endpoint_template": "https://datadryad.org/api/v2/files/{file_id}",
        "download_endpoint_template": "https://datadryad.org/api/v2/files/{file_id}/download",
        "pair_id": PILOT_PAIR_ID,
        "material": "Au",
        "particle_diameter_nm": 5.0,
        "magnification_kx": 260,
        "electron_dose_e_per_a2": 450.0,
        "substrate": "ultrathin C",
        "microscope": "TEAM 0.5 aberration-corrected transmission electron microscope",
        "camera": "OneView (Gatan)",
        "labeler_count": 1,
        "annotation_tool": "LabelBox",
        "image_file": RemoteFileSpec(
            2451485,
            "Au_5nm_260kx_450e_Std_UTC_FFCorr_Team05_Images.h5",
            184.55,
            "MB",
        ),
        "label_file": RemoteFileSpec(
            2451482,
            "Au_5nm_260kx_450e_Std_UTC_FFCorr_Team05_Labels.h5",
            92.28,
            "MB",
        ),
        "processed_metadata_file": RemoteFileSpec(
            2451515, "Processed_datasets_metadata.csv", 2.10, "KB"
        ),
        "hdf5": Hdf5Contract(
            image_dataset_name="images",
            label_dataset_name="labels",
            patch_height=512,
            patch_width=512,
            image_mean_abs_tolerance=0.00001,
            image_std_abs_tolerance=0.00001,
            allowed_label_values=(0, 1),
        ),
        "training": TrainingReference(
            repository="Zenodo",
            record_id=14927582,
            doi="10.5281/zenodo.14927582",
            dataset_version="v1",
            name="training_images.h5",
            url="https://zenodo.org/records/14927582/files/training_images.h5?download=1",
            md5="caac404a7ea2c65b2403aee5728a70eb",
            sha256="e709b7f1fa383bd111bb0b7e8d4662452b46198f52e4e88b19bb3f3e222c0926",
            dataset_name="images",
            shape=(256, 512, 512),
            candidate_parent_patch_count=64,
            candidate_parent_count=4,
        ),
        "overlap": OverlapContract(
            quantization_decimals=9,
            signature_block_size=16,
            review_ncc_threshold=0.995,
            exact_match_rule="quantized_per_patch_standardized_sha256",
        ),
        "notebook_repository": "ScottLabUCB/NN_training",
        "notebook_commit": "9f92235102a805abc76e3d60065d677ee2068c90",
        "notebook": "model training for HRTEM.ipynb",
        "notebook_blob_sha": "a21bf95fb41f63efb0c33b1563bc43a073afed58",
        "verified_training_input_name": "training_images.h5",
        "dryad_pilot_pair_named_as_training_input": False,
        "authoritative_cross_dataset_acquisition_lineage_manifest_available": False,
    }
    for field, value in expected.items():
        actual = getattr(config, field)
        if actual != value:
            raise ValueError(
                f"public config mismatch for {field}: {actual!r} != {value!r}"
            )


'''
replace_between(contract, "def validate_public_config", "def normalize_dryad_file_metadata", new_validate_public)

replace_exact(
    config,
    '    "license": "CC0-1.0",\n    "api_file_endpoint_template"',
    '    "license": "CC0-1.0",\n    "source_version_id": 247105,\n    "api_file_endpoint_template"',
)

replace_exact(io, "import urllib.error\nimport urllib.request\n", "import urllib.error\nimport urllib.parse\nimport urllib.request\n")

new_io_block = r'''def _request_headers(*, dryad_binary: bool = False) -> dict[str, str]:
    headers = {"User-Agent": "materials-characterization-analyzer/0.10"}
    if dryad_binary:
        token = os.environ.get("DRYAD_API_TOKEN", "").strip()
        if not token:
            raise RuntimeError(
                "DRYAD_API_TOKEN is required for automatic Dryad binary acquisition."
            )
        headers["Authorization"] = f"Bearer {token}"
        headers["Accept"] = "application/octet-stream"
    return headers


def _dryad_link(payload: Mapping[str, Any], base_url: str, *names: str) -> str | None:
    links = payload.get("_links")
    if not isinstance(links, Mapping):
        return None
    for name in names:
        value = links.get(name)
        href = value.get("href") if isinstance(value, Mapping) else value
        if isinstance(href, str) and href.strip():
            resolved = urllib.parse.urljoin(base_url, href.strip())
            if urllib.parse.urlsplit(resolved).netloc != "datadryad.org":
                raise ValueError(f"unexpected Dryad link host: {resolved}")
            return resolved
    return None


def _dryad_records(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    direct = payload.get("files")
    if isinstance(direct, list):
        return [item for item in direct if isinstance(item, Mapping)]
    embedded = payload.get("_embedded")
    if isinstance(embedded, Mapping):
        for key, value in embedded.items():
            if isinstance(value, list) and "file" in str(key).lower():
                return [item for item in value if isinstance(item, Mapping)]
    for key in ("data", "items", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, Mapping)]
    raise ValueError("Dryad source-version response does not contain a file list.")


def _normalize_doi(value: str) -> str:
    text = value.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if text.lower().startswith(prefix):
            text = text[len(prefix):]
            break
    return text.upper()


def _find_doi(value: Any) -> str | None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if "doi" in str(key).lower() and isinstance(item, str) and "10." in item:
                return item
        for item in value.values():
            found = _find_doi(item)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_doi(item)
            if found is not None:
                return found
    return None


def _source_version_context(
    config: PilotAuditConfig,
    individual_payload: Mapping[str, Any],
    api_url: str,
    cache: dict[str, Any],
) -> tuple[str, list[Mapping[str, Any]]]:
    version_url = _dryad_link(individual_payload, api_url, "stash:version", "version")
    if version_url is None:
        raise ValueError("Dryad individual-file response lacks a source-version link.")
    version_id = int(version_url.rstrip("/").rsplit("/", 1)[-1])
    if version_id != config.source_version_id:
        raise ValueError(
            f"Dryad source-version mismatch: {version_id} != {config.source_version_id}"
        )
    if version_url not in cache:
        version_payload = fetch_json(version_url)
        doi = _find_doi(version_payload)
        dataset_url = _dryad_link(version_payload, version_url, "stash:dataset", "dataset")
        if doi is None:
            if dataset_url is None:
                raise ValueError("Dryad source version lacks verifiable dataset DOI identity.")
            dataset_payload = fetch_json(dataset_url)
            doi = _find_doi(dataset_payload)
        if doi is None or _normalize_doi(doi) != _normalize_doi(config.doi):
            raise ValueError(f"Dryad dataset DOI mismatch for source version {version_id}.")
        files_url = _dryad_link(version_payload, version_url, "stash:files", "files")
        if files_url is None:
            files_url = version_url.rstrip("/") + "/files"
        records: list[Mapping[str, Any]] = []
        seen: set[str] = set()
        url: str | None = files_url
        while url is not None:
            if url in seen:
                raise ValueError(f"Dryad file pagination cycle detected at {url}")
            seen.add(url)
            page = fetch_json(url)
            records.extend(_dryad_records(page))
            url = _dryad_link(page, url, "next", "stash:next")
        if not records:
            raise ValueError("Dryad source-version file inventory is empty.")
        cache[version_url] = {
            "records": records,
            "files_url": files_url,
            "dataset_doi": config.doi,
        }
    context = cache[version_url]
    return version_url, list(context["records"])


def _record_name(record: Mapping[str, Any]) -> str | None:
    for key in ("path", "filename", "fileName", "name"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return Path(value).name
    return None


def _record_id(record: Mapping[str, Any]) -> int | None:
    value = record.get("id", record.get("fileId"))
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _record_digest(record: Mapping[str, Any]) -> Any:
    for key in ("digest", "checksum", "md5", "sha256"):
        if record.get(key) is not None:
            return record[key]
    return None


def _enrich_dryad_metadata(
    config: PilotAuditConfig,
    spec: RemoteFileSpec,
    raw_payload: Mapping[str, Any],
    api_url: str,
    cache: dict[str, Any],
) -> Mapping[str, Any]:
    version_url, records = _source_version_context(config, raw_payload, api_url, cache)
    matches = [
        record
        for record in records
        if _record_name(record) == spec.name
        and _record_id(record) in (None, spec.file_id)
    ]
    if len(matches) != 1:
        raise ValueError(
            f"expected one source-version record for {spec.name!r}; found {len(matches)}"
        )
    digest = _record_digest(matches[0])
    if digest is None:
        raise ValueError(f"source-version record lacks checksum for {spec.name}.")
    download_url = _dryad_link(
        raw_payload, api_url, "stash:download", "download"
    ) or config.download_endpoint_template.format(file_id=spec.file_id)
    enriched = dict(raw_payload)
    enriched.update(
        {
            "id": spec.file_id,
            "path": spec.name,
            "digest": digest,
            "source_version_id": config.source_version_id,
            "source_version_api_url": version_url,
            "source_version_file_record": dict(matches[0]),
            "dataset_doi": config.doi,
            "downloadUrl": download_url,
        }
    )
    return enriched


def _validate_enriched_identity(
    payload: Mapping[str, Any], config: PilotAuditConfig
) -> None:
    try:
        version_id = int(payload.get("source_version_id"))
    except (TypeError, ValueError) as exc:
        raise ValueError("Dryad metadata lacks pinned source_version_id.") from exc
    if version_id != config.source_version_id:
        raise ValueError(
            f"Dryad source-version mismatch: {version_id} != {config.source_version_id}"
        )
    doi = payload.get("dataset_doi")
    if not isinstance(doi, str) or _normalize_doi(doi) != _normalize_doi(config.doi):
        raise ValueError("Dryad metadata dataset DOI mismatch.")


def resolve_dryad_file(
    config: PilotAuditConfig,
    spec: RemoteFileSpec,
    *,
    local_path: str | Path | None,
    api_metadata_path: str | Path | None,
    temp: Path,
    source_version_cache: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], Path]:
    api_url = config.api_file_endpoint_template.format(file_id=spec.file_id)
    cache = source_version_cache if source_version_cache is not None else {}
    raw_payload = (
        json.loads(Path(api_metadata_path).read_text(encoding="utf-8"))
        if api_metadata_path is not None
        else fetch_json(api_url)
    )
    if not isinstance(raw_payload, Mapping):
        raise ValueError(f"Dryad API response for {spec.name} is not an object.")
    if api_metadata_path is None:
        resolved_payload = _enrich_dryad_metadata(
            config, spec, raw_payload, api_url, cache
        )
    else:
        resolved_payload = raw_payload
    _validate_enriched_identity(resolved_payload, config)
    fallback_url = config.download_endpoint_template.format(file_id=spec.file_id)
    metadata = normalize_dryad_file_metadata(resolved_payload, spec, fallback_url)
    metadata["api_url"] = api_url
    metadata["source_version_id"] = config.source_version_id
    metadata["dataset_doi"] = config.doi
    metadata["api_response_sha256"] = hashlib.sha256(
        json.dumps(resolved_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    if local_path is None:
        destination = temp / spec.name
        download(
            metadata["download_url"],
            destination,
            headers=_request_headers(dryad_binary=True),
        )
        acquisition_mode = "downloaded_from_api_resolved_url"
    else:
        destination = Path(local_path)
        if not destination.is_file():
            raise FileNotFoundError(destination)
        acquisition_mode = "user_supplied_local_file"

    actual = file_hashes(destination)
    if actual["bytes"] != metadata["size_bytes"]:
        raise ValueError(
            f"Dryad size mismatch for {spec.name}: {actual['bytes']} != "
            f"{metadata['size_bytes']}"
        )
    algorithm = str(metadata["digest_algorithm"])
    if algorithm not in actual:
        raise ValueError(f"unsupported calculated digest algorithm: {algorithm!r}.")
    if actual[algorithm] != metadata["digest"]:
        raise ValueError(
            f"Dryad {algorithm} mismatch for {spec.name}: {actual[algorithm]} != "
            f"{metadata['digest']}"
        )
    metadata.update(actual)
    metadata["source_digest_verified"] = True
    metadata["acquisition_mode"] = acquisition_mode
    return metadata, destination


'''
replace_between(io, "def resolve_dryad_file", "def acquire_training", new_io_block)

replace_between(
    io,
    "def fetch_json",
    "def file_hashes",
    r'''def fetch_json(
    url: str,
    attempts: int = 5,
    headers: Mapping[str, str] | None = None,
) -> Mapping[str, Any]:
    last_error: Exception | None = None
    request_headers = dict(headers or _request_headers())
    for attempt in range(attempts):
        request = urllib.request.Request(url, headers=request_headers)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, Mapping):
                raise ValueError("remote JSON response is not an object.")
            return payload
        except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(2**attempt)
    raise RuntimeError(f"failed to fetch JSON from {url}") from last_error


def download(
    url: str,
    destination: Path,
    attempts: int = 5,
    headers: Mapping[str, str] | None = None,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    last_error: Exception | None = None
    request_headers = dict(headers or _request_headers())
    for attempt in range(attempts):
        partial.unlink(missing_ok=True)
        request = urllib.request.Request(url, headers=request_headers)
        try:
            with urllib.request.urlopen(request, timeout=180) as response, partial.open("wb") as handle:
                shutil.copyfileobj(response, handle, length=1024 * 1024)
            os.replace(partial, destination)
            return
        except (OSError, urllib.error.URLError) as exc:
            last_error = exc
            partial.unlink(missing_ok=True)
            if attempt + 1 < attempts:
                time.sleep(2**attempt)
    raise RuntimeError(f"failed to download {url}") from last_error


''',
)

replace_exact(
    engine,
    '            image_meta, images_path = resolve_dryad_file(\n',
    '            source_version_cache: dict[str, Any] = {}\n            image_meta, images_path = resolve_dryad_file(\n',
)
replace_exact(
    engine,
    '                api_metadata_path=image_api_metadata_path,\n                temp=temp,\n            )\n',
    '                api_metadata_path=image_api_metadata_path,\n                temp=temp,\n                source_version_cache=source_version_cache,\n            )\n',
    expected_count=1,
)
replace_exact(
    engine,
    '                api_metadata_path=label_api_metadata_path,\n                temp=temp,\n            )\n',
    '                api_metadata_path=label_api_metadata_path,\n                temp=temp,\n                source_version_cache=source_version_cache,\n            )\n',
)
replace_exact(
    engine,
    '                api_metadata_path=processed_metadata_api_path,\n                temp=temp,\n            )\n',
    '                api_metadata_path=processed_metadata_api_path,\n                temp=temp,\n                source_version_cache=source_version_cache,\n            )\n',
)
replace_exact(
    engine,
    '        overlap_clear = not exact and not review\n        next_status = (\n            "eligible_to_freeze_diagnostic_cross_material_stress_test_protocol"\n            if overlap_clear\n            else "blocked_by_possible_cross_dataset_content_overlap"\n        )\n',
    '        overlap_clear = not exact and not review\n        binding_authoritative = binding["status"] == "exact_unique_row_binding"\n        data_audit_complete = binding_authoritative\n        if not binding_authoritative:\n            next_status = "blocked_unresolved_processed_metadata_binding"\n        elif not overlap_clear:\n            next_status = "blocked_by_possible_cross_dataset_content_overlap"\n        else:\n            next_status = (\n                "eligible_to_freeze_diagnostic_cross_material_stress_test_protocol"\n            )\n',
)
replace_exact(
    engine,
    '                "data_audit_complete": True,\n                "content_overlap_gate_passed": overlap_clear,\n',
    '                "data_audit_complete": data_audit_complete,\n                "processed_metadata_binding_authoritative": binding_authoritative,\n                "content_overlap_gate_passed": overlap_clear,\n',
)
replace_exact(
    engine,
    '                    "The pilot material is Au rather than cobalt oxide, labels were produced "\n                    "by one human, one creator overlaps, and authoritative cross-dataset "\n                    "acquisition-lineage exclusion is unavailable."\n',
    '                    "The pilot material is Au rather than cobalt oxide, labels were produced "\n                    "by one human, one creator overlaps, authoritative cross-dataset "\n                    "acquisition-lineage exclusion is unavailable, and protocol readiness "\n                    "also requires exact processed-metadata row binding."\n',
)

resolver.write_text(r'''#!/usr/bin/env python3
"""Enrich Dryad file metadata while preserving raw individual responses."""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Mapping

from mca.tem_external_validation_pilot_contract import SOURCE_DOI, SOURCE_VERSION_ID

BASE_URL = "https://datadryad.org"


def _fetch(url: str, attempts: int = 5) -> Mapping[str, Any]:
    last_error: Exception | None = None
    for attempt in range(attempts):
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "materials-characterization-analyzer/0.10"},
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, Mapping):
                raise ValueError("Dryad API response must be an object.")
            return payload
        except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(2**attempt)
    raise RuntimeError(f"failed to fetch {url}") from last_error


def _link(payload: Mapping[str, Any], base_url: str, *names: str) -> str | None:
    links = payload.get("_links")
    if not isinstance(links, Mapping):
        return None
    for name in names:
        value = links.get(name)
        href: Any = value.get("href") if isinstance(value, Mapping) else value
        if isinstance(href, str) and href.strip():
            resolved = urllib.parse.urljoin(base_url, href.strip())
            if urllib.parse.urlsplit(resolved).netloc != "datadryad.org":
                raise ValueError(f"unexpected Dryad link host: {resolved}")
            return resolved
    return None


def _records(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    direct = payload.get("files")
    if isinstance(direct, list):
        return [item for item in direct if isinstance(item, Mapping)]
    embedded = payload.get("_embedded")
    if isinstance(embedded, Mapping):
        for key, value in embedded.items():
            if isinstance(value, list) and "file" in str(key).lower():
                return [item for item in value if isinstance(item, Mapping)]
    for key in ("data", "items", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, Mapping)]
    raise ValueError("Dryad version files response does not contain a file list.")


def _file_pages(start_url: str) -> tuple[list[tuple[str, Mapping[str, Any]]], list[Mapping[str, Any]]]:
    pages: list[tuple[str, Mapping[str, Any]]] = []
    records: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    url: str | None = start_url
    while url is not None:
        if url in seen:
            raise ValueError(f"Dryad file pagination cycle detected at {url}")
        seen.add(url)
        payload = _fetch(url)
        pages.append((url, payload))
        records.extend(_records(payload))
        url = _link(payload, url, "next", "stash:next")
    if not records:
        raise ValueError("Dryad version file inventory is empty.")
    return pages, records


def _parse_file_binding(value: str) -> tuple[int, Path]:
    identifier, separator, path_text = value.partition("=")
    if not separator or not path_text:
        raise argparse.ArgumentTypeError("file bindings must use FILE_ID=PATH")
    try:
        file_id = int(identifier)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Dryad file ID must be an integer") from exc
    if file_id <= 0:
        raise argparse.ArgumentTypeError("Dryad file ID must be positive")
    return file_id, Path(path_text)


def _name(record: Mapping[str, Any]) -> str | None:
    for key in ("path", "filename", "fileName", "name"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return Path(value).name
    return None


def _digest(record: Mapping[str, Any]) -> Any:
    for key in ("digest", "checksum", "md5", "sha256"):
        if record.get(key) is not None:
            return record[key]
    return None


def _normalize_doi(value: str) -> str:
    text = value.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if text.lower().startswith(prefix):
            text = text[len(prefix):]
            break
    return text.upper()


def _find_doi(value: Any) -> str | None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if "doi" in str(key).lower() and isinstance(item, str) and "10." in item:
                return item
        for item in value.values():
            found = _find_doi(item)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_doi(item)
            if found is not None:
                return found
    return None


def _verify_dataset_identity(
    version_payload: Mapping[str, Any], version_url: str, doi: str
) -> Mapping[str, Any] | None:
    observed = _find_doi(version_payload)
    dataset_payload: Mapping[str, Any] | None = None
    if observed is None:
        dataset_url = _link(version_payload, version_url, "stash:dataset", "dataset")
        if dataset_url is None:
            raise ValueError("Dryad source version lacks verifiable dataset DOI identity.")
        dataset_payload = _fetch(dataset_url)
        observed = _find_doi(dataset_payload)
    if observed is None or _normalize_doi(observed) != _normalize_doi(doi):
        raise ValueError(f"Dryad dataset DOI mismatch: {observed!r} != {doi!r}")
    return dataset_payload


def resolve(
    doi: str,
    expected_version_id: int,
    bindings: Iterable[tuple[int, Path]],
    output_dir: Path,
) -> None:
    if _normalize_doi(doi) != _normalize_doi(SOURCE_DOI):
        raise ValueError(f"unexpected Dryad DOI: {doi!r}")
    if expected_version_id != SOURCE_VERSION_ID:
        raise ValueError(
            f"unexpected Dryad source version: {expected_version_id} != {SOURCE_VERSION_ID}"
        )
    source_bindings = list(bindings)
    payloads = [json.loads(path.read_text(encoding="utf-8")) for _, path in source_bindings]
    if not all(isinstance(payload, Mapping) for payload in payloads):
        raise ValueError("all individual-file responses must be objects.")

    version_urls = {
        _link(payload, f"{BASE_URL}/api/v2/files/{file_id}", "stash:version", "version")
        for (file_id, _), payload in zip(source_bindings, payloads)
    }
    if None in version_urls or len(version_urls) != 1:
        raise ValueError(f"pilot files do not resolve to one source version: {version_urls}")
    version_url = next(iter(version_urls))
    version_id = int(version_url.rstrip("/").rsplit("/", 1)[-1])
    if version_id != expected_version_id:
        raise ValueError(
            f"Dryad source-version mismatch: {version_id} != {expected_version_id}"
        )
    version_payload = _fetch(version_url)
    dataset_payload = _verify_dataset_identity(version_payload, version_url, doi)
    files_url = _link(version_payload, version_url, "stash:files", "files")
    if files_url is None:
        files_url = version_url.rstrip("/") + "/files"
    pages, records = _file_pages(files_url)

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "dryad-source-version-api.json").write_text(
        json.dumps(version_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if dataset_payload is not None:
        (output_dir / "dryad-source-dataset-api.json").write_text(
            json.dumps(dataset_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    for index, (url, payload) in enumerate(pages, start=1):
        (output_dir / f"dryad-source-version-files-page-{index:03d}.json").write_text(
            json.dumps({"request_url": url, "response": payload}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    (output_dir / "dryad-source-version-files-inventory.json").write_text(
        json.dumps(
            {"version_id": version_id, "dataset_doi": doi, "page_count": len(pages), "file_record_count": len(records), "records": records},
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )

    for (expected_id, path), payload in zip(source_bindings, payloads):
        expected_name = _name(payload)
        if expected_name is None:
            raise ValueError(f"individual Dryad response has no filename: {path}")
        matches = [record for record in records if _name(record) == expected_name]
        if len(matches) != 1:
            raise ValueError(
                f"expected one source-version record for {expected_name!r}; found {len(matches)}"
            )
        digest = _digest(matches[0])
        if digest is None:
            raise ValueError(f"source-version record lacks checksum for {expected_name}.")
        download_url = _link(
            payload,
            f"{BASE_URL}/api/v2/files/{expected_id}",
            "stash:download",
            "download",
        )
        if download_url is None:
            raise ValueError(f"individual Dryad response lacks download link for {expected_name}.")
        enriched = dict(payload)
        enriched.update(
            {
                "id": expected_id,
                "digest": digest,
                "source_version_id": version_id,
                "source_version_api_url": version_url,
                "source_version_files_api_url": files_url,
                "source_version_files_page_count": len(pages),
                "downloadUrl": download_url,
                "endpoint_file_id_source": "workflow_pinned_request_path",
                "source_version_file_record": dict(matches[0]),
                "dataset_doi": doi,
            }
        )
        destination = output_dir / f"dryad-file-{expected_id}-enriched.json"
        destination.write_text(
            json.dumps(enriched, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({"file_id": expected_id, "name": expected_name, "source_version_id": version_id, "digest": digest, "download_url": download_url, "enriched_path": str(destination)}))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--doi", default=SOURCE_DOI)
    parser.add_argument("--expected-version-id", type=int, default=SOURCE_VERSION_ID)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("files", nargs="+", type=_parse_file_binding)
    args = parser.parse_args()
    resolve(args.doi, args.expected_version_id, args.files, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''', encoding="utf-8")

replace_exact(
    workflow,
    '      - "src/mca/tem_external_validation_pilot_contract.py"\n      - "src/mca/tem_external_validation_pilot_audit.py"\n      - "tests/test_dryad_hrtem_pilot_pair_audit.py"\n',
    '      - "src/mca/tem_external_validation_pilot_contract.py"\n      - "src/mca/tem_external_validation_pilot_engine.py"\n      - "src/mca/tem_external_validation_pilot_io.py"\n      - "src/mca/tem_external_validation_pilot_audit.py"\n      - "tests/test_dryad_hrtem_pilot_pair_audit.py"\n      - "tests/test_dryad_hrtem_pilot_standardization_scope.py"\n      - "tests/test_resolve_dryad_pilot_file_metadata.py"\n',
    expected_count=2,
)
replace_exact(
    workflow,
    '          mkdir -p outputs/dryad-api-responses\n',
    '          mkdir -p outputs/dryad-api-responses/raw\n',
)
replace_exact(
    workflow,
    '          python scripts/resolve_dryad_pilot_file_metadata.py \\\n            --doi "10.7941/D1SP93" \\\n            --output-dir outputs/dryad-source-version-metadata \\\n',
    '          cp /tmp/dryad-*-api.json outputs/dryad-api-responses/raw/\n          python scripts/resolve_dryad_pilot_file_metadata.py \\\n            --doi "10.7941/D1SP93" \\\n            --expected-version-id 247105 \\\n            --output-dir outputs/dryad-source-version-metadata \\\n',
)
replace_exact(
    workflow,
    '            2451515=/tmp/dryad-metadata-api.json\n          cp /tmp/dryad-*-api.json outputs/dryad-api-responses/\n',
    '            2451515=/tmp/dryad-metadata-api.json\n',
)
replace_between(
    workflow,
    '      - name: Record acquisition readiness\n',
    '      - name: Download exact Dryad pilot files\n',
    '''      - name: Record acquisition readiness
        id: acquisition
        run: |
          set -euo pipefail
          mkdir -p outputs
          if [[ -n "${DRYAD_API_TOKEN:-}" ]]; then
            status="credential_configured_not_yet_verified"
            credential_configured=true
            can_attempt=true
          else
            status="blocked_missing_dryad_api_token"
            credential_configured=false
            can_attempt=false
          fi
          python - "$status" "$credential_configured" <<'PY'
          import json
          import sys
          from pathlib import Path

          status = sys.argv[1]
          credential_configured = sys.argv[2].lower() == "true"
          payload = {
              "schema_version": "1.0",
              "case_id": "dryad_hrtem_pilot_pair_audit",
              "status": status,
              "credential_configured": credential_configured,
              "authenticated_real_data_download_available": False,
              "live_metadata_and_source_version_verified": True,
              "real_hdf5_audit_performed": False,
              "real_content_overlap_audit_performed": False,
              "required_repository_secret": "DRYAD_API_TOKEN",
              "scientific_interpretation": (
                  "External acquisition credential is absent; no real HDF5 or scientific "
                  "validation result may be claimed."
                  if not credential_configured
                  else "A credential is configured but has not yet been authenticated by a successful binary download."
              ),
          }
          Path("outputs/dryad-acquisition-readiness.json").write_text(
              json.dumps(payload, indent=2, sort_keys=True) + "\\n",
              encoding="utf-8",
          )
          PY
          echo "can_attempt=$can_attempt" >> "$GITHUB_OUTPUT"

''',
)
replace_exact(
    workflow,
    "if: steps.acquisition.outputs.can_download == 'true'",
    "if: steps.acquisition.outputs.can_attempt == 'true'",
    expected_count=4,
)
replace_exact(
    workflow,
    '          download 2451482 /tmp/Au_5nm_260kx_450e_Std_UTC_FFCorr_Team05_Labels.h5\n',
    '''          download 2451482 /tmp/Au_5nm_260kx_450e_Std_UTC_FFCorr_Team05_Labels.h5
          python - <<'PY'
          import json
          from pathlib import Path
          path = Path("outputs/dryad-acquisition-readiness.json")
          payload = json.loads(path.read_text())
          payload["status"] = "authenticated_download_verified"
          payload["authenticated_real_data_download_available"] = True
          payload["scientific_interpretation"] = (
              "The configured credential was verified by successful authenticated downloads; real-data audit steps follow."
          )
          path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\\n")
          PY
''',
)
replace_exact(
    workflow,
    '            --images-api-metadata /tmp/dryad-images-api.json \\\n            --labels-api-metadata /tmp/dryad-labels-api.json \\\n            --processed-metadata-api /tmp/dryad-metadata-api.json \\\n',
    '            --images-api-metadata outputs/dryad-source-version-metadata/dryad-file-2451485-enriched.json \\\n            --labels-api-metadata outputs/dryad-source-version-metadata/dryad-file-2451482-enriched.json \\\n            --processed-metadata-api outputs/dryad-source-version-metadata/dryad-file-2451515-enriched.json \\\n',
)

replace_exact(
    tests,
    '                "digest": f"{algorithm}:{digest}",\n                "_links": {\n',
    '                "digest": f"{algorithm}:{digest}",\n                "source_version_id": 247105,\n                "dataset_doi": "10.7941/D1SP93",\n                "_links": {\n',
)
replace_exact(
    tests,
    'from mca.tem_external_validation_pilot_contract import (\n    load_config,\n',
    'from mca.tem_external_validation_pilot_contract import (\n    Hdf5Contract,\n    OverlapContract,\n    load_config,\n',
)
replace_exact(
    tests,
    'from mca.tem_external_validation_pilot_audit import run_pilot_pair_audit\n',
    'from mca.tem_external_validation_pilot_audit import run_pilot_pair_audit\nfrom mca.tem_external_validation_pilot_io import resolve_dryad_file\n',
)
append_tests = r'''


def test_public_contract_rejects_scientific_contract_drift() -> None:
    base = load_config(CONFIG)
    with pytest.raises(ValueError, match="public config mismatch for hdf5"):
        validate_public_config(
            replace(
                base,
                hdf5=Hdf5Contract(
                    image_dataset_name=base.hdf5.image_dataset_name,
                    label_dataset_name=base.hdf5.label_dataset_name,
                    patch_height=base.hdf5.patch_height,
                    patch_width=base.hdf5.patch_width,
                    image_mean_abs_tolerance=base.hdf5.image_mean_abs_tolerance,
                    image_std_abs_tolerance=base.hdf5.image_std_abs_tolerance,
                    allowed_label_values=(0, 1, 2),
                ),
            )
        )
    with pytest.raises(ValueError, match="public config mismatch for overlap"):
        validate_public_config(
            replace(
                base,
                overlap=OverlapContract(
                    quantization_decimals=base.overlap.quantization_decimals,
                    signature_block_size=base.overlap.signature_block_size,
                    review_ncc_threshold=0.90,
                    exact_match_rule=base.overlap.exact_match_rule,
                ),
            )
        )
    with pytest.raises(ValueError, match="public config mismatch for training"):
        validate_public_config(
            replace(base, training=replace(base.training, sha256="0" * 64))
        )
    with pytest.raises(ValueError, match="public config mismatch for notebook_commit"):
        validate_public_config(replace(base, notebook_commit="0" * 40))


def test_non_authoritative_processed_metadata_binding_blocks_protocol_freeze(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    config = fixture["config"]
    fixture["metadata"].write_text(
        "dataset,material\n"
        f"{config.image_file.name.removesuffix('_Images.h5')},Au\n",
        encoding="utf-8",
    )
    fixture["metadata_api"] = _api(
        fixture["metadata"],
        config.processed_metadata_file.file_id,
        config.processed_metadata_file.name,
    )
    summary = _run(tmp_path, fixture)
    assert summary["source"]["processed_metadata_binding"]["status"] == (
        "unique_prefix_candidate_not_authoritative"
    )
    assert not summary["readiness"]["data_audit_complete"]
    assert not summary["readiness"]["processed_metadata_binding_authoritative"]
    assert summary["readiness"]["next_status"] == (
        "blocked_unresolved_processed_metadata_binding"
    )


def test_automatic_resolution_follows_pinned_version_and_sends_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = load_config(CONFIG)
    payload_path = tmp_path / config.processed_metadata_file.name
    payload_path.write_text("x\n", encoding="utf-8")
    digest = hashlib.sha256(payload_path.read_bytes()).hexdigest()
    api_url = config.api_file_endpoint_template.format(
        file_id=config.processed_metadata_file.file_id
    )
    version_url = f"https://datadryad.org/api/v2/versions/{config.source_version_id}"
    files_url = version_url + "/files"
    individual = {
        "id": config.processed_metadata_file.file_id,
        "path": config.processed_metadata_file.name,
        "size": payload_path.stat().st_size,
        "_links": {
            "stash:version": {"href": version_url},
            "stash:download": {"href": api_url + "/download"},
        },
    }
    version = {
        "doi": config.doi,
        "_links": {"stash:files": {"href": files_url}},
    }
    files = {
        "files": [
            {
                "id": config.processed_metadata_file.file_id,
                "path": config.processed_metadata_file.name,
                "size": payload_path.stat().st_size,
                "digest": f"sha256:{digest}",
            }
        ]
    }
    responses = {api_url: individual, version_url: version, files_url: files}
    monkeypatch.setattr(
        "mca.tem_external_validation_pilot_io.fetch_json",
        lambda url, attempts=5, headers=None: responses[url],
    )
    captured: dict[str, str] = {}

    def fake_download(url, destination, attempts=5, headers=None):
        captured.update(dict(headers or {}))
        destination.write_bytes(payload_path.read_bytes())

    monkeypatch.setattr(
        "mca.tem_external_validation_pilot_io.download", fake_download
    )
    monkeypatch.setenv("DRYAD_API_TOKEN", "test-token")
    metadata, resolved = resolve_dryad_file(
        config,
        config.processed_metadata_file,
        local_path=None,
        api_metadata_path=None,
        temp=tmp_path / "download",
        source_version_cache={},
    )
    assert resolved.is_file()
    assert metadata["source_version_id"] == 247105
    assert metadata["dataset_doi"] == config.doi
    assert metadata["source_digest_verified"]
    assert captured["Authorization"] == "Bearer test-token"


def test_automatic_download_requires_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = load_config(CONFIG)
    api_url = config.api_file_endpoint_template.format(file_id=config.image_file.file_id)
    version_url = f"https://datadryad.org/api/v2/versions/{config.source_version_id}"
    files_url = version_url + "/files"
    responses = {
        api_url: {
            "id": config.image_file.file_id,
            "path": config.image_file.name,
            "size": 1,
            "_links": {
                "stash:version": {"href": version_url},
                "stash:download": {"href": api_url + "/download"},
            },
        },
        version_url: {"doi": config.doi, "_links": {"stash:files": {"href": files_url}}},
        files_url: {
            "files": [
                {
                    "id": config.image_file.file_id,
                    "path": config.image_file.name,
                    "size": 1,
                    "digest": "sha256:" + hashlib.sha256(b"x").hexdigest(),
                }
            ]
        },
    }
    monkeypatch.setattr(
        "mca.tem_external_validation_pilot_io.fetch_json",
        lambda url, attempts=5, headers=None: responses[url],
    )
    monkeypatch.delenv("DRYAD_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="DRYAD_API_TOKEN is required"):
        resolve_dryad_file(
            config,
            config.image_file,
            local_path=None,
            api_metadata_path=None,
            temp=tmp_path / "download",
            source_version_cache={},
        )
'''
text = tests.read_text(encoding="utf-8")
if "test_public_contract_rejects_scientific_contract_drift" in text:
    raise SystemExit("Dryad pilot tests already patched")
tests.write_text(text + append_tests, encoding="utf-8")

resolver_tests = Path("tests/test_resolve_dryad_pilot_file_metadata.py")
resolver_tests.write_text(r'''from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path("scripts/resolve_dryad_pilot_file_metadata.py")


def _module():
    spec = importlib.util.spec_from_file_location("resolve_dryad", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _raw(path: Path, file_id: int, name: str, version_id: int = 247105) -> Path:
    payload = {
        "id": file_id,
        "path": name,
        "size": 3,
        "_links": {
            "stash:version": {"href": f"https://datadryad.org/api/v2/versions/{version_id}"},
            "stash:download": {"href": f"https://datadryad.org/api/v2/files/{file_id}/download"},
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_resolver_preserves_raw_responses_and_writes_separate_enriched_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    bindings = [
        (2451485, _raw(tmp_path / "image.json", 2451485, "image.h5")),
        (2451482, _raw(tmp_path / "label.json", 2451482, "label.h5")),
        (2451515, _raw(tmp_path / "metadata.json", 2451515, "metadata.csv")),
    ]
    originals = {path: path.read_bytes() for _, path in bindings}
    version_url = "https://datadryad.org/api/v2/versions/247105"
    files_url = version_url + "/files"
    records = [
        {"id": file_id, "path": json.loads(path.read_text())["path"], "digest": "sha256:" + str(file_id).zfill(64)[-64:], "size": 3}
        for file_id, path in bindings
    ]
    responses = {
        version_url: {"doi": "10.7941/D1SP93", "_links": {"stash:files": {"href": files_url}}},
        files_url: {"files": records},
    }
    monkeypatch.setattr(module, "_fetch", lambda url, attempts=5: responses[url])
    output = tmp_path / "out"
    module.resolve("10.7941/D1SP93", 247105, bindings, output)
    for path, payload in originals.items():
        assert path.read_bytes() == payload
    for file_id, _ in bindings:
        enriched = json.loads((output / f"dryad-file-{file_id}-enriched.json").read_text())
        assert enriched["source_version_id"] == 247105
        assert enriched["dataset_doi"] == "10.7941/D1SP93"


def test_resolver_rejects_wrong_source_version_before_inventory_fetch(tmp_path: Path) -> None:
    module = _module()
    binding = (2451485, _raw(tmp_path / "image.json", 2451485, "image.h5", 999999))
    with pytest.raises(ValueError, match="source-version mismatch"):
        module.resolve("10.7941/D1SP93", 247105, [binding], tmp_path / "out")


def test_resolver_rejects_wrong_dataset_doi(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    binding = (2451485, _raw(tmp_path / "image.json", 2451485, "image.h5"))
    version_url = "https://datadryad.org/api/v2/versions/247105"
    monkeypatch.setattr(module, "_fetch", lambda url, attempts=5: {"doi": "10.0000/WRONG"})
    with pytest.raises(ValueError, match="dataset DOI mismatch"):
        module.resolve("10.7941/D1SP93", 247105, [binding], tmp_path / "out")
''', encoding="utf-8")

replace_exact(
    readme,
    'Missing, unsupported, or mismatched checksums fail closed. Raw API and source-version responses are preserved as workflow evidence.\n',
    'Missing, unsupported, or mismatched checksums fail closed. Raw individual-file API responses are copied before enrichment, enriched records are written to separate files, and source version `247105` plus dataset DOI `10.7941/D1SP93` are verified before their checksums are used.\n',
)
replace_exact(
    readme,
    '- with `DRYAD_API_TOKEN`, it downloads the exact files and runs the real HDF5 and content-overlap audit.\n',
    '- with `DRYAD_API_TOKEN`, the workflow first records only that a credential is configured, marks authenticated download availability true only after all three binary downloads succeed, and then runs the real HDF5 and content-overlap audit.\n',
)
replace_exact(
    readme,
    'A completed authenticated data audit may permit freezing a protocol for a diagnostic Au-to-cobalt cross-material stress test.',
    'A completed authenticated data audit may permit freezing a protocol for a diagnostic Au-to-cobalt cross-material stress test only when the processed metadata row is bound exactly and uniquely.',
)

replace_exact(
    changelog,
    '### Fixed\n\n',
    '### Fixed\n\n- Dryad HRTEM pilot automatic acquisition now resolves the pinned file-linked source version and checksum inventory, authenticates binary downloads without exposing the token, preserves raw API responses separately from enriched evidence, and keeps readiness blocked unless processed metadata binding is exact and authoritative.\n- The public Dryad pilot contract now pins the HDF5, training, overlap, notebook, source-version, and endpoint configuration; workflow evidence distinguishes a configured credential from a successfully verified authenticated download.\n',
)

print("Applied Dryad HRTEM pilot review fixes")
