"""The consultation loop.

Pick the most informative question, ask it, update the belief, decide when
to stop. No LLM involved - the rulebook is already on disk by this point.
"""

from engine import bayes as B

# ---- every threshold lives here, nowhere else ----------------------------
STOP_CONFIDENCE = 0.85   # top candidate this far ahead -> confident
STOP_RESIDUAL   = 0.05   # ...but only stop if nothing useful is left to ask
MIN_GAIN        = 0.01   # below this, a question teaches us nothing
MAX_QUESTIONS   = 15


class Consultation:
    def __init__(self, rulebook, max_questions=MAX_QUESTIONS):
        self.rb = rulebook
        self.max_questions = max_questions
        self.belief = rulebook.prior()
        self.asked = set()
        self.findings = {}     # finding -> "present" | "absent" | option | "not_stated"
        self.log = []

    # -- scoring -----------------------------------------------------------

    def gain(self, fid):
        if self.rb.is_choice(fid):
            return B.info_gain_choice(self.belief, self.rb.choice_rows(fid),
                                      len(self.rb.options(fid)))
        return B.info_gain_binary(self.belief, self.rb.row(fid))

    def candidates(self):
        """[(finding, gain)] best first. Choice and yes/no compete on the
        same axis - bits are bits."""
        out = [(f, self.gain(f)) for f in self.rb.all_findings()
               if f not in self.asked]
        return sorted(out, key=lambda x: -x[1])

    def next_question(self):
        c = self.candidates()
        if not c or c[0][1] < MIN_GAIN:
            return None
        return c[0]

    # -- stopping ----------------------------------------------------------

    def best_residual_gain(self):
        c = self.candidates()
        return c[0][1] if c else 0.0

    def should_stop(self):
        if len(self.asked) >= self.max_questions:
            return True, "question budget reached"
        if self.best_residual_gain() < MIN_GAIN:
            return True, "nothing left that would teach us anything"
        top = max(self.belief.values())
        if top >= STOP_CONFIDENCE and self.best_residual_gain() < STOP_RESIDUAL:
            return True, f"confident ({top:.0%}) and nothing useful left to ask"
        return False, None

    # -- answering ---------------------------------------------------------

    def answer(self, fid, value):
        """value: True/False for yes-no, an option index for choice,
        None for "I don't know" - which updates NOTHING."""
        before = dict(self.belief)
        self.asked.add(fid)

        if value is None:
            status = "not_stated"
        elif self.rb.is_choice(fid):
            self.belief = B.update_choice(self.belief,
                                          self.rb.choice_rows(fid), value)
            status = self.rb.options(fid)[value]
        else:
            self.belief = B.update_binary(self.belief, self.rb.row(fid),
                                          bool(value))
            status = "present" if value else "absent"

        self.findings[fid] = status
        self.log.append({
            "n": len(self.asked), "finding": fid, "answer": status,
            "entropy_before": B.entropy(before),
            "entropy_after": B.entropy(self.belief),
            "top": B.rank(self.belief)[0],
        })
        return status

    def ranked(self, n=None):
        r = B.rank(self.belief)
        return r[:n] if n else r

    def flagged(self, threshold=0.05):
        """must_not_miss conditions still carrying real probability."""
        return [(c, p) for c, p in self.ranked()
                if self.rb.must_not_miss(c) and p >= threshold]
