"""Shared Anthropic client + .env loading."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MODEL_GENERATE = "claude-opus-5"   # writes the rulebook - quality matters most
# Opus for classification too, for now. It is ~20x the cost of Haiku
# (~$0.004 vs ~$0.0002 a call) but it is the most dangerous step in the
# system - a wrong category sends the patient into the wrong rulebook and
# everything after that is confidently wrong. Revisit once there is
# performance data to compare the two on real complaints.
MODEL_CLASSIFY = "claude-opus-5"


def load_env(path=None):
    """Tiny .env reader so we don't need another dependency."""
    path = Path(path) if path else ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if v and not os.environ.get(k):
            os.environ[k] = v


def get_client():
    import anthropic
    load_env()
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise SystemExit(
            "\n  No ANTHROPIC_API_KEY found.\n"
            "  Open .env and paste your key after ANTHROPIC_API_KEY=\n"
            "  Get one at https://console.anthropic.com/settings/keys\n")
    return anthropic.Anthropic(api_key=key)
