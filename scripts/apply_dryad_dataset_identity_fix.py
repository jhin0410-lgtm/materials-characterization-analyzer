from __future__ import annotations

from pathlib import Path


def replace_exact(path: Path, old: str, new: str, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    actual = text.count(old)
    if actual != count:
        raise SystemExit(f"{path}: expected {count}, found {actual}: {old[:100]!r}")
    path.write_text(text.replace(old, new), encoding="utf-8")


resolver = Path("scripts/resolve_dryad_pilot_file_metadata.py")
io = Path("src/mca/tem_external_validation_pilot_io.py")
resolver_tests = Path("tests/test_resolve_dryad_pilot_file_metadata.py")
pilot_tests = Path("tests/test_dryad_hrtem_pilot_pair_audit.py")

old_helpers = '''def _normalize_doi(value: str) -> str:
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
'''
new_helpers = '''def _normalize_doi(value: str) -> str:
    text = value.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if text.lower().startswith(prefix):
            text = text[len(prefix):]
            break
    return text.upper()


def _doi_from_dataset_url(url: str) -> str:
    path_token = urllib.parse.unquote(
        urllib.parse.urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
    )
    normalized = _normalize_doi(path_token)
    if not normalized.startswith("10.") or "/" not in normalized:
        raise ValueError(f"Dryad dataset link does not encode a DOI: {url}")
    return normalized


def _find_doi(value: Any) -> str | None:
    if isinstance(value, str):
        normalized = _normalize_doi(value)
        return value if normalized.startswith("10.") and "/" in normalized else None
    if isinstance(value, Mapping):
        for key, item in value.items():
            if (
                str(key).lower() in {"doi", "identifier"}
                and isinstance(item, str)
                and _find_doi(item) is not None
            ):
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
'''
replace_exact(resolver, old_helpers, new_helpers)
replace_exact(io, old_helpers, new_helpers)

old_verify = '''def _verify_dataset_identity(
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
'''
new_verify = '''def _verify_dataset_identity(
    version_payload: Mapping[str, Any],
    version_url: str,
    dataset_url: str,
    doi: str,
) -> Mapping[str, Any]:
    expected = _normalize_doi(doi)
    linked = _doi_from_dataset_url(dataset_url)
    if linked != expected:
        raise ValueError(f"Dryad dataset-link DOI mismatch: {linked!r} != {expected!r}")
    version_observed = _find_doi(version_payload)
    if version_observed is not None and _normalize_doi(version_observed) != expected:
        raise ValueError(
            f"Dryad source-version DOI mismatch: {version_observed!r} != {doi!r}"
        )
    dataset_payload = _fetch(dataset_url)
    dataset_observed = _find_doi(dataset_payload)
    if dataset_observed is not None and _normalize_doi(dataset_observed) != expected:
        raise ValueError(
            f"Dryad dataset API DOI mismatch: {dataset_observed!r} != {doi!r}"
        )
    return dataset_payload
'''
replace_exact(resolver, old_verify, new_verify)

old_resolve = '''    version_urls = {
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
'''
new_resolve = '''    version_urls = {
        _link(payload, f"{BASE_URL}/api/v2/files/{file_id}", "stash:version", "version")
        for (file_id, _), payload in zip(source_bindings, payloads)
    }
    if None in version_urls or len(version_urls) != 1:
        raise ValueError(f"pilot files do not resolve to one source version: {version_urls}")
    dataset_urls = {
        _link(payload, f"{BASE_URL}/api/v2/files/{file_id}", "stash:dataset", "dataset")
        for (file_id, _), payload in zip(source_bindings, payloads)
    }
    if None in dataset_urls or len(dataset_urls) != 1:
        raise ValueError(f"pilot files do not resolve to one dataset: {dataset_urls}")
    version_url = next(iter(version_urls))
    dataset_url = next(iter(dataset_urls))
    version_id = int(version_url.rstrip("/").rsplit("/", 1)[-1])
    if version_id != expected_version_id:
        raise ValueError(
            f"Dryad source-version mismatch: {version_id} != {expected_version_id}"
        )
    version_payload = _fetch(version_url)
    dataset_payload = _verify_dataset_identity(
        version_payload, version_url, dataset_url, doi
    )
'''
replace_exact(resolver, old_resolve, new_resolve)

old_context = '''    if version_url not in cache:
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
'''
new_context = '''    dataset_url = _dryad_link(individual_payload, api_url, "stash:dataset", "dataset")
    if dataset_url is None:
        raise ValueError("Dryad individual-file response lacks a dataset link.")
    expected_doi = _normalize_doi(config.doi)
    linked_doi = _doi_from_dataset_url(dataset_url)
    if linked_doi != expected_doi:
        raise ValueError(
            f"Dryad dataset-link DOI mismatch: {linked_doi!r} != {expected_doi!r}"
        )
    if version_url not in cache:
        version_payload = fetch_json(version_url)
        version_doi = _find_doi(version_payload)
        if version_doi is not None and _normalize_doi(version_doi) != expected_doi:
            raise ValueError(
                f"Dryad source-version DOI mismatch for source version {version_id}."
            )
        dataset_payload = fetch_json(dataset_url)
        dataset_doi = _find_doi(dataset_payload)
        if dataset_doi is not None and _normalize_doi(dataset_doi) != expected_doi:
            raise ValueError(
                f"Dryad dataset API DOI mismatch for source version {version_id}."
            )
        files_url = _dryad_link(version_payload, version_url, "stash:files", "files")
'''
replace_exact(io, old_context, new_context)
replace_exact(
    io,
    '''        cache[version_url] = {
            "records": records,
            "files_url": files_url,
            "dataset_doi": config.doi,
        }
    context = cache[version_url]
    return version_url, list(context["records"])
''',
    '''        cache[version_url] = {
            "records": records,
            "files_url": files_url,
            "dataset_url": dataset_url,
            "dataset_doi": config.doi,
        }
    context = cache[version_url]
    if context["dataset_url"] != dataset_url:
        raise ValueError("Dryad files resolve to different datasets within one source version.")
    return version_url, list(context["records"])
''',
)
replace_exact(
    io,
    '''            "dataset_doi": config.doi,
            "downloadUrl": download_url,
''',
    '''            "dataset_doi": config.doi,
            "dataset_api_url": cache[version_url]["dataset_url"],
            "downloadUrl": download_url,
''',
)

replace_exact(
    resolver_tests,
    '''def _raw(path: Path, file_id: int, name: str, version_id: int = 247105) -> Path:
''',
    '''def _raw(
    path: Path,
    file_id: int,
    name: str,
    version_id: int = 247105,
    dataset_doi: str = "10.7941/D1SP93",
) -> Path:
''',
)
replace_exact(
    resolver_tests,
    '''            "stash:version": {"href": f"https://datadryad.org/api/v2/versions/{version_id}"},
            "stash:download": {"href": f"https://datadryad.org/api/v2/files/{file_id}/download"},
''',
    '''            "stash:dataset": {
                "href": "/api/v2/datasets/doi%3A" + dataset_doi.replace("/", "%2F")
            },
            "stash:version": {"href": f"https://datadryad.org/api/v2/versions/{version_id}"},
            "stash:download": {"href": f"https://datadryad.org/api/v2/files/{file_id}/download"},
''',
)
replace_exact(
    resolver_tests,
    '''    files_url = version_url + "/files"
    records = [
''',
    '''    files_url = version_url + "/files"
    dataset_url = "https://datadryad.org/api/v2/datasets/doi%3A10.7941%2FD1SP93"
    records = [
''',
)
replace_exact(
    resolver_tests,
    '''    responses = {
        version_url: {"doi": "10.7941/D1SP93", "_links": {"stash:files": {"href": files_url}}},
        files_url: {"files": records},
    }
''',
    '''    responses = {
        version_url: {"_links": {"stash:files": {"href": files_url}}},
        dataset_url: {"identifier": "doi:10.7941/D1SP93"},
        files_url: {"files": records},
    }
''',
)
replace_exact(
    resolver_tests,
    '''    binding = (2451485, _raw(tmp_path / "image.json", 2451485, "image.h5"))
    version_url = "https://datadryad.org/api/v2/versions/247105"
    monkeypatch.setattr(module, "_fetch", lambda url, attempts=5: {"doi": "10.0000/WRONG"})
    with pytest.raises(ValueError, match="dataset DOI mismatch"):
''',
    '''    binding = (
        2451485,
        _raw(
            tmp_path / "image.json",
            2451485,
            "image.h5",
            dataset_doi="10.0000/WRONG",
        ),
    )
    with pytest.raises(ValueError, match="dataset-link DOI mismatch"):
''',
)

replace_exact(
    pilot_tests,
    '''    files_url = version_url + "/files"
    individual = {
''',
    '''    files_url = version_url + "/files"
    dataset_url = "https://datadryad.org/api/v2/datasets/doi%3A10.7941%2FD1SP93"
    individual = {
''',
    count=1,
)
replace_exact(
    pilot_tests,
    '''        "_links": {
            "stash:version": {"href": version_url},
            "stash:download": {"href": api_url + "/download"},
        },
    }
    version = {
        "doi": config.doi,
        "_links": {"stash:files": {"href": files_url}},
    }
''',
    '''        "_links": {
            "stash:dataset": {"href": dataset_url},
            "stash:version": {"href": version_url},
            "stash:download": {"href": api_url + "/download"},
        },
    }
    version = {"_links": {"stash:files": {"href": files_url}}}
''',
    count=1,
)
replace_exact(
    pilot_tests,
    '''    responses = {api_url: individual, version_url: version, files_url: files}
''',
    '''    responses = {
        api_url: individual,
        version_url: version,
        dataset_url: {"identifier": "doi:10.7941/D1SP93"},
        files_url: files,
    }
''',
    count=1,
)
replace_exact(
    pilot_tests,
    '''    files_url = version_url + "/files"
    responses = {
        api_url: {
''',
    '''    files_url = version_url + "/files"
    dataset_url = "https://datadryad.org/api/v2/datasets/doi%3A10.7941%2FD1SP93"
    responses = {
        api_url: {
''',
    count=1,
)
replace_exact(
    pilot_tests,
    '''            "_links": {
                "stash:version": {"href": version_url},
                "stash:download": {"href": api_url + "/download"},
            },
        },
        version_url: {"doi": config.doi, "_links": {"stash:files": {"href": files_url}}},
        files_url: {
''',
    '''            "_links": {
                "stash:dataset": {"href": dataset_url},
                "stash:version": {"href": version_url},
                "stash:download": {"href": api_url + "/download"},
            },
        },
        version_url: {"_links": {"stash:files": {"href": files_url}}},
        dataset_url: {"identifier": "doi:10.7941/D1SP93"},
        files_url: {
''',
    count=1,
)

print("Applied Dryad dataset-link identity fix")
