"""Assess a public HRTEM dataset as an external-validation candidate.

This module evaluates source metadata and comparability gates. It does not download
image arrays, train or run a model, compute segmentation accuracy, or certify
parent/acquisition independence.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import __version__

CASE_ID = "dryad_hrtem_external_validation_candidate_assessment"
SOURCE_DOI = "10.7941/D1SP93"
RESULT = "not_ready_for_in_domain_external_validation"
DOMAIN_SHIFT_STATUS = (
    "candidate_for_cross_material_domain_shift_stress_test_after_data_audit"
)

LIMITATIONS = (
    "The assessment uses source-reported repository metadata and does not independently inspect the HDF5 arrays or raw DM3 files.",
    "The candidate materials are Au, Ag, and CdSe rather than cobalt oxide, so performance would measure cross-material domain shift rather than in-domain cobalt-oxide generalization.",
    "One creator is shared with the cobalt-oxide dataset, and the public records do not provide an immutable cross-dataset acquisition-lineage exclusion manifest.",
    "Segmentation maps were created by one human labeler; inter-rater uncertainty and adjudication evidence are unavailable in the assessed metadata.",
    "No model training, inference, segmentation metric, physical conversion, causal claim, optimization, or engineering-release decision is performed.",
)


@dataclass(frozen=True)
class DatasetPair:
    pair_id: str
    material: str
    image_file: str
    image_size_mb: float
    label_file: str
    label_size_mb: float


@dataclass(frozen=True)
class CandidateAssessmentConfig:
    case_id: str
    repository: str
    doi: str
    published_date: str
    version_label: str
    license: str
    total_size_gb: float
    raw_image_count: int
    curated_pair_count: int
    materials: tuple[str, ...]
    substrates: tuple[str, ...]
    pixel_size_nm_range: tuple[float, float]
    electron_dose_e_per_a2_range: tuple[float, float]
    particle_diameter_nm_range: tuple[float, float]
    microscope: str
    camera: str
    raw_image_shape: tuple[int, int]
    labeler_count: int
    annotation_tool: str
    image_dataset_key: str
    label_dataset_key: str
    preprocessing_steps: tuple[str, ...]
    target_material: str
    overlapping_creator_names: tuple[str, ...]
    immutable_cross_dataset_lineage_manifest_available: bool
    verified_not_used_for_target_model_training: bool
    pairs: tuple[DatasetPair, ...]

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "CandidateAssessmentConfig":
        _reject_unknown(
            payload,
            {
                "case_id",
                "source",
                "reported_measurement_context",
                "processed_data_contract",
                "target_comparison",
                "pairs",
            },
            "config",
        )
        source = _mapping(payload, "source")
        context = _mapping(payload, "reported_measurement_context")
        processed = _mapping(payload, "processed_data_contract")
        target = _mapping(payload, "target_comparison")
        _reject_unknown(
            source,
            {
                "repository",
                "doi",
                "published_date",
                "version_label",
                "license",
                "total_size_gb",
                "raw_image_count",
                "curated_pair_count",
            },
            "source",
        )
        _reject_unknown(
            context,
            {
                "materials",
                "substrates",
                "pixel_size_nm_range",
                "electron_dose_e_per_a2_range",
                "particle_diameter_nm_range",
                "microscope",
                "camera",
                "raw_image_shape",
                "labeler_count",
                "annotation_tool",
            },
            "reported_measurement_context",
        )
        _reject_unknown(
            processed,
            {"image_dataset_key", "label_dataset_key", "preprocessing_steps"},
            "processed_data_contract",
        )
        _reject_unknown(
            target,
            {
                "target_material",
                "overlapping_creator_names",
                "immutable_cross_dataset_lineage_manifest_available",
                "verified_not_used_for_target_model_training",
            },
            "target_comparison",
        )
        pair_entries = payload.get("pairs")
        if not isinstance(pair_entries, list) or not pair_entries:
            raise ValueError("pairs must be a non-empty list.")
        pairs: list[DatasetPair] = []
        for index, entry in enumerate(pair_entries):
            if not isinstance(entry, Mapping):
                raise ValueError(f"pairs[{index}] must be an object.")
            _reject_unknown(
                entry,
                {
                    "pair_id",
                    "material",
                    "image_file",
                    "image_size_mb",
                    "label_file",
                    "label_size_mb",
                },
                f"pairs[{index}]",
            )
            pairs.append(
                DatasetPair(
                    pair_id=_required_text(entry, "pair_id"),
                    material=_required_text(entry, "material"),
                    image_file=_required_text(entry, "image_file"),
                    image_size_mb=float(entry["image_size_mb"]),
                    label_file=_required_text(entry, "label_file"),
                    label_size_mb=float(entry["label_size_mb"]),
                )
            )
        config = cls(
            case_id=_required_text(payload, "case_id"),
            repository=_required_text(source, "repository"),
            doi=_required_text(source, "doi"),
            published_date=_required_text(source, "published_date"),
            version_label=_required_text(source, "version_label"),
            license=_required_text(source, "license"),
            total_size_gb=float(source["total_size_gb"]),
            raw_image_count=int(source["raw_image_count"]),
            curated_pair_count=int(source["curated_pair_count"]),
            materials=_text_tuple(context, "materials"),
            substrates=_text_tuple(context, "substrates"),
            pixel_size_nm_range=_float_pair(context, "pixel_size_nm_range"),
            electron_dose_e_per_a2_range=_float_pair(
                context, "electron_dose_e_per_a2_range"
            ),
            particle_diameter_nm_range=_float_pair(
                context, "particle_diameter_nm_range"
            ),
            microscope=_required_text(context, "microscope"),
            camera=_required_text(context, "camera"),
            raw_image_shape=_int_pair(context, "raw_image_shape"),
            labeler_count=int(context["labeler_count"]),
            annotation_tool=_required_text(context, "annotation_tool"),
            image_dataset_key=_required_text(processed, "image_dataset_key"),
            label_dataset_key=_required_text(processed, "label_dataset_key"),
            preprocessing_steps=_text_tuple(processed, "preprocessing_steps"),
            target_material=_required_text(target, "target_material"),
            overlapping_creator_names=_text_tuple(
                target, "overlapping_creator_names", allow_empty=True
            ),
            immutable_cross_dataset_lineage_manifest_available=_required_bool(
                target, "immutable_cross_dataset_lineage_manifest_available"
            ),
            verified_not_used_for_target_model_training=_required_bool(
                target, "verified_not_used_for_target_model_training"
            ),
            pairs=tuple(pairs),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if not re.fullmatch(r"[a-z0-9_]+", self.case_id):
            raise ValueError("case_id must use lowercase letters, digits, and underscores.")
        if self.total_size_gb <= 0 or self.raw_image_count <= 0:
            raise ValueError("source size and raw image count must be positive.")
        if self.curated_pair_count != len(self.pairs):
            raise ValueError("curated_pair_count must equal the pair inventory length.")
        if self.labeler_count <= 0:
            raise ValueError("labeler_count must be positive.")
        for low, high, label in (
            (*self.pixel_size_nm_range, "pixel_size_nm_range"),
            (*self.electron_dose_e_per_a2_range, "electron_dose_e_per_a2_range"),
            (*self.particle_diameter_nm_range, "particle_diameter_nm_range"),
        ):
            if low <= 0 or high < low:
                raise ValueError(f"invalid {label}.")
        pair_ids = [pair.pair_id for pair in self.pairs]
        image_files = [pair.image_file for pair in self.pairs]
        label_files = [pair.label_file for pair in self.pairs]
        for label, values in (
            ("pair_id", pair_ids),
            ("image_file", image_files),
            ("label_file", label_files),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} values must be unique.")
        for pair in self.pairs:
            if pair.material not in self.materials:
                raise ValueError(f"pair material is absent from materials: {pair.material}")
            if pair.image_size_mb <= 0 or pair.label_size_mb <= 0:
                raise ValueError("pair file sizes must be positive.")
            if not pair.image_file.endswith("_Images.h5"):
                raise ValueError(f"unexpected image filename: {pair.image_file}")
            if not pair.label_file.endswith("_Labels.h5"):
                raise ValueError(f"unexpected label filename: {pair.label_file}")


def load_config(path: str | Path) -> CandidateAssessmentConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("case config must contain a JSON object.")
    return CandidateAssessmentConfig.from_mapping(payload)


def validate_public_config(config: CandidateAssessmentConfig) -> None:
    expected = {
        "case_id": CASE_ID,
        "repository": "Dryad",
        "doi": SOURCE_DOI,
        "published_date": "2023-07-31",
        "version_label": "2023-07-31",
        "license": "CC0-1.0",
        "total_size_gb": 33.69,
        "raw_image_count": 407,
        "curated_pair_count": 13,
        "materials": ("Au", "Ag", "CdSe"),
        "substrates": ("ultrathin C", "SiN"),
        "pixel_size_nm_range": (0.02, 0.042),
        "electron_dose_e_per_a2_range": (80.0, 884.0),
        "particle_diameter_nm_range": (2.2, 20.0),
        "microscope": "TEAM 0.5 aberration-corrected transmission electron microscope",
        "camera": "OneView (Gatan)",
        "raw_image_shape": (4096, 4096),
        "labeler_count": 1,
        "annotation_tool": "LabelBox",
        "image_dataset_key": "images",
        "label_dataset_key": "labels",
        "target_material": "cobalt oxide",
        "overlapping_creator_names": ("Mary Scott",),
        "immutable_cross_dataset_lineage_manifest_available": False,
        "verified_not_used_for_target_model_training": False,
    }
    for field, value in expected.items():
        actual = getattr(config, field)
        if actual != value:
            raise ValueError(f"public config mismatch for {field}: {actual!r} != {value!r}")


def run_candidate_assessment(
    config: CandidateAssessmentConfig, output_dir: str | Path
) -> dict[str, Any]:
    output = _prepare_output(output_dir)
    inventory_path = output / "tem_external_validation_candidate_inventory.csv"
    summary_path = output / "external_validation_candidate_summary.json"
    report_path = output / "external_validation_candidate_report.md"
    manifest_path = output / "external_validation_candidate_artifact_manifest.json"

    rows = [
        {
            "pair_id": pair.pair_id,
            "material": pair.material,
            "image_file": pair.image_file,
            "image_size_mb": pair.image_size_mb,
            "label_file": pair.label_file,
            "label_size_mb": pair.label_size_mb,
            "combined_size_mb": pair.image_size_mb + pair.label_size_mb,
            "source_doi": config.doi,
            "label_origin": "single_human_labeler_source_reported",
            "in_domain_material_match": pair.material.lower()
            == config.target_material.lower(),
            "candidate_status": DOMAIN_SHIFT_STATUS,
        }
        for pair in config.pairs
    ]
    smallest = min(rows, key=lambda row: float(row["combined_size_mb"]))
    material_match = any(bool(row["in_domain_material_match"]) for row in rows)
    gates = {
        "distinct_repository_doi_available": True,
        "human_segmentation_labels_reported": True,
        "multiple_acquisition_sessions_reported": True,
        "processed_image_label_pairs_available": True,
        "target_material_match": material_match,
        "immutable_cross_dataset_lineage_manifest_available": config.immutable_cross_dataset_lineage_manifest_available,
        "verified_not_used_for_target_model_training": config.verified_not_used_for_target_model_training,
        "creator_overlap_with_target_dataset": bool(config.overlapping_creator_names),
        "multi_labeler_or_adjudication_evidence_available": config.labeler_count > 1,
    }
    summary = {
        "schema_version": "1.0",
        "case_id": config.case_id,
        "software_version": __version__,
        "source": {
            "repository": config.repository,
            "doi": config.doi,
            "published_date": config.published_date,
            "version_label": config.version_label,
            "license": config.license,
            "total_size_gb": config.total_size_gb,
            "raw_image_count": config.raw_image_count,
            "curated_image_label_pair_count": config.curated_pair_count,
        },
        "reported_measurement_context": {
            "materials": list(config.materials),
            "substrates": list(config.substrates),
            "pixel_size_nm_range": list(config.pixel_size_nm_range),
            "electron_dose_e_per_a2_range": list(
                config.electron_dose_e_per_a2_range
            ),
            "particle_diameter_nm_range": list(
                config.particle_diameter_nm_range
            ),
            "microscope": config.microscope,
            "camera": config.camera,
            "raw_image_shape": list(config.raw_image_shape),
            "labeler_count": config.labeler_count,
            "annotation_tool": config.annotation_tool,
        },
        "processed_data_contract": {
            "image_dataset_key": config.image_dataset_key,
            "label_dataset_key": config.label_dataset_key,
            "preprocessing_steps": list(config.preprocessing_steps),
            "arrays_inspected_by_this_assessment": False,
            "checksums_pinned_by_this_assessment": False,
        },
        "target_comparison": {
            "target_material": config.target_material,
            "overlapping_creator_names": list(config.overlapping_creator_names),
            "gates": gates,
        },
        "result_counts": {
            "candidate_pair_count": len(rows),
            "in_domain_material_pair_count": sum(
                int(bool(row["in_domain_material_match"])) for row in rows
            ),
            "cross_material_pair_count": sum(
                int(not bool(row["in_domain_material_match"])) for row in rows
            ),
            "independent_in_domain_external_validation_pair_count": 0,
        },
        "pilot_recommendation": {
            "pair_id": smallest["pair_id"],
            "image_file": smallest["image_file"],
            "label_file": smallest["label_file"],
            "combined_size_mb": smallest["combined_size_mb"],
            "purpose": "smallest complete image-label pair for checksum, HDF5, lineage, and overlap audit before any model inference",
        },
        "readiness": {
            "status": RESULT,
            "cross_material_domain_shift_status": DOMAIN_SHIFT_STATUS,
            "model_evaluation_allowed_now": False,
            "required_before_model_evaluation": [
                "pin repository API file identifiers and checksums",
                "inspect exact HDF5 shapes, dtypes, attributes, and image-label pairing",
                "audit patch-to-parent or acquisition mapping",
                "audit content overlap against all target training parents",
                "freeze a parent-disjoint evaluation manifest before model inference",
                "document material and acquisition domain shift",
            ],
        },
        "processing": {
            "external_files_downloaded": False,
            "source_arrays_modified": False,
            "model_training_performed": False,
            "model_inference_performed": False,
            "segmentation_accuracy_computed": False,
            "physical_size_computed": False,
        },
        "scientific_closeout": {
            "status": "Diagnostic",
            "result": RESULT,
            "strongest_evidence": (
                "The source reports 407 raw HRTEM images, 13 processed image-label pairs, and single-human segmentation maps across multiple acquisition conditions."
            ),
            "primary_limitation": (
                "The materials differ from cobalt oxide, author and possible workflow lineage overlap exists, and no immutable cross-dataset parent/acquisition exclusion manifest has been verified."
            ),
            "evidence_that_would_change_conclusion": (
                "Checksum-pinned arrays with authoritative acquisition IDs, demonstrated non-use in target-model development, parent-disjoint overlap clearance, and preferably independently adjudicated labels."
            ),
            "suitable_for": [
                "external-source inventory",
                "cross-material domain-shift candidate selection",
                "pilot data-audit planning",
            ],
            "not_suitable_for": [
                "cobalt-oxide in-domain external validation",
                "segmentation performance claims",
                "model selection or engineering release",
            ],
        },
        "limitations": list(LIMITATIONS),
    }
    _write_csv(inventory_path, rows, INVENTORY_COLUMNS)
    _write_json(summary_path, summary)
    report_path.write_text(_build_report(summary), encoding="utf-8")
    manifest = _build_manifest(
        output,
        [inventory_path, summary_path, report_path],
        case_id=config.case_id,
        source_doi=config.doi,
    )
    _write_json(manifest_path, manifest)
    return summary


def _prepare_output(path: str | Path) -> Path:
    output = Path(path)
    if output.exists():
        if output.is_symlink() or not output.is_dir() or any(output.iterdir()):
            raise FileExistsError("output directory must be absent or empty.")
    else:
        output.mkdir(parents=True)
    return output


def _write_csv(
    path: Path, rows: Iterable[Mapping[str, Any]], columns: tuple[str, ...]
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row[column] for column in columns})


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _build_manifest(
    output: Path,
    artifacts: list[Path],
    *,
    case_id: str,
    source_doi: str,
) -> dict[str, Any]:
    records = [
        {
            "path": path.relative_to(output).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in artifacts
    ]
    return {
        "schema_version": "1.0",
        "case_id": case_id,
        "software_version": __version__,
        "source_doi": source_doi,
        "artifact_count": len(records),
        "artifacts": records,
    }


def _build_report(summary: Mapping[str, Any]) -> str:
    counts = summary["result_counts"]
    pilot = summary["pilot_recommendation"]
    lines = [
        "# Dryad HRTEM External-Validation Candidate Assessment",
        "",
        "**Evidence level:** Diagnostic",
        "",
        f"**Result:** `{summary['readiness']['status']}`",
        "",
        "## Source inventory",
        "",
        f"- Raw HRTEM images reported: {summary['source']['raw_image_count']}",
        f"- Processed image-label pairs: {counts['candidate_pair_count']}",
        f"- Target-material matches: {counts['in_domain_material_pair_count']}",
        f"- Independent in-domain external-validation pairs: {counts['independent_in_domain_external_validation_pair_count']}",
        "",
        "## Assessment",
        "",
        "The dataset is a credible external source with human segmentation labels, but it is not an in-domain cobalt-oxide validation set.",
        "",
        "It may become a cross-material domain-shift stress-test source only after checksum, HDF5, lineage, and content-overlap audits.",
        "",
        "## Smallest pilot pair",
        "",
        f"- Pair: `{pilot['pair_id']}`",
        f"- Image: `{pilot['image_file']}`",
        f"- Label: `{pilot['label_file']}`",
        f"- Combined reported size: {pilot['combined_size_mb']} MB",
        "",
        "## Required before inference",
        "",
    ]
    lines.extend(
        f"- {item}" for item in summary["readiness"]["required_before_model_evaluation"]
    )
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in summary["limitations"])
    return "\n".join(lines) + "\n"


def _mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} must be an object.")
    return value


def _required_text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty text.")
    return value


def _required_bool(payload: Mapping[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean.")
    return value


def _text_tuple(
    payload: Mapping[str, Any], key: str, *, allow_empty: bool = False
) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ValueError(f"{key} must be a {'possibly empty' if allow_empty else 'non-empty'} list.")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{key} must contain non-empty strings.")
    return tuple(value)


def _float_pair(payload: Mapping[str, Any], key: str) -> tuple[float, float]:
    value = payload.get(key)
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{key} must contain two values.")
    return float(value[0]), float(value[1])


def _int_pair(payload: Mapping[str, Any], key: str) -> tuple[int, int]:
    value = payload.get(key)
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{key} must contain two integers.")
    result = int(value[0]), int(value[1])
    if any(item <= 0 for item in result):
        raise ValueError(f"{key} values must be positive.")
    return result


def _reject_unknown(
    payload: Mapping[str, Any], allowed: set[str], context: str
) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"unknown {context} keys: {unknown}")


INVENTORY_COLUMNS = (
    "pair_id",
    "material",
    "image_file",
    "image_size_mb",
    "label_file",
    "label_size_mb",
    "combined_size_mb",
    "source_doi",
    "label_origin",
    "in_domain_material_match",
    "candidate_status",
)
