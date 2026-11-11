"""Optional enrichment: ask Claude for exam notes on each important release.

Runs only when ANTHROPIC_API_KEY is set (and the `anthropic` package is installed).
The model sees the text of one release and must answer from that text alone.
Everything it returns is labelled AI-generated on the site.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

log = logging.getLogger("pib.enrich")

SYSTEM = """You are an exam-preparation editor for UPSC Civil Services and APPSC Group 1 / Group 2 aspirants.
You will be given the text of ONE Press Information Bureau (PIB) release.
Use ONLY facts stated in that text. Never add outside facts, numbers, names or dates.
Reply with a single JSON object and nothing else (no markdown fences)."""

PROMPT = """Ministry: {ministry}
Title: {title}

Release text:
{body}

Return JSON with exactly these keys:
{{
  "prelims_facts": ["3 to 5 short factual bullets a Prelims question could be built on: names, numbers, nodal ministry, partner countries, locations, dates. Each under 25 words."],
  "mains_angle": "1-2 sentences: the policy or governance takeaway and which GS paper / topic it supports (for example 'GS-3 Economy: ...').",
  "gs_papers": ["subset of GS1, GS2, GS3, GS4, Essay"],
  "mcq": {{"q": "one Prelims-style multiple-choice question answerable from the text", "options": ["A", "B", "C", "D"], "answer": 0, "explanation": "one sentence"}} or null if the text is too thin,
  "telugu": {telugu_hint}
}}"""


def _client(cfg: dict[str, Any]):
    key = os.environ.get(cfg["api_key_env"])
    if not key:
        return None
    try:
        import anthropic  # type: ignore
    except ImportError:
        log.warning("ANTHROPIC_API_KEY is set but the 'anthropic' package is not installed; skipping enrichment")
        return None
    return anthropic.Anthropic(api_key=key)


def _parse_json(text: str) -> dict | None:
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _clean(d: dict, want_telugu: bool) -> dict | None:
    facts = [str(x).strip() for x in d.get("prelims_facts", []) if str(x).strip()][:5]
    angle = str(d.get("mains_angle", "")).strip()
    papers = [p for p in d.get("gs_papers", []) if p in {"GS1", "GS2", "GS3", "GS4", "Essay"}]
    mcq = d.get("mcq")
    if isinstance(mcq, dict):
        opts = mcq.get("options")
        ans = mcq.get("answer")
        if not (isinstance(opts, list) and len(opts) == 4 and isinstance(ans, int) and 0 <= ans < 4 and mcq.get("q")):
            mcq = None
        else:
            mcq = {
                "q": str(mcq["q"]).strip(),
                "options": [str(o).strip() for o in opts],
                "answer": ans,
                "explanation": str(mcq.get("explanation", "")).strip(),
            }
    else:
        mcq = None
    if not facts and not angle:
        return None
    out: dict[str, Any] = {"prelims_facts": facts, "mains_angle": angle, "gs_papers": papers, "mcq": mcq}
    if want_telugu and d.get("telugu"):
        out["telugu"] = str(d["telugu"]).strip()
    return out


def enrich_items(pending: list[dict[str, Any]], cfg: dict[str, Any], budget: int) -> int:
    """pending: list of dicts with keys item (the stored dict) and body (full text, in memory only).

    Sets item['ai'] in place. Returns the number of items enriched.
    """
    if budget <= 0 or not pending:
        return 0
    client = _client(cfg)
    if client is None:
        return 0

    want_telugu = bool(cfg.get("telugu", True))
    telugu_hint = (
        '"two short sentences in Telugu summarising the release for an APPSC aspirant"'
        if want_telugu
        else "null"
    )
    done = 0
    for entry in pending[:budget]:
        item, body = entry["item"], entry["body"]
        prompt = PROMPT.format(
            ministry=item["ministry"],
            title=item["title"],
            body=body[: cfg.get("max_body_chars", 5000)],
            telugu_hint=telugu_hint,
        )
        try:
            msg = client.messages.create(
                model=cfg["model"],
                max_tokens=1400,
                system=SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
            parsed = _parse_json(text)
            cleaned = _clean(parsed, want_telugu) if parsed else None
            if cleaned:
                cleaned["model"] = cfg["model"]
                item["ai"] = cleaned
                done += 1
            else:
                log.warning("enrichment returned unusable JSON for PRID %s", item["prid"])
        except Exception as e:  # network, rate limit, auth: keep the run alive
            log.warning("enrichment failed for PRID %s: %s", item["prid"], e)
    return done
