from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

SCRIPTS = Path(__file__).parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import review_public_zr15nb_dsc_candidates as review  # noqa: E402


def _row(
    run_id: str,
    candidate_id: int,
    candidate_type: str,
    temperature_c: float,
    enthalpy: float,
) -> dict:
    return {
        "run_id": run_id,
        "candidate_id": candidate_id,
        "candidate_type": candidate_type,
        "temperature_c": temperature_c,
        "enthalpy_within_fwhm_j_g": enthalpy,
    }


def test_review_matches_same_direction_candidates_one_to_one() -> None:
    table = pd.DataFrame(
        [
            _row("primary", 1, "exothermic", 360.0, -10.0),
            _row("primary", 2, "endothermic", 500.0, 5.0),
            _row("sensitivity_1c", 1, "exothermic", 360.2, -9.9),
            _row("sensitivity_1c", 2, "endothermic", 500.1, 5.1),
            _row("sensitivity_5c", 1, "exothermic", 360.5, -10.1),
            _row("sensitivity_5c", 2, "endothermic", 499.8, 4.9),
        ]
    )
    reviewed, unmatched = review.review_candidates(table, tolerance_c=10.0)
    assert len(reviewed) == 2
    assert unmatched.empty
    assert reviewed["all_runs_matched"].all()
    assert reviewed["all_runs_diagnostic_area_direction_consistent"].all()
    assert set(reviewed["case_review_status"]) == {"stable_temperature_review_required"}
    assert reviewed["maximum_temperature_spread_c"].max() == pytest.approx(0.5)


def test_directionally_inconsistent_area_is_flagged_not_removed() -> None:
    table = pd.DataFrame(
        [
            _row("primary", 1, "endothermic", 657.0, -0.5),
            _row("sensitivity_1c", 1, "endothermic", 657.1, -0.6),
            _row("sensitivity_5c", 1, "endothermic", 649.1, -0.7),
        ]
    )
    reviewed, unmatched = review.review_candidates(table, tolerance_c=10.0)
    assert len(reviewed) == 1
    assert unmatched.empty
    row = reviewed.iloc[0]
    assert row["all_runs_matched"]
    assert not row["all_runs_diagnostic_area_direction_consistent"]
    assert row["case_review_status"] == (
        "stable_temperature_area_direction_review_required"
    )


def test_unmatched_sensitivity_candidate_is_preserved() -> None:
    table = pd.DataFrame(
        [
            _row("primary", 1, "exothermic", 360.0, -10.0),
            _row("sensitivity_1c", 1, "exothermic", 360.1, -10.0),
            _row("sensitivity_1c", 2, "endothermic", 700.0, 1.0),
            _row("sensitivity_5c", 1, "exothermic", 360.2, -10.0),
        ]
    )
    reviewed, unmatched = review.review_candidates(table, tolerance_c=10.0)
    assert len(reviewed) == 1
    assert len(unmatched) == 1
    assert unmatched.iloc[0]["candidate_type"] == "endothermic"
    assert unmatched.iloc[0]["temperature_c"] == pytest.approx(700.0)


def test_review_rejects_missing_run_or_invalid_tolerance() -> None:
    table = pd.DataFrame(
        [
            _row("primary", 1, "exothermic", 360.0, -10.0),
            _row("sensitivity_1c", 1, "exothermic", 360.1, -10.0),
        ]
    )
    with pytest.raises(review.ReviewError, match="exactly the three configured runs"):
        review.review_candidates(table, tolerance_c=10.0)
    complete = pd.concat(
        [table, pd.DataFrame([_row("sensitivity_5c", 1, "exothermic", 360.2, -10.0)])],
        ignore_index=True,
    )
    with pytest.raises(review.ReviewError, match="tolerance must be positive"):
        review.review_candidates(complete, tolerance_c=0.0)



def test_global_assignment_maximizes_matches_before_distance() -> None:
    table = pd.DataFrame(
        [
            _row("primary", 1, "exothermic", 0.0, -1.0),
            _row("primary", 2, "exothermic", 10.0, -1.0),
            _row("sensitivity_1c", 1, "exothermic", -6.1, -1.0),
            _row("sensitivity_1c", 2, "exothermic", 4.0, -1.0),
            _row("sensitivity_5c", 1, "exothermic", -6.1, -1.0),
            _row("sensitivity_5c", 2, "exothermic", 4.0, -1.0),
        ]
    )
    reviewed, unmatched = review.review_candidates(table, tolerance_c=10.0)
    assert unmatched.empty
    assert reviewed["all_runs_matched"].all()
    first = reviewed.sort_values("primary_temperature_c").iloc[0]
    second = reviewed.sort_values("primary_temperature_c").iloc[1]
    assert first["sensitivity_1c_temperature_c"] == pytest.approx(-6.1)
    assert second["sensitivity_1c_temperature_c"] == pytest.approx(4.0)


def test_existing_review_section_is_replaced_idempotently() -> None:
    base = "# Report\n\nOriginal evidence"
    reviewed = (
        base
        + "\n\n"
        + review.REVIEW_SECTION_START
        + "\n## Candidate smoothing-sensitivity review\nold\n"
        + review.REVIEW_SECTION_END
    )
    assert review._strip_existing_review(reviewed) == base
    legacy = base + "\n\n## Candidate smoothing-sensitivity review\nold"
    assert review._strip_existing_review(legacy) == base
