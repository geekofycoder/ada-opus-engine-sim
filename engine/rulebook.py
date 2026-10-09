"""Loads a rulebook from disk and hands the engine plain numbers.

A rulebook is one folder under kb/. It holds everything needed to run a
consultation for one complaint category:

    kb/generated/head_dizziness__female__30-39/
        meta.yaml          who wrote it, when, which model
        findings.yaml      the questions, in patient-facing words
        conditions/*.yaml  one file per condition - P(finding | condition)

Nothing in this file knows Claude exists.
"""

import os
import yaml

from engine.bayes import BASE_RATE


class RulebookError(Exception):
    pass


class Rulebook:
    def __init__(self, path, meta, findings, conditions):
        self.path = path
        self.meta = meta
        self.findings = findings        # id -> {type, question, definition, options?}
        self.conditions = conditions    # id -> {name, prior, choices, findings}

    # -- what kind of question is this -------------------------------------

    def is_choice(self, fid):
        return self.findings[fid]["type"] == "choice"

    def options(self, fid):
        return list(self.findings[fid]["options"].keys())

    def option_label(self, fid, index):
        opts = self.findings[fid]["options"]
        key = list(opts)[index]
        return opts[key] or key

    def question(self, fid):
        return self.findings[fid]["question"]

    def definition(self, fid):
        return self.findings[fid].get("definition", "")

    def binary_findings(self):
        return [f for f, m in self.findings.items() if m["type"] == "noul"]

    def choice_findings(self):
        return [f for f, m in self.findings.items() if m["type"] == "choice"]

    def all_findings(self):
        return self.choice_findings() + self.binary_findings()

    # -- the numbers -------------------------------------------------------

    def prior(self):
        total = sum(c["prior"] for c in self.conditions.values())
        return {cid: c["prior"] / total for cid, c in self.conditions.items()}

    def row(self, fid):
        """{condition: P(finding | condition)}. Blank cells -> BASE_RATE."""
        return {
            cid: c.get("findings", {}).get(fid, {}).get("p", BASE_RATE)
            for cid, c in self.conditions.items()
        }

    def choice_rows(self, fid):
        """{condition: [p_opt0, ...]}. A condition with no opinion gets uniform."""
        n = len(self.options(fid))
        uniform = [1.0 / n] * n
        return {
            cid: c.get("choices", {}).get(fid, uniform)
            for cid, c in self.conditions.items()
        }

    def name(self, cid):
        return self.conditions[cid]["name"]

    def must_not_miss(self, cid):
        return bool(self.conditions[cid].get("must_not_miss", False))


def load(path):
    """Read one rulebook folder."""
    def _read(p):
        with open(p) as f:
            return yaml.safe_load(f)

    if not os.path.isdir(path):
        raise RulebookError(f"no rulebook at {path}")

    meta = _read(os.path.join(path, "meta.yaml"))
    findings = _read(os.path.join(path, "findings.yaml"))

    conditions = {}
    cdir = os.path.join(path, "conditions")
    for fn in sorted(os.listdir(cdir)):
        if fn.endswith(".yaml"):
            c = _read(os.path.join(cdir, fn))
            conditions[c["id"]] = c

    rb = Rulebook(path, meta, findings, conditions)
    validate(rb)
    return rb


def validate(rb):
    """Catch a malformed rulebook at load time, not mid-consultation."""
    if not rb.conditions:
        raise RulebookError(f"{rb.path}: no conditions")

    for fid, m in rb.findings.items():
        if m.get("type") not in ("noul", "choice"):
            raise RulebookError(f"{fid}: type must be 'noul' or 'choice'")
        if m["type"] == "choice" and not m.get("options"):
            raise RulebookError(f"{fid}: choice finding has no options")

    for cid, c in rb.conditions.items():
        if not 0 < c.get("prior", 0) <= 1:
            raise RulebookError(f"{cid}: prior out of range")

        for fid, dist in c.get("choices", {}).items():
            if fid not in rb.findings:
                raise RulebookError(f"{cid}: unknown choice finding '{fid}'")
            n = len(rb.options(fid))
            if len(dist) != n:
                raise RulebookError(f"{cid}.{fid}: {len(dist)} entries, expected {n}")
            if abs(sum(dist) - 1.0) > 1e-6:
                raise RulebookError(f"{cid}.{fid}: sums to {sum(dist):.3f}, must be 1.0")

        for fid, cell in c.get("findings", {}).items():
            if fid not in rb.findings:
                raise RulebookError(f"{cid}: unknown finding '{fid}'")
            p = cell.get("p")
            if p is None or not 0 <= p <= 1:
                raise RulebookError(f"{cid}.{fid}: p={p} out of range")


def health_report(rb):
    """Every condition should have at least one cell where it beats every
    rival. Without one it can only be reached by elimination, which is slow
    and fragile. Returns [(condition, best_finding, margin)]."""
    out = []
    for cid in rb.conditions:
        best = None
        for fid in rb.binary_findings():
            row = rb.row(fid)
            p = row[cid]
            rival = max((row[o] for o in rb.conditions if o != cid), default=0)
            if p > rival and (best is None or p - rival > best[1]):
                best = (fid, p - rival)
        for fid in rb.choice_findings():
            rows = rb.choice_rows(fid)
            for i, opt in enumerate(rb.options(fid)):
                p = rows[cid][i]
                rival = max((rows[o][i] for o in rb.conditions if o != cid), default=0)
                if p > rival and (best is None or p - rival > best[1]):
                    best = (f"{fid}={opt}", p - rival)
        out.append((cid, best[0] if best else None, best[1] if best else 0.0))
    return sorted(out, key=lambda x: x[2])
