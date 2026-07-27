from pathlib import Path


def test_cross_repository_handoff_documentation_keeps_required_contract_terms() -> None:
    text = Path("docs/cross_repository_handoff.md").read_text(encoding="utf-8")
    for required in (
        "characterization_features_long.csv",
        "sample_context.csv",
        "characterization_handoff_bundle.json",
        "`sample_id` is the only allowed join key",
        "verify every recorded SHA-256",
        "reject row-order joins",
        "Diagnostic",
    ):
        assert required in text
