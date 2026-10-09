"""Free text -> one complaint category, with a confidence we can act on.

Uses Opus 5. It is more expensive than Haiku (~$0.004 vs ~$0.0002 a call)
but this is the single most dangerous step in the system: a wrong category
sends the patient into the wrong rulebook, and everything after that is
confidently wrong. Revisit once there is performance data to compare.
"""

from typing import Optional
from pydantic import BaseModel, Field

from llm.client import get_client, MODEL_CLASSIFY
from llm import categories as C

# Below this, we do not trust the pick. Tune once there is real data.
MIN_CONFIDENCE = 0.60

SYSTEM = """You route a patient's complaint to ONE category.

Pick the category describing WHAT THE PATIENT SAID, not what you suspect
they have. A patient saying "always tired" goes to fatigue_weakness even if
you think it is thyroid - the engine works that out from there.

Three rules that matter more than the rest:

1. If they describe NO symptoms and just want a check-up or bloods done,
   that is asymptomatic_screening. Conditions like high cholesterol are
   silent - questions cannot find them.

2. If they already have a diagnosis and are here for review, a refill, or
   their numbers checked, that is chronic_followup. Not a new problem.

3. If the complaint is too vague to place, or sits outside every category,
   return unclear with low confidence. Do NOT force a guess - a wrong
   category is worse than admitting you do not know.

confidence is your honest probability that this is the right category:
  0.9+  the complaint names the area plainly
  0.7   likely, but phrased loosely
  0.5   could as easily be the alternate
  0.3   guessing
"""


class Classification(BaseModel):
    category: str = Field(description="exactly one category id from the list")
    confidence: float = Field(ge=0, le=1,
        description="honest probability this is the right category")
    alternate: Optional[str] = Field(default=None,
        description="next most likely category id, or null")
    reason: str = Field(description="one short sentence")


def classify(text, verbose=False):
    """Returns a Classification. Never raises on a bad pick - falls back
    to 'unclear', which the CLI handles as a route rather than a diagnosis."""
    client = get_client()
    resp = client.messages.parse(
        model=MODEL_CLASSIFY,
        max_tokens=2000,
        system=SYSTEM,
        messages=[{"role": "user",
                   "content": f"Patient said: {text!r}\n\n"
                              f"CATEGORIES:\n\n{C.prompt_block()}"}],
        output_format=Classification,
    )
    r = resp.parsed_output

    if r.category not in C.CATEGORIES:
        return Classification(category="unclear", confidence=0.0,
                              alternate=None,
                              reason=f"model returned unknown id {r.category!r}")

    # Gap fix: a low-confidence pick is not trusted. Sending a patient into
    # the wrong rulebook produces a confident wrong answer with no warning.
    if r.confidence < MIN_CONFIDENCE and r.category != "unclear":
        if verbose:
            print(f"  low confidence ({r.confidence:.2f}) on "
                  f"{r.category} - treating as unclear")
        return Classification(category="unclear", confidence=r.confidence,
                              alternate=r.category,
                              reason=f"best guess was {r.category} but only "
                                     f"{r.confidence:.0%} sure")
    return r
