"""Every rulebook on disk must load and be usable.

This is the test that would have caught the real bug we hit: a generated
rulebook where a condition referenced a choice finding ('duration') that was
never defined in the findings list. It crashed at load time, after already
being written to disk.

Runs offline. No API key needed.
"""

import pytest
from conftest import ROOT

from engine import bayes as B
from engine import rulebook as RB
from engine.consult import Consultation

KB_DIRS = [ROOT / "kb" / "generated", ROOT / "kb" / "reviewed"]


def all_rulebook_paths():
    out = []
    for d in KB_DIRS:
        if d.is_dir():
            out += sorted(p for p in d.iterdir() if p.is_dir())
    return out


PATHS = all_rulebook_paths()
IDS = [p.name for p in PATHS]


def test_at_least_one_rulebook_ships():
    assert PATHS, "no rulebooks found - the repo should ship at least one example"


@pytest.mark.parametrize("path", PATHS, ids=IDS)
def test_rulebook_loads(path):
    """Catches unknown finding ids, distributions that don't sum to 1,
    priors out of range, and malformed YAML."""
    RB.load(path)


@pytest.mark.parametrize("path", PATHS, ids=IDS)
def test_every_referenced_finding_exists(path):
    """The cross-reference check. Pydantic validates each field's shape but
    cannot verify a condition only mentions findings that were defined."""
    rb = RB.load(path)
    known = set(rb.findings)
    for cid, c in rb.conditions.items():
        for fid in c.get("findings", {}):
            assert fid in known, f"{cid} references undefined finding {fid!r}"
        for fid in c.get("choices", {}):
            assert fid in known, f"{cid} references undefined choice {fid!r}"
            assert rb.is_choice(fid), f"{cid}: {fid!r} is not a choice finding"


@pytest.mark.parametrize("path", PATHS, ids=IDS)
def test_priors_are_a_distribution(path):
    rb = RB.load(path)
    assert sum(rb.prior().values()) == pytest.approx(1.0)


@pytest.mark.parametrize("path", PATHS, ids=IDS)
def test_consultation_runs_to_completion(path):
    """Drive a full consultation answering 'no' to everything. It must
    terminate, and never produce a belief that stops summing to 1."""
    rb = RB.load(path)
    c = Consultation(rb)
    turns = 0
    while turns < 50:
        stop, _ = c.should_stop()
        if stop:
            break
        nxt = c.next_question()
        if nxt is None:
            break
        fid, _gain = nxt
        c.answer(fid, 0 if rb.is_choice(fid) else False)
        assert sum(c.belief.values()) == pytest.approx(1.0)
        turns += 1
    assert turns < 50, "consultation did not terminate"
    assert c.ranked(), "no ranked result"


@pytest.mark.parametrize("path", PATHS, ids=IDS)
def test_dont_know_changes_nothing(path):
    rb = RB.load(path)
    c = Consultation(rb)
    fid, _ = c.next_question()
    before = dict(c.belief)
    c.answer(fid, None)
    assert c.belief == before
    assert c.findings[fid] == "not_stated"


@pytest.mark.parametrize("path", PATHS, ids=IDS)
def test_every_finding_has_question_and_definition(path):
    rb = RB.load(path)
    for fid in rb.all_findings():
        assert rb.question(fid), f"{fid} has no patient-facing question"
        assert rb.definition(fid), f"{fid} has no definition"
