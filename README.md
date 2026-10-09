# ada-opus-engine-sim

A symptom-to-disease predictor. Claude writes the knowledge base once per
complaint; a Bayesian engine then runs the consultation with no model involved.

> Prototype. The knowledge base is machine-written and **not clinically
> reviewed**. Not for clinical use.

## 1. Install

```bash
cd ada-opus-engine-sim
pip install -r requirements.txt
```

## 2. Add your key

```bash
cp .env.example .env
```

Then open `.env` and paste your key after the `=` sign:

```
ANTHROPIC_API_KEY=sk-ant-...
```

Get one at https://console.anthropic.com/settings/keys

## 3. Run it

```bash
python cli.py
```

It asks what's bothering you, your sex and age, then starts the questions.

**First time for a complaint type takes ~60 seconds** - Claude is writing the
rulebook. You'll see a progress counter. Every later patient with that same
complaint is instant and free.

---

## Other commands

```bash
python cli.py --why                    # show why each question was picked
python cli.py --categories             # what complaints it covers
python cli.py --list                   # list the rulebooks on disk
python cli.py --inspect <key>          # look inside one rulebook
pytest                                 # 50 tests, offline, no key needed
```

Skip the prompts:

```bash
python cli.py --complaint "my knee hurts" --sex male --age 58
```

## Try it without a key

Five rulebooks ship with the repo, so this runs with zero API calls:

```bash
python cli.py --complaint "dizzy" --sex female --age 34 \
              --category dizziness --why
```

---

How it all works: **MASTERFILE.md**
