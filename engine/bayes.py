"""Pure Bayesian maths. No LLM, no network, no files, no medicine.

Three ideas:
  1. belief   = {condition: probability}, always sums to 1
  2. update   = reweight each condition by how well it predicted the answer
  3. info_gain = how much confusion a question would remove, worked out BEFORE
                 asking it
"""

from math import log2

# A blank cell in a rulebook means "nothing unusual here".
BASE_RATE = 0.05


def normalize(weights):
    """Rescale so the values sum to 1."""
    total = sum(weights.values())
    if total <= 0:
        n = len(weights) or 1
        return {k: 1.0 / n for k in weights}
    return {k: v / total for k, v in weights.items()}


def entropy(belief):
    """Confusion in bits. 2**entropy = how many options you're torn between."""
    return -sum(p * log2(p) for p in belief.values() if p > 0)


def effective_options(belief):
    """The readable version of entropy."""
    return 2 ** entropy(belief)


def rank(belief):
    """[(condition, probability)] most likely first."""
    return sorted(belief.items(), key=lambda kv: -kv[1])


# ---------------------------------------------------------------- yes / no

def update_binary(belief, row, answer_yes):
    """row = {condition: P(finding | condition)}

    YES -> multiply by p.   NO -> multiply by (1 - p).   Then rescale.
    """
    return normalize({
        c: belief[c] * (row.get(c, BASE_RATE) if answer_yes
                        else 1.0 - row.get(c, BASE_RATE))
        for c in belief
    })


def info_gain_binary(belief, row):
    """Expected drop in entropy. Can never exceed 1.0 bit - a two-way answer
    can at best halve the candidate space."""
    p_yes = sum(belief[c] * row.get(c, BASE_RATE) for c in belief)
    if p_yes <= 1e-9 or p_yes >= 1 - 1e-9:
        return 0.0
    return entropy(belief) - (
        p_yes * entropy(update_binary(belief, row, True))
        + (1 - p_yes) * entropy(update_binary(belief, row, False))
    )


# ------------------------------------------------------------- multi-choice

def update_choice(belief, rows, option_index):
    """rows = {condition: [p_opt0, p_opt1, ...]}, each list summing to 1."""
    return normalize({
        c: belief[c] * rows[c][option_index] for c in belief if c in rows
    })


def info_gain_choice(belief, rows, n_options):
    """Can exceed 1.0 bit. A 5-option question has five doors, not two -
    which is why 'where is the pain' usually wins turn 1."""
    after = 0.0
    for k in range(n_options):
        pk = sum(belief[c] * rows[c][k] for c in belief if c in rows)
        if pk > 1e-9:
            after += pk * entropy(update_choice(belief, rows, k))
    return entropy(belief) - after
