#!/usr/bin/env python3
"""Ada-style symptom checker.

Claude writes the rulebook once per complaint category.
The engine then runs the consultation with no model involved.
"""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine import bayes as B
from engine import rulebook as RB
from engine.consult import Consultation
from llm import categories as CATS

BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"
RED, GRN, YEL = "\033[31m", "\033[32m", "\033[33m"


def ask(msg):
    try:
        return input(msg).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)


def show_belief(c, prev=None, n=5):
    print()
    for cid, p in c.ranked(n):
        if p < 0.01:
            continue
        delta = ""
        if prev and cid in prev:
            d = (p - prev[cid]) * 100
            if abs(d) >= 1:
                delta = f"  {'^' if d > 0 else 'v'}{d:+5.1f}"
        flag = f" {RED}(!){RESET}" if c.rb.must_not_miss(cid) else ""
        bar = "#" * int(round(p * 26))
        print(f"   {c.rb.name(cid):<34}{p:>5.0%} {bar:<26}{DIM}{delta}{RESET}{flag}")
    print(f"{DIM}   {B.entropy(c.belief):.2f} bits -> "
          f"{B.effective_options(c.belief):.1f} options still in play{RESET}")


def ask_finding(c, fid, show_why, gain):
    rb = c.rb
    print(f"\n{BOLD}{rb.question(fid)}{RESET}")
    if show_why:
        kind = f"choice/{len(rb.options(fid))}" if rb.is_choice(fid) else "yes/no"
        print(f"{DIM}   [{kind}]  {gain:.3f} bits{RESET}")

    if rb.is_choice(fid):
        opts = rb.options(fid)
        for i, o in enumerate(opts, 1):
            print(f"     {i}. {rb.option_label(fid, i - 1)}")
        while True:
            r = ask(f"   [1-{len(opts)}] / [?] don't know / [d]efine / [q]uit > ").lower()
            if r in ("?", ""):
                return None
            if r == "q":
                sys.exit(0)
            if r == "d":
                print(f"{DIM}   {rb.definition(fid)}{RESET}")
                continue
            if r.isdigit() and 1 <= int(r) <= len(opts):
                return int(r) - 1
    else:
        while True:
            r = ask("   [y]es / [n]o / [?] don't know / [d]efine / [q]uit > ").lower()
            if r in ("y", "yes"):
                return True
            if r in ("n", "no"):
                return False
            if r in ("?", ""):
                return None
            if r == "q":
                sys.exit(0)
            if r == "d":
                print(f"{DIM}   {rb.definition(fid)}{RESET}")


# ------------------------------------------------------------------ commands

def cmd_categories():
    print(f"\n{BOLD}DIFFERENTIAL{RESET}{DIM} - loads a rulebook, asks questions{RESET}")
    for c, m in CATS.CATEGORIES.items():
        if m["kind"] != CATS.DIFFERENTIAL:
            continue
        sx = f"  {DIM}[sex-specific]{RESET}" if m["sex_specific"] else ""
        print(f"\n   {BOLD}{c}{RESET}{sx}")
        print(f"   {DIM}{m['covers']}{RESET}")
    print(f"\n\n{BOLD}ROUTE{RESET}{DIM} - no questions, hands off{RESET}")
    for c, m in CATS.CATEGORIES.items():
        if m["kind"] != CATS.ROUTE:
            continue
        print(f"\n   {BOLD}{c}{RESET}")
        print(f"   {DIM}{m['covers']}{RESET}")
    print()


def cmd_list():
    for root in (str(ROOT / "kb" / "reviewed"), str(ROOT / "kb" / "generated")):
        if not os.path.isdir(root):
            continue
        keys = sorted(d for d in os.listdir(root)
                      if os.path.isdir(os.path.join(root, d)))
        print(f"\n{BOLD}kb/{os.path.basename(root)}/{RESET}  ({len(keys)})")
        for k in keys:
            try:
                rb = RB.load(os.path.join(root, k))
                print(f"   {k:<44} {len(rb.conditions)} conditions, "
                      f"{len(rb.all_findings())} findings")
            except Exception as e:
                print(f"   {k:<44} {RED}broken: {e}{RESET}")
    print()


def cmd_inspect(key):
    path = None
    for root in (str(ROOT / "kb" / "reviewed"), str(ROOT / "kb" / "generated")):
        if os.path.isdir(os.path.join(root, key)):
            path = os.path.join(root, key)
    if not path:
        sys.exit(f"no rulebook '{key}' - try: python cli.py --list")

    rb = RB.load(path)
    print(f"\n{BOLD}{path}{RESET}")
    print(f"{DIM}   {rb.meta.get('generated_by','?')} on "
          f"{rb.meta.get('generated_at','?')} - {rb.meta.get('status','?')}{RESET}")
    print(f"\n{BOLD}conditions{RESET}")
    for cid, p in B.rank(rb.prior()):
        flag = f" {RED}must-not-miss{RESET}" if rb.must_not_miss(cid) else ""
        print(f"   {rb.name(cid):<36}{p:>6.1%}{flag}")
    print(f"\n{BOLD}findings{RESET}")
    for f in rb.all_findings():
        k = f"choice/{len(rb.options(f))}" if rb.is_choice(f) else "yes/no"
        print(f"   [{k:<9}] {rb.question(f)}")
    print(f"\n{BOLD}health - does every condition have a discriminator?{RESET}")
    for cid, fid, margin in RB.health_report(rb):
        warn = f"  {RED}<- WEAK{RESET}" if margin < 0.20 else ""
        print(f"   {rb.name(cid):<36}{str(fid):<30}+{margin:.2f}{warn}")
    print(f"\n{DIM}   base entropy {B.entropy(rb.prior()):.2f} bits -> "
          f"{B.effective_options(rb.prior()):.1f} effective options{RESET}\n")


def show_route(category, meta):
    """Screening and follow-up visits have nothing to narrow. Running a
    symptom differential on them would produce confident nonsense."""
    print(f"\n{YEL}{BOLD}{meta.get('label', category)}{RESET}\n")
    for sentence in CATS.route_message(category).split(". "):
        if sentence.strip():
            print(f"   {sentence.strip().rstrip('.')}.")
    print(f"\n{DIM}   No questions asked - a symptom differential cannot "
          f"answer this.{RESET}\n")


# ---------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--complaint", help="skip the prompt, e.g. 'my head feels dizzy'")
    ap.add_argument("--sex", choices=["female", "male"])
    ap.add_argument("--age", type=int)
    ap.add_argument("--category", help="skip classification, e.g. dizziness")
    ap.add_argument("--why", action="store_true", help="show information gain per question")
    ap.add_argument("--categories", action="store_true", help="list complaint categories")
    ap.add_argument("--list", action="store_true", help="list rulebooks on disk")
    ap.add_argument("--inspect", metavar="KEY", help="show one rulebook in detail")
    a = ap.parse_args()

    if a.categories:
        return cmd_categories()
    if a.list:
        return cmd_list()
    if a.inspect:
        return cmd_inspect(a.inspect)

    from llm import generate as G

    complaint = a.complaint or ask("\nWhat's bothering you? > ")
    sex = a.sex
    while sex not in ("female", "male"):
        sex = ask("Sex [female/male] > ").lower()
    age = a.age
    while not age:
        try:
            age = int(ask("Age > "))
        except ValueError:
            pass

    # 1. which category of complaint is this?
    if a.category:
        category, conf, why_cat = a.category, 1.0, "given on the command line"
    else:
        from llm.classify import classify
        print(f"{DIM}  classifying ...{RESET}")
        r = classify(complaint, verbose=True)
        category, conf, why_cat = r.category, r.confidence, r.reason
        if r.alternate:
            why_cat += f"   (alternate: {r.alternate})"

    meta = CATS.CATEGORIES.get(category, {})
    print(f"{DIM}  category: {category}  ({conf:.0%} confident) - {why_cat}{RESET}")

    # 2. not every complaint is a differential
    if not CATS.is_differential(category):
        return show_route(category, meta)

    key, band = G.key_for(category, sex, age)
    print(f"{DIM}  rulebook key: {key}{RESET}")

    # 3. do we already have a rulebook for it?
    path = G.find_existing(key)
    if path:
        print(f"{GRN}  found existing rulebook: {path}{RESET}")
    else:
        print(f"{DIM}  no rulebook yet - generating one{RESET}")
        path = G.generate(category, sex, age)

    rb = RB.load(path)

    # 4. run the consultation. No model from here on.
    c = Consultation(rb)
    print(f"\n{DIM}  {len(rb.conditions)} conditions in play. "
          f"Starting from population priors.{RESET}")
    show_belief(c)

    while True:
        stop, why = c.should_stop()
        if stop:
            break
        nxt = c.next_question()
        if nxt is None:
            why = "nothing left worth asking"
            break
        fid, gain = nxt
        prev = dict(c.belief)
        c.answer(fid, ask_finding(c, fid, a.why, gain))
        show_belief(c, prev)

    print(f"\n{BOLD}Stopped after {len(c.asked)} questions{RESET} {DIM}- {why}{RESET}\n")
    for i, (cid, p) in enumerate(c.ranked(3), 1):
        print(f"   {i}. {rb.name(cid):<34}{p:>6.1%}")

    flagged = c.flagged()
    if flagged:
        print(f"\n   {RED}Serious conditions not ruled out:{RESET}")
        for cid, p in flagged:
            print(f"     {rb.name(cid)}  {p:.0%}")

    unknown = sum(1 for v in c.findings.values() if v == "not_stated")
    print(f"\n{DIM}   {len(c.findings) - unknown} answered, {unknown} unknown{RESET}")
    print(f"{DIM}   Prototype. Machine-written knowledge base, "
          f"not clinically reviewed.{RESET}\n")


if __name__ == "__main__":
    main()
