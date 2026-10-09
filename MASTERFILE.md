# How this works

Everything below uses one real example you can run yourself:

```bash
python cli.py --complaint "dizzy" --sex female --age 34 --category dizziness --why
```

---

## 1. The one idea

**Claude writes the rulebook. The engine plays the game.**

- Claude is called **once**, before any question is asked.
- Claude never sees a patient answer. Ever.
- After that, it is pure arithmetic.

Why split it this way:

| job | who does it | because |
|---|---|---|
| Which conditions exist, how common, which symptoms | **Claude** | it has read the medical literature |
| Which question to ask next | **engine** | it is maths, and Claude is bad at maths |
| Updating the percentages | **engine** | same |
| When to stop | **engine** | a fixed rule, so it always ends |

If Claude ran the conversation instead, three things break:
1. It might ask 4 questions or 34 — no guaranteed ending.
2. Two identical patients could get different answers.
3. "70% likely" would be a guess, not a calculated number.

---

## 2. The folders

```
Ada_Opus_engine_sim/
│
├── engine/              ← THE MATHS. No Claude. No internet.
│   ├── bayes.py           entropy, update, info_gain
│   ├── rulebook.py        reads a rulebook folder off disk
│   └── consult.py         the question loop, and when to stop
│
├── llm/                 ← THE CLAUDE CALLS. All of them, only here.
│   ├── client.py          reads .env, makes the client
│   ├── classify.py        "my leg hurts" -> "leg_pain"
│   ├── prompt.py          the instructions sent to Claude
│   ├── schema.py          the shape Claude must return
│   └── generate.py        makes the call, writes the YAML
│
├── kb/                  ← *** THE KNOWLEDGE BASE LIVES HERE ***
│   ├── generated/         Claude writes here. Machine-written.
│   └── reviewed/          a doctor corrected it. Trusted.
│
└── cli.py               wires the two halves together
```

**`engine/` imports nothing from `llm/`.** You can delete the whole `llm/`
folder and the engine still runs on any rulebook already on disk.

---

## 3. Where the knowledge base gets populated

This is the part to watch.

```
kb/generated/dizziness__female__18-39/
│
├── meta.yaml                    who wrote it, when, which model
├── findings.yaml                the questions, in patient words
└── conditions/
    ├── bppv.yaml                one file per condition
    ├── menieres.yaml
    ├── posterior_stroke_tia.yaml
    └── ...
```

**The folder name is the cache key:** `category__sex__ageband`

- First patient with dizziness → folder does not exist → Claude writes it (~$0.10, ~20s)
- Every later patient with dizziness → folder exists → **free and instant**

### How the key is built

```python
age_band(34)  ->  "18-39"        # clinical bands, not decades
sex           ->  "female"       # or "any" if the complaint presents the same in both
category      ->  "dizziness"

key = "dizziness__female__18-39"
```

Then the lookup is a folder check. No database, no fuzzy matching:

```python
for root in ("kb/reviewed", "kb/generated"):   # reviewed always wins
    if os.path.isdir(f"{root}/{key}"):
        return f"{root}/{key}"
return None                                    # miss -> call Claude
```

Age bands are **18-39 / 40-64 / 65+** (plus child and teen), not decades.
Those boundaries are where disease risk genuinely shifts. A decade band put
a cliff between 39 and 40 that meant nothing medically.

Sex collapses to `any` unless the complaint really differs - `urinary` and
`dizziness` keep it, `respiratory_urti` does not. Together these cut the
total number of rulebooks that could ever exist from 240 to **70**.

So the knowledge base is not something you sit down and write. It grows to
fit whoever actually walks in.

### What one condition file looks like

`kb/generated/dizziness__female__18-39/conditions/bppv.yaml`

```yaml
id: bppv
name: Benign paroxysmal positional vertigo
prior: 0.25                     # 25 of 100 dizzy patients have this
must_not_miss: false

choices:
  episode_duration: [0.85, 0.12, 0.02, 0.01]   # seconds|minutes|hours|days

findings:
  spinning:          {p: 0.95}
  trig_head_move:    {p: 0.90, note: "THE discriminator"}
  nausea:            {p: 0.60}
  hearing_change:    {p: 0.02, note: "RULE-OUT: Meniere's is 0.85"}
```

Every number means **one thing**:

> `p: 0.90` = *out of 100 people who definitely have BPPV, 90 say the dizziness
> starts when they turn their head.*

That is it. The whole knowledge base is that sentence, repeated.

---

## 4. One patient, start to finish

### Step 1 — the patient types one line

```
What's bothering you? > dizzy
Sex [female/male] > female
Age > 34
```

### Step 2 — pick a category

`llm/classify.py` asks **Opus 5** to choose from a fixed list of 15.
It cannot invent one; it picks from the list and reports how sure it is.

```
"dizzy"  ->  dizziness,  92% confident
```

Opus rather than Haiku because this is the most dangerous step in the
system: a wrong category sends the patient into the wrong rulebook and
everything after that is confidently wrong. ~$0.004 a call.

**Below 60% confidence the pick is thrown away** and treated as `unclear`.

### Step 2b — is this even a differential?

```bash
python cli.py --categories
```

Twelve categories run the engine. Three do not:

| category | what happens |
|---|---|
| `chronic_followup` | "here for my BP check" - needs results reviewed, not questions |
| `asymptomatic_screening` | high cholesterol is **silent**; no question can find it |
| `unclear` | too vague - ask the patient to rephrase |

These stop with a message and ask nothing. Running a symptom-narrowing
engine on a screening visit would produce confident nonsense.

### Step 3 — look for a rulebook

```
key = dizziness__female__18-39

  kb/reviewed/dizziness__female__18-39/   exists?  no
  kb/generated/dizziness__female__18-39/  exists?  YES
```

Found it. **No Claude call.** (If it were missing, step 3b below runs.)

### Step 3b — only if missing: Claude writes it

`llm/generate.py` sends the prompt from `llm/prompt.py` and demands the
shape in `llm/schema.py`. Pydantic validates the response or raises.
The YAML files get written. This happens once per category, ever.

### Step 4 — the engine starts

10 conditions, straight from the priors:

```
Benign paroxysmal positional vertigo    25%
Orthostatic hypotension                 18%
Vasovagal presyncope                    12%
Vestibular neuritis                     10%
...
3.04 bits -> 8.2 options still in play
```

"8.2 options" means: *as confused as someone picking between 8 things.*
The goal is to get that to 1.

### Step 5 — pick the best question

The engine scores **every** unasked question and takes the top one:

```
0.698 bits   How long does each episode last?     <- ask this
0.585 bits   Does the room feel like it's spinning?
0.457 bits   Do you feel like you might faint?
...
0.060 bits   Any new weakness or numbness?        <- worthless right now
```

### Step 6 — ask, then update

```
"How long does each episode of dizziness last?"
   1. Seconds   2. Minutes   3. Hours   4. Days or never stops
> 1
```

```
BPPV            25% -> 43%     ^+18.3
Orthostatic     18% -> 29%     ^+11.4
Anxiety         10% ->  2%     v -8.0
2.01 bits -> 4.0 options
```

### Step 7 — repeat

```
Q2  "Does the room feel like it is spinning?"       YES
    BPPV 43% -> 88%

Q3  "Does it start when you turn your head?"        YES
    BPPV 88% -> 98%
```

### Step 8 — stop

```
Stopped after 3 questions - confident (98%) and nothing useful left to ask

  1. Benign paroxysmal positional vertigo    98.5%
  2. Orthostatic hypotension                  0.8%
  3. Vestibular neuritis                      0.3%
```

**Three questions. Thirteen were available.**

---

## 5. The maths, in three pieces

### Piece 1 — updating

Patient says YES to spinning. Look up the spinning column:

```
BPPV           0.95
Vestibular     0.95
Orthostatic    0.10
Anaemia        0.05
```

Multiply each condition's current percentage by its number:

```
BPPV         0.4310 x 0.95 = 0.40945
Orthostatic  0.2907 x 0.10 = 0.02907
Vasovagal    0.1720 x 0.05 = 0.00860
...
                             -------
                             0.46370   <- divide everyone by this
```

```
BPPV = 0.40945 / 0.46370 = 88%
```

**If the answer is NO, multiply by `(1 - p)` instead.** Same two lines.

### Piece 2 — the confusion meter

```
entropy = -SUM( p x log2(p) )
```

You never need to read that formula. Read this instead:

```
2 ^ entropy  =  how many options you're torn between
```

```
3.04 bits -> 8.2 options        at the start
0.15 bits -> 1.1 options        after 3 questions
```

### Piece 3 — choosing the next question

For each unasked question, the engine plays out **both futures on paper**:

1. Pretend the answer is YES → how confused would I be?
2. Pretend the answer is NO → how confused would I be?
3. Average those, weighted by how likely each answer is
4. Subtract from current confusion → that's the score

Highest score wins. Run `--why` to see the scores.

**Key rule:** a yes/no question can never score above **1.0 bits** — two doors
can at best halve the field. A 5-option question can score higher. That is why
"how long does it last" and "where is the pain" usually win turn 1.

---

## 6. Four things that surprise people

### A good question is one they DISAGREE about

```
nausea            BAD question          worse_exertion    GOOD question
  BPPV      0.60                          anaemia   0.80
  vestibular 0.85                         BPPV      0.05
  Meniere's 0.70                          vestibular 0.05
  (all high - learns nothing)             (one stands out - splits the field)
```

### A LOW number is as useful as a high one

BPPV has `hearing_change: 0.02`. Looks pointless. It is not — Meniere's is
`0.85`. When the patient says **no hearing change**, Meniere's collapses and
BPPV rises *without any evidence in its favour*. That is a **rule-out**, and
half of all diagnosis is rule-outs.

### A question's value changes every turn

```
"ringing in the ears?"    turn 1:  0.045 bits   (nearly worthless)
                          turn 7:  0.253 bits   (decisive)
```

Same question. Same rulebook. The *belief* changed, so the value changed.
**This is why no question order is stored anywhere.**

### Evidence can make you MORE confused

If the leader is at 93% and the patient says something that fits a different
condition, entropy goes **up**. That is correct. A system that only ever
narrows is hiding contradictory evidence from you.

---

## 7. Checking a rulebook is any good

```bash
python cli.py --inspect dizziness__female__18-39
```

```
health - does every condition have a discriminator?
   Medication side effect       None             +0.00  <- WEAK
   Vasovagal presyncope         lightheaded      +0.05  <- WEAK
   Cardiac arrhythmia           palpitations     +0.20  <- WEAK
   Anxiety                      duration=minutes +0.25
   ...
   Meniere's disease            hearing_change   +0.77
```

**A discriminator is one finding where the condition beats every rival.**
Without one, it can only be reached by elimination — slow and fragile.

The shipped example has three weak ones. That is the check doing its job,
not a bug. Fixing them means adding a finding where each stands alone.

---

## 8. What it costs

| | per consultation |
|---|---|
| Classify the complaint | ~$0.0002 |
| Rulebook already on disk | **$0** |
| Rulebook missing — Claude writes it | ~$0.10, once |
| Running the questions | **$0** |

The 50th dizzy patient costs a fifth of a cent. Only the first one pays.

---

## 9. When something looks wrong

| symptom | look here |
|---|---|
| Wrong category picked | `llm/categories.py` - fix `covers` / `patient_says` |
| Too many "unclear" | lower `MIN_CONFIDENCE` in `llm/classify.py` |
|---|---|
| Asked a silly question | `--why` — see what it scored. Probably a column where everything is similar. |
| Wrong answer | `cli.py --inspect <key>` — check the discriminators |
| A condition never wins | It has no discriminator. Health report will show `+0.00`. |
| Stops too early | `STOP_CONFIDENCE` in `engine/consult.py` |
| Asks too many questions | `MAX_QUESTIONS` in `engine/consult.py` |
| Every threshold | top of `engine/consult.py`, nowhere else |

---

## 10. The honest limits

1. **Claude's numbers are estimates, not measurements.** The engine combines
   them correctly, but correct arithmetic on guessed inputs is still guessed
   output. That is what `kb/reviewed/` is for — a doctor corrects the numbers
   and moves the folder.

2. **Never test it with patients you made up from the same rulebook.** That
   measures nothing. You need real cases with known answers.

3. **Rare dangerous conditions get neglected.** Information gain chases the
   big probabilities. A condition with a 2% prior rarely gets its questions
   asked. `must_not_miss: true` is in the schema for this reason, and the
   CLI flags them at the end — but a proper safety layer that interrupts the
   loop is not built yet.

4. **Not clinically reviewed. Not for real patients.**
