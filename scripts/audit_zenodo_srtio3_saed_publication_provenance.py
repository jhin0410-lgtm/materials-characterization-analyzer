from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

ARTICLE_DOI = "10.1038/s41586-026-10823-x"
ARTICLE_PATH = "/articles/s41586-026-10823-x"
ZENODO_DOI = "10.5281/zenodo.20300700"
TRUSTED_NATURE_HOSTS = {"nature.com", "www.nature.com"}


class SrTiO3PublicationProvenanceError(RuntimeError):
    """Raised when the bounded SrTiO3 publication-provenance contract is violated."""


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() in {"script", "style", "noscript"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in {"script", "style", "noscript"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth and data.strip():
            self.parts.append(data)


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SrTiO3PublicationProvenanceError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve(strict=True)
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            payload = json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise SrTiO3PublicationProvenanceError(f"invalid JSON: {resolved}") from exc
    if not isinstance(payload, dict):
        raise SrTiO3PublicationProvenanceError(f"JSON root must be an object: {resolved}")
    return payload


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _resolve_repo_path(value: object) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise SrTiO3PublicationProvenanceError("repository evidence path must be a string")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise SrTiO3PublicationProvenanceError("configured repository evidence path is unsafe")
    resolved = (PROJECT_ROOT / candidate).resolve(strict=True)
    if PROJECT_ROOT not in resolved.parents:
        raise SrTiO3PublicationProvenanceError("repository evidence resolved outside project root")
    return resolved


def _string_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise SrTiO3PublicationProvenanceError(f"{field} must be a non-empty list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise SrTiO3PublicationProvenanceError(f"{field} must contain non-empty strings")
        text = item.strip()
        if text in result:
            raise SrTiO3PublicationProvenanceError(f"{field} must not contain duplicates")
        result.append(text)
    return result


def _trusted_publication_url(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise SrTiO3PublicationProvenanceError("publication URL is missing")
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in TRUSTED_NATURE_HOSTS:
        raise SrTiO3PublicationProvenanceError("publication URL is outside trusted Nature host")
    if parsed.path != ARTICLE_PATH:
        raise SrTiO3PublicationProvenanceError("publication URL path is not the pinned article")
    return value


def _validate_config(config: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "case_id",
        "audit_date",
        "publication",
        "repository_evidence",
        "expected_saed_members",
        "scientific_boundary",
        "decision_rules",
    }
    if set(config) != required or config.get("schema_version") != "1.0":
        raise SrTiO3PublicationProvenanceError(
            "publication provenance config keys/schema do not match contract"
        )

    publication = config.get("publication")
    expected_publication_fields = {
        "doi",
        "title",
        "url",
        "maximum_response_bytes",
        "required_text_claims",
    }
    if not isinstance(publication, dict) or set(publication) != expected_publication_fields:
        raise SrTiO3PublicationProvenanceError("publication contract is invalid")
    if publication.get("doi") != ARTICLE_DOI:
        raise SrTiO3PublicationProvenanceError("publication DOI drifted")
    _trusted_publication_url(publication.get("url"))
    if ARTICLE_DOI.rsplit("/", 1)[-1] != ARTICLE_PATH.rsplit("/", 1)[-1]:
        raise SrTiO3PublicationProvenanceError("publication DOI and Nature article path disagree")
    title_stem = publication.get("title")
    if not isinstance(title_stem, str) or title_stem.strip() != (
        "Imaging of nanoscale polar textures in quantum paraelectric"
    ):
        raise SrTiO3PublicationProvenanceError("publication stable title stem drifted")
    ceiling = publication.get("maximum_response_bytes")
    if not isinstance(ceiling, int) or not 100_000 <= ceiling <= 5_000_000:
        raise SrTiO3PublicationProvenanceError("publication response ceiling is invalid")

    claims = publication.get("required_text_claims")
    required_claims = {
        "figure_1d_temperature_sequence",
        "figure_1d_reciprocal_scale",
        "afd_superspot_assignment",
        "extended_temperature_series",
        "zenodo_data_binding",
    }
    if not isinstance(claims, dict) or set(claims) != required_claims:
        raise SrTiO3PublicationProvenanceError("required publication claim set drifted")
    for name, terms in claims.items():
        _string_list(terms, f"required_text_claims.{name}")

    evidence = config.get("repository_evidence")
    expected_evidence_keys = {
        "metadata_snapshot",
        "remote_inventory_snapshot",
        "tiff_metadata_snapshot",
        "prepixel_metadata_snapshot",
        "notebook_provenance_snapshot",
    }
    if not isinstance(evidence, dict) or set(evidence) != expected_evidence_keys:
        raise SrTiO3PublicationProvenanceError("repository_evidence contract is invalid")
    for path in evidence.values():
        _resolve_repo_path(path)

    members = config.get("expected_saed_members")
    expected_members = {
        "SAED/23K.tif": 23,
        "SAED/91K.tif": 91,
        "SAED/172K.tif": 172,
    }
    if not isinstance(members, list) or len(members) != 3:
        raise SrTiO3PublicationProvenanceError("expected_saed_members must contain three entries")
    observed_members: dict[str, int] = {}
    for item in members:
        if not isinstance(item, dict) or set(item) != {"path", "temperature_k"}:
            raise SrTiO3PublicationProvenanceError("expected SAED member entry is invalid")
        path = item.get("path")
        temperature = item.get("temperature_k")
        if not isinstance(path, str) or not isinstance(temperature, int):
            raise SrTiO3PublicationProvenanceError("expected SAED member types are invalid")
        observed_members[path] = temperature
    if observed_members != expected_members:
        raise SrTiO3PublicationProvenanceError("expected SAED member/temperature mapping drifted")

    boundary = config.get("scientific_boundary")
    allowed_true = {
        "publication_html_request_authorized",
        "publication_text_normalization_authorized",
    }
    if not isinstance(boundary, dict) or any(
        boundary.get(key) is not True for key in allowed_true
    ):
        raise SrTiO3PublicationProvenanceError("publication text operations are not authorized")
    if any(value is not False for key, value in boundary.items() if key not in allowed_true):
        raise SrTiO3PublicationProvenanceError(
            "pixel/analyzer/figure-image actions must remain disabled"
        )

    rules = config.get("decision_rules")
    if not isinstance(rules, dict) or not rules or any(value is not True for value in rules.values()):
        raise SrTiO3PublicationProvenanceError("all fail-closed publication rules must be enabled")
    return config


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", html.unescape(value)).casefold()
    normalized = normalized.replace("−", "-").replace("–", "-").replace("—", "-")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _visible_text(payload: bytes) -> str:
    try:
        decoded = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SrTiO3PublicationProvenanceError("publication response is not UTF-8 HTML") from exc
    parser = _VisibleTextParser()
    parser.feed(decoded)
    return _normalize_text(" ".join(parser.parts))


def _download_publication(url: str, maximum_bytes: int) -> tuple[bytes, str]:
    request = urllib.request.Request(
        _trusted_publication_url(url),
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/140.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "identity",
        },
    )
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
    with opener.open(request, timeout=120) as response:
        status = getattr(response, "status", None) or response.getcode()
        if status != 200:
            raise SrTiO3PublicationProvenanceError(f"publication returned HTTP {status}")
        final_url = response.geturl()
        parsed = urllib.parse.urlparse(final_url)
        if parsed.scheme != "https" or parsed.hostname not in TRUSTED_NATURE_HOSTS:
            raise SrTiO3PublicationProvenanceError("publication redirected outside trusted Nature host")
        if parsed.path != ARTICLE_PATH:
            raise SrTiO3PublicationProvenanceError("publication redirected away from pinned article")
        content_type = response.headers.get_content_type()
        if content_type not in {"text/html", "application/xhtml+xml"}:
            raise SrTiO3PublicationProvenanceError(
                f"unexpected publication content type: {content_type}"
            )
        payload = response.read(maximum_bytes + 1)
    if len(payload) > maximum_bytes:
        raise SrTiO3PublicationProvenanceError("publication response exceeds configured ceiling")
    return payload, final_url


def _validate_repository_evidence(config: Mapping[str, Any]) -> dict[str, Any]:
    paths = {
        name: _resolve_repo_path(path)
        for name, path in config["repository_evidence"].items()
    }
    snapshots = {name: _load_json(path) for name, path in paths.items()}

    metadata = snapshots["metadata_snapshot"]
    if metadata.get("execution_status") != "metadata_audit_completed":
        raise SrTiO3PublicationProvenanceError("metadata snapshot is not completed")
    source = metadata.get("source")
    if not isinstance(source, Mapping) or source.get("record_id") != 20300700:
        raise SrTiO3PublicationProvenanceError("metadata snapshot is not the pinned Zenodo record")
    if source.get("doi") != ZENODO_DOI:
        raise SrTiO3PublicationProvenanceError("metadata Zenodo DOI drifted")

    remote = snapshots["remote_inventory_snapshot"]
    if remote.get("execution_status") != "remote_central_directory_inventory_completed":
        raise SrTiO3PublicationProvenanceError("remote inventory is not completed")
    inventory_summary = remote.get("inventory_summary")
    if not isinstance(inventory_summary, Mapping):
        raise SrTiO3PublicationProvenanceError("remote inventory summary is invalid")
    member_paths = inventory_summary.get("member_paths")
    if not isinstance(member_paths, list):
        raise SrTiO3PublicationProvenanceError("remote inventory member paths are invalid")
    expected_paths = [item["path"] for item in config["expected_saed_members"]]
    if any(path not in member_paths for path in expected_paths):
        raise SrTiO3PublicationProvenanceError("expected SAED TIFF is absent from remote inventory")

    tiff = snapshots["tiff_metadata_snapshot"]
    if tiff.get("case_id") != "zenodo_srtio3_saed_tiff_metadata":
        raise SrTiO3PublicationProvenanceError("TIFF metadata case identity drifted")
    common = tiff.get("common_tiff_structure")
    if not isinstance(common, Mapping):
        raise SrTiO3PublicationProvenanceError("TIFF structure evidence is invalid")
    if common.get("ImageWidth") != 2048 or common.get("ImageLength") != 2048:
        raise SrTiO3PublicationProvenanceError("TIFF dimensions differ from verified evidence")
    readiness = tiff.get("readiness")
    if not isinstance(readiness, Mapping):
        raise SrTiO3PublicationProvenanceError("TIFF readiness evidence is invalid")
    if common.get("StripOffsets") != 272 or readiness.get("pixel_access_authorized") is not False:
        raise SrTiO3PublicationProvenanceError("TIFF pixel boundary drifted")
    tiff_members = tiff.get("members")
    if not isinstance(tiff_members, list):
        raise SrTiO3PublicationProvenanceError("TIFF member evidence is invalid")
    observed_tiff_paths = [
        item.get("path") for item in tiff_members if isinstance(item, Mapping)
    ]
    if observed_tiff_paths != expected_paths:
        raise SrTiO3PublicationProvenanceError("TIFF member order/identity differs from contract")

    prepixel = snapshots["prepixel_metadata_snapshot"]
    if prepixel.get("case_id") != "zenodo_srtio3_saed_prepixel_metadata":
        raise SrTiO3PublicationProvenanceError("pre-pixel metadata case identity drifted")
    text_metadata = prepixel.get("common_text_metadata")
    range_evidence = prepixel.get("range_evidence")
    if not isinstance(text_metadata, Mapping) or not isinstance(range_evidence, Mapping):
        raise SrTiO3PublicationProvenanceError("pre-pixel evidence structure is invalid")
    software = text_metadata.get("Software")
    if not isinstance(software, Mapping) or software.get("text") != "tifffile.py":
        raise SrTiO3PublicationProvenanceError("TIFF serialization evidence drifted")
    if range_evidence.get("pixel_bytes_decompressed") != 0:
        raise SrTiO3PublicationProvenanceError("pre-pixel audit unexpectedly accessed pixels")

    notebook = snapshots["notebook_provenance_snapshot"]
    if notebook.get("case_id") != "zenodo_srtio3_notebook_provenance":
        raise SrTiO3PublicationProvenanceError("notebook provenance case identity drifted")
    search = notebook.get("search_summary")
    if not isinstance(search, Mapping):
        raise SrTiO3PublicationProvenanceError("notebook search summary is invalid")
    for field in (
        "explicit_saed_term_hits",
        "explicit_23K_hits",
        "explicit_91K_hits",
        "explicit_172K_hits",
    ):
        if search.get(field) != 0:
            raise SrTiO3PublicationProvenanceError(
                "notebook evidence unexpectedly acquired direct SAED/temperature linkage"
            )

    return {
        "record_id": 20300700,
        "doi": ZENODO_DOI,
        "saed_archive_key": "SAED.zip",
        "saed_member_paths": expected_paths,
        "tiff_shape": [2048, 2048],
        "tiff_storage": "float64",
        "tiff_serialization_software": "tifffile.py",
        "verified_first_pixel_strip_offset": 272,
        "notebook_explicit_saed_or_temperature_hits": 0,
        "snapshot_sha256": {name: _sha256_file(path) for name, path in paths.items()},
    }


def _claim_results(text: str, claims: Mapping[str, Any]) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for claim_name, raw_terms in claims.items():
        terms = _string_list(raw_terms, f"required_text_claims.{claim_name}")
        normalized_terms = [_normalize_text(term) for term in terms]
        found = {term: term in text for term in normalized_terms}
        if not all(found.values()):
            missing = [term for term, present in found.items() if not present]
            raise SrTiO3PublicationProvenanceError(
                f"required publication claim {claim_name!r} is missing terms: {missing}"
            )
        results[str(claim_name)] = {
            "supported": True,
            "required_terms": normalized_terms,
        }
    return results


def run_audit(*, config_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    config_resolved = Path(config_path).expanduser().resolve(strict=True)
    config = _validate_config(_load_json(config_resolved))
    repository_binding = _validate_repository_evidence(config)

    publication = config["publication"]
    payload, final_url = _download_publication(
        str(publication["url"]), int(publication["maximum_response_bytes"])
    )
    text = _visible_text(payload)
    title_stem = _normalize_text(str(publication["title"]))
    if title_stem not in text:
        raise SrTiO3PublicationProvenanceError(
            "stable publication title stem is absent from Nature response"
        )
    claims = _claim_results(text, publication["required_text_claims"])

    result = {
        "schema_version": "1.0",
        "case_id": config["case_id"],
        "audit_date": config["audit_date"],
        "execution_status": "publication_provenance_audit_completed",
        "config_sha256": _sha256_file(config_resolved),
        "publication": {
            "doi": publication["doi"],
            "title": publication["title"],
            "identity_basis": "exact DOI, exact Nature article path, and stable visible title stem",
            "source_url": publication["url"],
            "final_url": final_url,
            "response_bytes": len(payload),
            "response_sha256": _sha256_bytes(payload),
            "html_retained": False,
            "visible_text_retained": False,
            "required_claims": claims,
        },
        "repository_binding": repository_binding,
        "supported_publication_facts": {
            "figure_1d_temperatures_k": [23, 91, 172],
            "figure_1d_reciprocal_scale_bar_inv_angstrom": 0.1,
            "figure_1d_afd_superspot_assignment": "half-integer AFD superspots",
            "extended_data_diffraction_temperature_range_k": [23, 215],
            "final_article_data_availability_zenodo_doi": ZENODO_DOI,
        },
        "evidence_assessment": {
            "final_publication_identity": "Supported",
            "publication_to_zenodo_record_binding": "Supported",
            "saed_filename_temperature_semantics": "Supported",
            "published_figure_1d_reciprocal_scale_bar": "Supported",
            "source_author_afd_superspot_assignment": "Diagnostic",
            "exact_tiff_byte_to_figure_panel_binding": "Diagnostic",
            "source_tiff_pixel_to_reciprocal_scale_calibration": "Inconclusive",
            "source_tiff_pattern_center": "Inconclusive",
            "saed_acquisition_independence": "Inconclusive",
            "detector_native_intensity_provenance": "Inconclusive",
            "complete_reference_truth_for_phase_indexing": "Inconclusive",
            "external_validation_readiness": "Inconclusive",
            "scientific_evidence_level": "Diagnostic",
        },
        "readiness": {
            "temperature_semantics_resolved": True,
            "bounded_source_to_published_figure_mapping_can_be_predeclared": True,
            "saed_tiff_pixel_access_authorized": False,
            "published_figure_image_download_authorized": False,
            "image_registration_authorized": False,
            "four_d_stem_download_authorized": False,
            "analyzer_execution_authorized": False,
            "phase_indexing_authorized": False,
            "external_validation_ready": False,
            "engineering_decision_ready": False,
        },
        "next_evidence": {
            "priority": 1,
            "requirement": (
                "predeclared_bounded_source_tiff_to_published_figure1d_identity_and_"
                "reciprocal_scale_mapping"
            ),
            "why": (
                "The final publication now resolves the 23K/91K/172K temperature semantics and "
                "provides a 0.1 inverse-angstrom scale bar for the displayed patterns, but the "
                "source TIFF pixels are not yet byte-to-panel bound or calibrated."
            ),
            "pixel_access_requires_separate_contract": True,
            "four_d_stem_access_required": False,
        },
        "scientific_boundary": [
            "The final publication resolves the temperature meaning of the three SAED labels because it directly binds figure data to the same Zenodo record and shows diffraction at 23 K, 91 K, and 172 K.",
            "The published 0.1 inverse-angstrom scale bar applies to the displayed figure panel and is not silently transferred into a source-TIFF pixel calibration.",
            "The same-region temperature realignment described for 4D-STEM is not used as evidence that the three SAED TIFFs are independent or paired acquisitions.",
            "The notebook remains a separate 4D-STEM workflow and its rotation, crop, and beam-centre procedure is not applied to SAED TIFFs.",
            "No diffraction pixel, published figure image, analyzer inference, phase indexing, external-validation claim, or engineering decision is authorized by this audit."
        ],
    }

    output = Path(output_path).expanduser().resolve(strict=False)
    if output.exists():
        raise SrTiO3PublicationProvenanceError(f"refusing to overwrite output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the final SrTiO3 publication's bounded textual link to the Zenodo SAED "
            "evidence without opening diffraction pixels or figure images."
        )
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        result = run_audit(config_path=args.config, output_path=args.output)
    except (SrTiO3PublicationProvenanceError, FileNotFoundError, OSError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
