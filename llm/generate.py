"""Ask Claude Opus 5 for a rulebook, validate it, write it to kb/generated/.

This is the ONLY place in the project that calls a model for medical content.
It runs once per (category, sex, age band) - never during a consultation.
"""

import os
import time
from pathlib import Path

import yaml

from llm.client import get_client, MODEL_GENERATE
from llm.prompt import build
from llm.schema import GeneratedRulebook

ROOT = Path(__file__).resolve().parents[1]
KB_GENERATED = str(ROOT / "kb" / "generated")
KB_REVIEWED = str(ROOT / "kb" / "reviewed")


def _structural_problems(rb):
    """Errors that make a rulebook UNUSABLE. Checked before writing to disk.

    Pydantic validates each field's shape but cannot check that a condition
    only references findings that actually exist - that is a cross-reference,
    and getting it wrong means the rulebook will not load at all.
    """
    noul = {f.id for f in rb.findings if f.type == "noul"}
    choice = {f.id: len(f.options or []) for f in rb.findings
              if f.type == "choice"}
    problems = []

    for c in rb.conditions:
        for cell in c.cells:
            if cell.finding not in noul:
                problems.append(
                    f"condition '{c.id}' references yes/no finding "
                    f"'{cell.finding}' which is not in your findings list")
        for cd in c.choices:
            if cd.finding not in choice:
                problems.append(
                    f"condition '{c.id}' references choice finding "
                    f"'{cd.finding}' which is not in your findings list")
                continue
            n = choice[cd.finding]
            if len(cd.distribution) != n:
                problems.append(
                    f"condition '{c.id}' gives {len(cd.distribution)} numbers "
                    f"for '{cd.finding}' which has {n} options")
            elif abs(sum(cd.distribution) - 1.0) > 1e-6:
                problems.append(
                    f"condition '{c.id}' distribution for '{cd.finding}' sums "
                    f"to {sum(cd.distribution):.3f}, must be exactly 1.0")

    # every choice finding needs a distribution from every condition that
    # mentions it, else the engine silently uses a uniform fallback
    return problems


def _weak_conditions(rb):
    """Conditions with no finding where they beat every rival. A quality
    problem, not a correctness one - we warn rather than regenerate."""
    noul = {f.id for f in rb.findings if f.type == "noul"}
    best = {c.id: 0.0 for c in rb.conditions}
    for fid in noul:
        vals = {c.id: next((x.p for x in c.cells if x.finding == fid), 0.05)
                for c in rb.conditions}
        for cid, p in vals.items():
            rival = max((v for k, v in vals.items() if k != cid), default=0)
            if p > rival:
                best[cid] = max(best[cid], p - rival)
    return [cid for cid, m in best.items() if m <= 0.0]


# Clinically meaningful age bands, NOT decades.
#
# The old decade banding put a cliff between 39 and 40 that meant nothing
# medically, and another at 29/30, and another at 49/50. These boundaries
# are where disease priors genuinely shift - cardiovascular risk, cancer
# risk and degenerative disease all change around 40 and again around 65.
# Fewer bands also means far better cache hit rates.
AGE_BANDS = [
    (0, 12, "child"),
    (13, 17, "teen"),
    (18, 39, "18-39"),
    (40, 64, "40-64"),
    (65, 200, "65plus"),
]


def age_band(age):
    for lo, hi, name in AGE_BANDS:
        if lo <= int(age) <= hi:
            return name
    return "18-39"


def key_for(category, sex, age):
    """Cache key: category__sex__ageband

    Sex collapses to 'any' for categories that present the same way in both,
    which halves how many rulebooks ever need generating.
    """
    from llm.categories import sex_specific
    band = age_band(age)
    s = sex if sex_specific(category) else "any"
    return f"{category}__{s}__{band}", band


def find_existing(key):
    """Reviewed rulebooks always win over generated ones."""
    for root in (KB_REVIEWED, KB_GENERATED):
        p = os.path.join(root, key)
        if os.path.isdir(p):
            return p
    return None


def generate(category, sex, age, verbose=True, effort="medium",
             retry=True, _extra=""):
    """Call Claude, write YAML, return the folder path."""
    key, band = key_for(category, sex, age)
    from llm.categories import CATEGORIES
    meta = CATEGORIES.get(category, {})
    system, user = build(category, sex, band,
                         meta.get("label", category),
                         meta.get("covers", ""))

    client = get_client()

    # Streaming, for two reasons:
    #   1. a non-streamed request with max_tokens=16000 blocks with no output
    #      and can hit the SDK's HTTP timeout on a long generation
    #   2. it lets us show progress, so a 40s wait does not look like a hang
    #
    # effort="medium" because writing a table from recalled medical knowledge
    # is not deep reasoning. "high" (the default) roughly doubles the time for
    # little gain here. Raise it if generated rulebooks come out weak.
    t0 = time.time()
    chars = 0
    spin = "|/-\\"
    with client.messages.stream(
        model=MODEL_GENERATE,
        max_tokens=16000,
        system=system,
        messages=[{"role": "user", "content": user + _extra}],
        output_config={"effort": effort},
        output_format=GeneratedRulebook,
    ) as stream:
        for event in stream:
            if getattr(event, "type", "") == "text" and verbose:
                chars += len(getattr(event, "text", ""))
                el = time.time() - t0
                print(f"\r  {spin[int(el * 4) % 4]} writing rulebook ... "
                      f"{chars:,} chars  {el:.0f}s", end="", flush=True)
        resp = stream.get_final_message()
    if verbose:
        print(f"\r  done in {time.time() - t0:.0f}s" + " " * 30)

    rb = getattr(resp, "parsed_output", None)
    if rb is None:   # older SDKs don't attach parsed_output to a stream result
        text = "".join(b.text for b in resp.content if b.type == "text")
        rb = GeneratedRulebook.model_validate_json(text)

    # Structural errors make the rulebook unloadable. Retry once with the
    # exact failures fed back - the model fixes these reliably when told.
    problems = _structural_problems(rb)
    if problems and retry:
        if verbose:
            print(f"  {len(problems)} structural problem(s), regenerating:")
            for p_ in problems[:4]:
                print(f"    - {p_}")
        fix = ("\n\nYour previous attempt had these errors. Fix them:\n  "
               + "\n  ".join(problems) +
               "\n\nEvery finding a condition references MUST appear in the "
               "findings list with a matching id and type.")
        return generate(category, sex, age, verbose=verbose, effort=effort,
                        _extra=fix, retry=False)
    if problems:
        raise SystemExit(f"  rulebook still broken after retry:\n    "
                         + "\n    ".join(problems))

    path = os.path.join(KB_GENERATED, key)
    _write(path, rb, resp, category, sex, band)

    weak = _weak_conditions(rb)
    if weak and verbose:
        print(f"  note: no clear discriminator for {', '.join(weak)}")
        print(f"        usable, but check with --inspect {key}")

    if verbose:
        u = resp.usage
        print(f"  wrote {len(rb.conditions)} conditions, {len(rb.findings)} "
              f"findings -> {path}")
        print(f"  tokens in={u.input_tokens} out={u.output_tokens}")
    return path


def _write(path, rb, resp, category, sex, band):
    import datetime
    os.makedirs(os.path.join(path, "conditions"), exist_ok=True)

    with open(os.path.join(path, "meta.yaml"), "w") as f:
        yaml.safe_dump({
            "category": category, "sex": sex, "age_band": band,
            "status": "generated",
            "generated_by": resp.model,
            "generated_at": datetime.date.today().isoformat(),
            "request_id": getattr(resp, "_request_id", None),
            "warning": "Machine-written. NOT clinically reviewed.",
        }, f, sort_keys=False)

    findings = {}
    for fd in rb.findings:
        entry = {"type": fd.type, "question": fd.question,
                 "definition": fd.definition}
        if fd.type == "choice" and fd.options:
            entry["options"] = {o.id: o.label for o in fd.options}
        findings[fd.id] = entry
    with open(os.path.join(path, "findings.yaml"), "w") as f:
        yaml.safe_dump(findings, f, sort_keys=False, default_flow_style=False)

    for c in rb.conditions:
        doc = {"id": c.id, "name": c.name, "prior": round(c.prior, 4),
               "must_not_miss": c.must_not_miss,
               "choices": {cd.finding: [round(x, 4) for x in cd.distribution]
                           for cd in c.choices},
               "findings": {cell.finding:
                            ({"p": round(cell.p, 3), "note": cell.note}
                             if cell.note else {"p": round(cell.p, 3)})
                            for cell in c.cells}}
        with open(os.path.join(path, "conditions", f"{c.id}.yaml"), "w") as f:
            yaml.safe_dump(doc, f, sort_keys=False, default_flow_style=False)
