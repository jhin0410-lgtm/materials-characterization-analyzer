"""Typed contract for the Dryad HRTEM pilot-pair audit."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

CASE_ID = "dryad_hrtem_pilot_pair_audit"
SOURCE_DOI = "10.7941/D1SP93"
PILOT_PAIR_ID = "au_5nm_260kx_450e"
_SUPPORTED_DIGEST_LENGTHS = {"md5": 32, "sha256": 64}


@dataclass(frozen=True)
class RemoteFileSpec:
    file_id: int
    name: str
    landing_page_size: float
    landing_page_size_unit: str


@dataclass(frozen=True)
class Hdf5Contract:
    image_dataset_name: str
    label_dataset_name: str
    patch_height: int
    patch_width: int
    image_mean_abs_tolerance: float
    image_std_abs_tolerance: float
    allowed_label_values: tuple[int, ...]


@dataclass(frozen=True)
class TrainingReference:
    repository: str
    record_id: int
    doi: str
    dataset_version: str
    name: str
    url: str
    md5: str
    sha256: str
    dataset_name: str
    shape: tuple[int, int, int]
    candidate_parent_patch_count: int
    candidate_parent_count: int


@dataclass(frozen=True)
class OverlapContract:
    quantization_decimals: int
    signature_block_size: int
    review_ncc_threshold: float
    exact_match_rule: str


@dataclass(frozen=True)
class PilotAuditConfig:
    case_id: str
    repository: str
    doi: str
    published_date: str
    version_label: str
    license: str
    api_file_endpoint_template: str
    download_endpoint_template: str
    pair_id: str
    material: str
    particle_diameter_nm: float
    magnification_kx: int
    electron_dose_e_per_a2: float
    substrate: str
    microscope: str
    camera: str
    labeler_count: int
    annotation_tool: str
    image_file: RemoteFileSpec
    label_file: RemoteFileSpec
    processed_metadata_file: RemoteFileSpec
    hdf5: Hdf5Contract
    training: TrainingReference
    overlap: OverlapContract
    notebook_repository: str
    notebook_commit: str
    notebook: str
    notebook_blob_sha: str
    verified_training_input_name: str
    dryad_pilot_pair_named_as_training_input: bool
    authoritative_cross_dataset_acquisition_lineage_manifest_available: bool

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "PilotAuditConfig":
        _reject_unknown(
            payload,
            {
                "case_id",
                "source",
                "pilot_pair",
                "hdf5_contract",
                "cobalt_training_reference",
                "overlap_contract",
                "target_model_provenance",
            },
            "config",
        )
        source = _mapping(payload, "source")
        pair = _mapping(payload, "pilot_pair")
        hdf5 = _mapping(payload, "hdf5_contract")
        training = _mapping(payload, "cobalt_training_reference")
        overlap = _mapping(payload, "overlap_contract")
        provenance = _mapping(payload, "target_model_provenance")
        config = cls(
            case_id=_text(payload, "case_id"),
            repository=_text(source, "repository"),
            doi=_text(source, "doi"),
            published_date=_text(source, "published_date"),
            version_label=_text(source, "version_label"),
            license=_text(source, "license"),
            api_file_endpoint_template=_text(source, "api_file_endpoint_template"),
            download_endpoint_template=_text(source, "download_endpoint_template"),
            pair_id=_text(pair, "pair_id"),
            material=_text(pair, "material"),
            particle_diameter_nm=float(pair["particle_diameter_nm"]),
            magnification_kx=int(pair["magnification_kx"]),
            electron_dose_e_per_a2=float(pair["electron_dose_e_per_a2"]),
            substrate=_text(pair, "substrate"),
            microscope=_text(pair, "microscope"),
            camera=_text(pair, "camera"),
            labeler_count=int(pair["labeler_count"]),
            annotation_tool=_text(pair, "annotation_tool"),
            image_file=_remote_file(
                _mapping(pair, "image_file"), "landing_page_size_mb", "MB"
            ),
            label_file=_remote_file(
                _mapping(pair, "label_file"), "landing_page_size_mb", "MB"
            ),
            processed_metadata_file=_remote_file(
                _mapping(pair, "processed_metadata_file"),
                "landing_page_size_kb",
                "KB",
            ),
            hdf5=Hdf5Contract(
                image_dataset_name=_text(hdf5, "image_dataset_name"),
                label_dataset_name=_text(hdf5, "label_dataset_name"),
                patch_height=int(hdf5["patch_height"]),
                patch_width=int(hdf5["patch_width"]),
                image_mean_abs_tolerance=float(hdf5["image_mean_abs_tolerance"]),
                image_std_abs_tolerance=float(hdf5["image_std_abs_tolerance"]),
                allowed_label_values=tuple(
                    int(value) for value in hdf5["allowed_label_values"]
                ),
            ),
            training=TrainingReference(
                repository=_text(training, "repository"),
                record_id=int(training["record_id"]),
                doi=_text(training, "doi"),
                dataset_version=_text(training, "dataset_version"),
                name=_text(training, "name"),
                url=_text(training, "url"),
                md5=_text(training, "md5"),
                sha256=_text(training, "sha256"),
                dataset_name=_text(training, "dataset_name"),
                shape=_int_tuple(training, "shape", 3),
                candidate_parent_patch_count=int(
                    training["candidate_parent_patch_count"]
                ),
                candidate_parent_count=int(training["candidate_parent_count"]),
            ),
            overlap=OverlapContract(
                quantization_decimals=int(overlap["quantization_decimals"]),
                signature_block_size=int(overlap["signature_block_size"]),
                review_ncc_threshold=float(overlap["review_ncc_threshold"]),
                exact_match_rule=_text(overlap, "exact_match_rule"),
            ),
            notebook_repository=_text(provenance, "repository"),
            notebook_commit=_text(provenance, "commit"),
            notebook=_text(provenance, "notebook"),
            notebook_blob_sha=_text(provenance, "notebook_blob_sha"),
            verified_training_input_name=_text(
                provenance, "verified_training_input_name"
            ),
            dryad_pilot_pair_named_as_training_input=_boolean(
                provenance, "dryad_pilot_pair_named_as_training_input"
            ),
            authoritative_cross_dataset_acquisition_lineage_manifest_available=_boolean(
                provenance,
                "authoritative_cross_dataset_acquisition_lineage_manifest_available",
            ),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if not re.fullmatch(r"[a-z0-9_]+", self.case_id):
            raise ValueError(
                "case_id must contain lowercase letters, digits, and underscores."
            )
        for template, label in (
            (self.api_file_endpoint_template, "api_file_endpoint_template"),
            (self.download_endpoint_template, "download_endpoint_template"),
        ):
            if template.count("{file_id}") != 1 or not template.startswith("https://"):
                raise ValueError(f"invalid {label}.")
        if self.labeler_count <= 0:
            raise ValueError("labeler_count must be positive.")
        if self.hdf5.patch_height <= 0 or self.hdf5.patch_width <= 0:
            raise ValueError("patch dimensions must be positive.")
        block = self.overlap.signature_block_size
        if block <= 0:
            raise ValueError("signature_block_size must be positive.")
        if self.hdf5.patch_height % block or self.hdf5.patch_width % block:
            raise ValueError("patch dimensions must be divisible by signature_block_size.")
        if not 0 < self.overlap.review_ncc_threshold <= 1:
            raise ValueError("review_ncc_threshold must be in (0, 1].")
        if not self.hdf5.allowed_label_values:
            raise ValueError("allowed_label_values cannot be empty.")
        specs = (self.image_file, self.label_file, self.processed_metadata_file)
        if any(spec.file_id <= 0 or spec.landing_page_size <= 0 for spec in specs):
            raise ValueError("Dryad file IDs and reported sizes must be positive.")
        if len({spec.file_id for spec in specs}) != len(specs):
            raise ValueError("Dryad file IDs must be distinct.")
        expected_training_rows = (
            self.training.candidate_parent_patch_count
            * self.training.candidate_parent_count
        )
        if self.training.shape[0] != expected_training_rows:
            raise ValueError(
                "training shape is inconsistent with candidate parent grouping."
            )
        for value, label, length in (
            (self.training.md5, "training md5", 32),
            (self.training.sha256, "training sha256", 64),
            (self.notebook_commit, "notebook commit", 40),
            (self.notebook_blob_sha, "notebook blob sha", 40),
        ):
            if len(value) != length or not re.fullmatch(r"[0-9a-f]+", value):
                raise ValueError(f"invalid {label}.")


def load_config(path: str | Path) -> PilotAuditConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("case config must contain a JSON object.")
    return PilotAuditConfig.from_mapping(payload)


def validate_public_config(config: PilotAuditConfig) -> None:
    expected = {
        "case_id": CASE_ID,
        "repository": "Dryad",
        "doi": SOURCE_DOI,
        "published_date": "2023-07-31",
        "version_label": "2023-07-31",
        "license": "CC0-1.0",
        "pair_id": PILOT_PAIR_ID,
        "material": "Au",
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
        "dryad_pilot_pair_named_as_training_input": False,
        "authoritative_cross_dataset_acquisition_lineage_manifest_available": False,
    }
    for field, value in expected.items():
        actual = getattr(config, field)
        if actual != value:
            raise ValueError(
                f"public config mismatch for {field}: {actual!r} != {value!r}"
            )


def normalize_dryad_file_metadata(
    payload: Mapping[str, Any], spec: RemoteFileSpec, fallback_download_url: str
) -> dict[str, Any]:
    """Normalize current Dryad metadata without fabricating a missing digest."""
    if not isinstance(payload, Mapping):
        raise ValueError("Dryad file metadata must be an object.")
    raw_id = payload.get("id", payload.get("fileId", spec.file_id))
    try:
        file_id = int(raw_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("Dryad file metadata contains an invalid file ID.") from exc
    if file_id != spec.file_id:
        raise ValueError(f"Dryad file ID mismatch: {file_id} != {spec.file_id}")

    name = _first_text(payload, "path", "filename", "fileName", "name")
    if name is None:
        raise ValueError("Dryad file metadata does not contain a filename.")
    name = Path(name).name
    if name != spec.name:
        raise ValueError(f"Dryad filename mismatch: {name!r} != {spec.name!r}")

    raw_size = payload.get("size", payload.get("sizeBytes", payload.get("bytes")))
    try:
        size_bytes = int(raw_size)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Dryad file metadata does not contain a valid byte size."
        ) from exc
    if size_bytes <= 0:
        raise ValueError("Dryad file byte size must be positive.")

    algorithm, digest = _extract_digest(payload)
    expected_length = _SUPPORTED_DIGEST_LENGTHS.get(algorithm)
    if expected_length is None:
        raise ValueError(f"unsupported Dryad digest algorithm: {algorithm!r}.")
    if not re.fullmatch(rf"[0-9a-f]{{{expected_length}}}", digest):
        raise ValueError(f"Dryad {algorithm} digest is invalid.")

    download_url = _extract_download_url(payload) or fallback_download_url
    if not download_url.startswith("https://"):
        raise ValueError("Dryad download URL must use HTTPS.")
    return {
        "file_id": file_id,
        "name": name,
        "size_bytes": size_bytes,
        "digest_algorithm": algorithm,
        "digest": digest,
        "download_url": download_url,
    }


def _extract_digest(payload: Mapping[str, Any]) -> tuple[str, str]:
    candidates = [
        payload.get("digest"),
        payload.get("checksum"),
        payload.get("md5"),
        payload.get("sha256"),
    ]
    for candidate in candidates:
        if isinstance(candidate, Mapping):
            algorithm = str(
                candidate.get(
                    "algorithm", candidate.get("type", candidate.get("scheme", ""))
                )
            ).lower().replace("-", "").strip()
            value = str(
                candidate.get(
                    "value", candidate.get("digest", candidate.get("checksum", ""))
                )
            ).lower().strip()
            if value and not algorithm:
                algorithm = _algorithm_from_bare_digest(value)
            if algorithm and value:
                return algorithm, value
        if isinstance(candidate, str) and candidate.strip():
            text = candidate.strip().lower()
            if ":" in text:
                algorithm, value = text.split(":", 1)
                return algorithm.replace("-", "").strip(), value.strip()
            return _algorithm_from_bare_digest(text), text
    raise ValueError("Dryad file metadata does not expose a checksum.")


def _algorithm_from_bare_digest(value: str) -> str:
    if re.fullmatch(r"[0-9a-f]{32}", value):
        return "md5"
    if re.fullmatch(r"[0-9a-f]{64}", value):
        return "sha256"
    raise ValueError("cannot infer a supported digest algorithm from digest length.")


def _extract_download_url(payload: Mapping[str, Any]) -> str | None:
    direct = _first_text(payload, "downloadUrl", "download_url", "url")
    if direct and "api/v2/files/" not in direct:
        return direct
    links = payload.get("_links")
    if isinstance(links, Mapping):
        for key in ("stash:download", "download", "self"):
            link = links.get(key)
            href = link.get("href") if isinstance(link, Mapping) else link
            if isinstance(href, str) and href.startswith("https://"):
                if key != "self" or "downloads/file_stream" in href:
                    return href
    return None


def _remote_file(
    payload: Mapping[str, Any], size_key: str, unit: str
) -> RemoteFileSpec:
    _reject_unknown(payload, {"file_id", "name", size_key}, "remote file")
    return RemoteFileSpec(
        file_id=int(payload["file_id"]),
        name=_text(payload, "name"),
        landing_page_size=float(payload[size_key]),
        landing_page_size_unit=unit,
    )


def _mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} must be an object.")
    return value


def _text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty text.")
    return value.strip()


def _boolean(payload: Mapping[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be boolean.")
    return value


def _int_tuple(
    payload: Mapping[str, Any], key: str, length: int
) -> tuple[int, ...]:
    value = payload.get(key)
    if not isinstance(value, list) or len(value) != length:
        raise ValueError(f"{key} must contain {length} integers.")
    result = tuple(int(item) for item in value)
    if any(item <= 0 for item in result):
        raise ValueError(f"{key} must contain positive integers.")
    return result


def _first_text(payload: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _reject_unknown(
    payload: Mapping[str, Any], allowed: set[str], label: str
) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"unknown {label} keys: {unknown}")
