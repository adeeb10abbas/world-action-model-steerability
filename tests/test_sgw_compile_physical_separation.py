"""Synthetic matched goals distinguish physical response from binary success."""
import copy

import pytest

from experiments.workshops.spatial_grounding_v1.compile import _confirmation_estimates


def paired_rows(family='LAT'):
    # Literal requested margins: D follows goals; C reverses both; I is fixed
    # at r=+0.07 m regardless of goal. M(-) is the negative of r(-).
    pairs = {
        'D': ((1, .13, 1), (-1, .13, 1)),
        'C': ((1, -.04, 0), (-1, -.08, 0)),
        'I': ((1, .07, 1), (-1, -.07, 0)),
    }
    return [
        {'model': 'N3', 'family': family, 'layout_id': f'{family}-C01',
         'stage': 'C', 'form': form, 'physical_goal_sign': sign,
         'analysis_status': 'complete', 'S': success,
         'status': 'valid_success' if success else 'valid_model_failure',
         'terminal_margin_m': margin, 'terminal_step': 450,
         'safety_censored': False}
        for form, goals in pairs.items() for sign, margin, success in goals
    ]


@pytest.mark.parametrize('family', ['LAT', 'HEIGHT', 'DIST'])
def test_physical_separation_has_metre_scale_and_retains_reversal_sign(family):
    row, = _confirmation_estimates(paired_rows(family))
    assert row['physical_separation_m_by_form'] == pytest.approx(
        {'D': .26, 'C': -.12, 'I': 0.0})
    assert row['physical_separation_status_by_form'] == dict.fromkeys(('D', 'C', 'I'), 'available')
    assert row['success_asymmetry_by_form'] == {'D': 0.0, 'C': 0.0, 'I': 1.0}
    # Existing consumers retain their numeric output with an explicit warning
    # in the data schema that the historical field is binary, not metres.
    assert row['separation_by_form'] == row['success_asymmetry_by_form']
    assert row['separation_by_form_legacy_alias_for'] == 'success_asymmetry_by_form'


def test_valid_manipulation_failures_still_contribute_observed_physical_endpoints():
    rows = paired_rows()
    rows[0].update(S=0, status='valid_model_failure')
    result, = _confirmation_estimates(rows)
    assert result['physical_separation_m_by_form']['D'] == pytest.approx(.26)
    assert result['success_asymmetry_by_form']['D'] == -1.0


@pytest.mark.parametrize('changes,expected_status', [
    ({'terminal_margin_m': None}, 'missing_margin'),
    ({'terminal_margin_m': float('nan')}, 'nonfinite_margin'),
    ({'terminal_margin_m': float('inf')}, 'nonfinite_margin'),
    ({'terminal_step': None}, 'missing_terminal_endpoint'),
    ({'terminal_step': 449}, 'missing_terminal_endpoint'),
    ({'status': 'censored', 'S': 0}, 'censored'),
    ({'safety_censored': True, 'S': 0}, 'censored'),
])
def test_missing_or_censored_endpoint_is_not_imputed_or_carried_forward(changes, expected_status):
    rows = paired_rows()
    rows[1].update(changes)
    result, = _confirmation_estimates(rows)
    assert result['status'] == 'complete'  # Binary six-cell block remains observed.
    assert result['physical_separation_m_by_form']['D'] is None
    assert result['physical_separation_status_by_form']['D'] == expected_status
    assert result['margin_status'] == 'unavailable'
    assert result['delta_M_I_C'] is None
    # Missing evidence in one form does not erase the other observed pairs.
    assert result['physical_separation_m_by_form']['C'] == pytest.approx(-.12)
    assert result['physical_separation_m_by_form']['I'] == 0.0


def test_absent_margin_is_not_reconstructed_from_success_or_the_other_goal():
    rows = paired_rows()
    del rows[0]['terminal_margin_m']
    result, = _confirmation_estimates(rows)
    assert result['physical_separation_m_by_form']['D'] is None
    assert result['physical_separation_status_by_form']['D'] == 'missing_margin'
    assert result['success_asymmetry_by_form']['D'] == 0.0


def test_incomplete_technical_block_produces_no_confirmatory_physical_estimate():
    rows = paired_rows()
    rows[0].update(analysis_status='incomplete', status='technical_invalid', S=None)
    before = copy.deepcopy(rows)
    result, = _confirmation_estimates(rows)
    assert rows == before
    assert result == {'model': 'N3', 'family': 'LAT', 'layout_id': 'LAT-C01', 'status': 'incomplete'}
