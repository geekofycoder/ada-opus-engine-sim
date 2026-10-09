"""Engine maths, checked against hand calculations.

No knowledge base, no files, no network, no API key. If these fail, the
arithmetic is wrong.
"""

import pytest
from conftest import ROOT  # noqa: F401  (puts the project root on sys.path)

from engine import bayes as B


# -- normalize -------------------------------------------------------------

def test_normalize_sums_to_one():
    out = B.normalize({"a": 2, "b": 3, "c": 5})
    assert sum(out.values()) == pytest.approx(1.0)
    assert out["a"] == pytest.approx(0.2)


def test_normalize_survives_total_collapse():
    """All weights zero must not divide by zero."""
    out = B.normalize({"a": 0.0, "b": 0.0})
    assert out["a"] == pytest.approx(0.5)


# -- entropy ---------------------------------------------------------------

def test_entropy_uniform_four_is_two_bits():
    assert B.entropy({k: 0.25 for k in "abcd"}) == pytest.approx(2.0)


def test_entropy_certainty_is_zero():
    assert B.entropy({"a": 1.0, "b": 0.0}) == pytest.approx(0.0)


def test_effective_options_is_two_to_the_entropy():
    assert B.effective_options({k: 0.25 for k in "abcd"}) == pytest.approx(4.0)


# -- binary update, worked by hand -----------------------------------------

def test_update_binary_yes_hand_calculation():
    #   A: 0.5 * 0.8 = 0.40     B: 0.5 * 0.2 = 0.10
    #   total 0.50  ->  A = 0.8, B = 0.2
    out = B.update_binary({"A": 0.5, "B": 0.5}, {"A": 0.8, "B": 0.2}, True)
    assert out["A"] == pytest.approx(0.8)
    assert out["B"] == pytest.approx(0.2)


def test_update_binary_no_hand_calculation():
    #   A: 0.5 * 0.2 = 0.10     B: 0.5 * 0.8 = 0.40
    out = B.update_binary({"A": 0.5, "B": 0.5}, {"A": 0.8, "B": 0.2}, False)
    assert out["A"] == pytest.approx(0.2)
    assert out["B"] == pytest.approx(0.8)


def test_missing_cell_behaves_exactly_like_base_rate():
    blank = B.update_binary({"A": 0.5, "B": 0.5}, {"A": 0.8}, True)
    spelt = B.update_binary({"A": 0.5, "B": 0.5},
                            {"A": 0.8, "B": B.BASE_RATE}, True)
    assert blank["A"] == pytest.approx(spelt["A"])


def test_update_is_order_independent():
    """Two findings applied in either order give the same belief."""
    b = {"A": 0.5, "B": 0.3, "C": 0.2}
    r1, r2 = {"A": 0.9, "B": 0.1, "C": 0.5}, {"A": 0.2, "B": 0.8, "C": 0.4}
    ab = B.update_binary(B.update_binary(b, r1, True), r2, False)
    ba = B.update_binary(B.update_binary(b, r2, False), r1, True)
    for d in ab:
        assert ab[d] == pytest.approx(ba[d])


# -- information gain ------------------------------------------------------

def test_useless_question_has_zero_gain():
    """Every condition equally likely to have it -> learns nothing."""
    gain = B.info_gain_binary({"A": 0.5, "B": 0.5}, {"A": 0.5, "B": 0.5})
    assert gain == pytest.approx(0.0, abs=1e-9)


def test_perfect_question_gains_exactly_one_bit():
    gain = B.info_gain_binary({"A": 0.5, "B": 0.5}, {"A": 1.0, "B": 0.0})
    assert gain == pytest.approx(1.0)


def test_binary_gain_can_never_exceed_one_bit():
    """A two-way answer can at best halve the space. Hard ceiling."""
    b = {k: 0.25 for k in "ABCD"}
    for row in ({"A": 1, "B": 1, "C": 0, "D": 0},
                {"A": .9, "B": .1, "C": .5, "D": .3}):
        assert B.info_gain_binary(b, row) <= 1.0 + 1e-9


def test_gain_is_never_negative():
    b = {"A": 0.7, "B": 0.2, "C": 0.1}
    for row in ({"A": .9, "B": .1, "C": .5}, {"A": .01, "B": .99, "C": .5}):
        assert B.info_gain_binary(b, row) >= -1e-9


# -- multi-way -------------------------------------------------------------

def test_choice_update_hand_calculation():
    rows = {"A": [0.8, 0.2], "B": [0.1, 0.9]}
    out = B.update_choice({"A": 0.5, "B": 0.5}, rows, 0)
    #   A: 0.5*0.8 = 0.40   B: 0.5*0.1 = 0.05   total 0.45
    assert out["A"] == pytest.approx(0.40 / 0.45)


def test_choice_gain_can_exceed_one_bit():
    """Why a multi-option question beats every yes/no question."""
    four = {k: 0.25 for k in "ABCD"}
    rows = {d: [1.0 if i == j else 0.0 for j in range(4)]
            for i, d in enumerate("ABCD")}
    assert B.info_gain_choice(four, rows, 4) == pytest.approx(2.0)


# -- the property that drives question ordering ----------------------------

def test_gain_depends_on_belief_not_on_the_row_alone():
    """The same question is worthless early and valuable later.

    A finding that only separates a rare candidate scores near zero while
    that candidate is rare, and rises once belief concentrates on it.
    """
    row = {"common": 0.02, "rare": 0.60}
    early = B.info_gain_binary({"common": 0.98, "rare": 0.02}, row)
    later = B.info_gain_binary({"common": 0.60, "rare": 0.40}, row)
    assert later > early * 5
