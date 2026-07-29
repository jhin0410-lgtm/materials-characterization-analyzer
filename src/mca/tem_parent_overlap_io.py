"""File, archive, and artifact helpers for the TEM parent-overlap audit."""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import stat
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

from . import __version__
from .tem_parent_overlap_contract import (
    CLOSEOUT_RESULT, FileSpec, ArchiveSpec, _validate_member_name,
)

def _acquire_file(spec: FileSpec, supplied: str | Path | None, temp: Path) -> tuple[Path, str]:
    return _acquire(spec, supplied, temp / spec.name)


def _acquire_archive(spec: ArchiveSpec, supplied: str | Path | None, temp: Path) -> tuple[Path, str]:
    return _acquire(spec, supplied, temp / spec.name)


def _acquire(spec: FileSpec | ArchiveSpec, supplied: str | Path | None, target: Path) -> tuple[Path, str]:
    if supplied is not None:
        path = Path(supplied)
        if path.is_symlink():
            raise ValueError(f"local input must not be a symlink: {path}")
        if not path.is_file():
            raise FileNotFoundError(path)
        return path, "local_exact_file"
    request = urllib.request.Request(spec.url, headers={"User-Agent": "materials-characterization-analyzer"})
    with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as handle:
        shutil.copyfileobj(response, handle, length=1024 * 1024)
    return target, "runtime_download"


def _verify_hashes(path: Path, spec: FileSpec | ArchiveSpec) -> dict[str, str]:
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            md5.update(chunk)
            sha256.update(chunk)
    result = {"md5": md5.hexdigest(), "sha256": sha256.hexdigest()}
    if result["md5"] != spec.md5:
        raise ValueError(f"MD5 mismatch for {spec.name}.")
    if result["sha256"] != spec.sha256:
        raise ValueError(f"SHA-256 mismatch for {spec.name}.")
    return result


def _validate_zip(path: Path, expected: tuple[str, ...]) -> dict[str, Any]:
    expected_set = set(expected)
    observed: set[str] = set()
    metadata: list[str] = []
    data_infos: list[zipfile.ZipInfo] = []
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            name = info.filename
            normalized = name.replace("\\", "/")
            posix = PurePosixPath(normalized)
            if posix.is_absolute() or ".." in posix.parts or normalized != name:
                raise ValueError(f"unsafe ZIP member path: {name}")
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError(f"ZIP member must not be a symlink: {name}")
            if info.is_dir():
                continue
            if name.startswith("__MACOSX/") or posix.name.startswith("._"):
                metadata.append(name)
                continue
            _validate_member_name(name)
            observed.add(name)
            data_infos.append(info)
        if observed != expected_set:
            raise ValueError(
                "ZIP member inventory changed; "
                f"missing={sorted(expected_set - observed)}, "
                f"unexpected={sorted(observed - expected_set)}"
            )
        return {
            "member_count": len(observed),
            "members": sorted(observed),
            "metadata_member_count": len(metadata),
            "metadata_members": sorted(metadata),
            "compressed_bytes": sum(info.compress_size for info in data_infos),
            "uncompressed_bytes": sum(info.file_size for info in data_infos),
            "central_directory_validated": True,
            "safe_paths_verified": True,
            "symlinks_absent": True,
        }


def _extract_member(archive: zipfile.ZipFile, member: str, target: Path) -> str:
    digest = hashlib.sha256()
    with archive.open(member) as source, target.open("wb") as output:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
            output.write(chunk)
    return digest.hexdigest()


def _prepare_output(path: str | Path) -> Path:
    output = Path(path)
    if output.exists():
        if output.is_symlink() or not output.is_dir() or any(output.iterdir()):
            raise FileExistsError("output directory must be absent or empty.")
    else:
        output.mkdir(parents=True)
    return output


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]], columns: tuple[str, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row[column] for column in columns})


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _manifest(
    output: Path,
    artifacts: list[Path],
    case_id: str,
    training_sha256: str,
    archive_sha256: str,
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
        "source_sha256": {
            "training_images": training_sha256,
            "source_image_archive": archive_sha256,
        },
        "artifact_count": len(records),
        "artifacts": records,
    }


def _build_report(summary: Mapping[str, Any]) -> str:
    counts = summary["result_counts"]
    matches = summary["content_equivalent_matches"]
    lines = [
        "# Public Cobalt Oxide TEM Parent-Overlap Audit", "",
        "**Evidence level:** Diagnostic", "",
        f"**Result:** `{CLOSEOUT_RESULT}`", "", "## Counts", "",
        f"- Public source frames: {counts['source_frame_count']}",
        f"- Content-equivalent overlaps: {counts['content_equivalent_overlap_frame_count']}",
        f"- Review required: {counts['review_required_frame_count']}",
        f"- No content-equivalent overlap detected: {counts['no_content_equivalent_overlap_detected_frame_count']}",
        "- Independent external-validation candidates: 0", "", "## Exact matches", "",
    ]
    if matches:
        lines.extend(
            f"- `{item['source_frame_id']}` -> parent {item['training_candidate_parent']} ({item['matched_tile_count']} tiles)"
            for item in matches
        )
    else:
        lines.append("- None under the audited comparison path.")
    lines.extend([
        "", "## Scientific boundary", "",
        "Non-overlapping frames remain image-only candidates because the public masks are source predictions, not independent ground truth.",
        "", "## Primary limitation", "",
        summary["scientific_closeout"]["primary_limitation"],
        "", "## Evidence required", "",
        summary["scientific_closeout"]["evidence_that_would_change_conclusion"],
        "", "## Limitations", "",
    ])
    lines.extend(f"- {item}" for item in summary["limitations"])
    return "\n".join(lines) + "\n"


FRAME_COLUMNS = (
    "source_id", "frame_index", "source_frame_id", "source_member",
    "source_member_sha256", "best_training_candidate_parent",
    "best_exact_tile_match_count", "best_exact_tile_match_fraction",
    "best_signature_ncc", "best_signature_rmse", "best_signature_max_abs_difference",
    "overlap_status", "external_validation_candidate_status",
    "independent_label_status", "independent_external_validation_candidate",
)

PAIRWISE_COLUMNS = (
    "source_id", "frame_index", "source_frame_id", "source_member",
    "source_member_sha256", "training_candidate_parent", "exact_tile_match_count",
    "exact_tile_match_fraction", "signature_ncc", "signature_rmse",
    "signature_max_abs_difference", "all_aligned_tile_hashes_match",
)
