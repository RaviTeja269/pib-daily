"""Rule-based exam-relevance tagging for PIB press releases.

Deliberately transparent: every flag comes from config.json, and each item
carries the reasons it was flagged so the site can show them.
"""
from __future__ import annotations

import re
from typing import Any

# Acronyms that appear in nearly every release and carry no revision value.
ACRONYM_STOP = {
    "PIB", "THE", "AND", "FOR", "NEW", "GOI", "IST", "PM", "CM", "DR", "SHRI", "SMT", "UT", "AM", "MOU",
    "SAMPLE", "ETC", "VIZ", "ALL", "ITS", "NOT", "BUT", "ARE", "WAS", "HAS", "HAD", "CAN", "WILL", "ALSO", "WITH",
    "FROM", "THIS", "THAT", "UNION", "STATE", "INDIA", "ID", "NO", "OF", "TO", "IN", "ON", "AT", "BY",
}

ACRONYM_RE = re.compile(r"\b(?:[A-Z]{2,}[A-Z0-9]*|[A-Z]-[A-Z0-9]{2,})(?:[-/][A-Za-z0-9]+)*\b")
NAMED_RE = re.compile(
    r"((?:[A-Z][\w'’\-]*\s+){1,5}"
    r"(?:Mission|Yojana|Abhiyan|Scheme|Portal|Programme|Program|Fund|Policy|Authority|Corridor|Index|Exercise|"
    r"Initiative|Campaign|Commission|Council|Framework|Mechanism|Platform|Network|Act|Bill))\b"
)
QUOTED_RE = re.compile(r"[‘'“\"]([A-Z][^‘’'“”\"\n]{2,40})[’'”\"]")
FIGURE_RE = re.compile(
    r"(?:(?:₹|Rs\.?|INR)\s?[\d,]+(?:\.\d+)?\s?(?:lakh crore|crore|lakh|billion|million)?)"
    r"|(?:\d+(?:\.\d+)?\s?(?:per cent|%))"
    r"|(?:\d[\d,]*(?:\.\d+)?\s?(?:crore|lakh|MW|GW|km|tonnes|hectares|billion|million)\b)",
    re.I,
)


def _kw_regex(kw: str) -> re.Pattern:
    """'archaeolog*' -> stem match; plain words -> whole-word match."""
    kw = kw.strip().lower()
    if kw.endswith("*"):
        return re.compile(r"\b" + re.escape(kw[:-1]) + r"\w*")
    return re.compile(r"\b" + re.escape(kw) + r"\b")


class Classifier:
    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg
        self.thresholds = cfg["thresholds"]
        self.default_w = cfg.get("default_ministry_weight", 1)
        self.ministry_weights = {k.lower(): v for k, v in cfg["ministry_weights"].items()}
        self.ministry_hint = {k.lower(): v for k, v in cfg.get("ministry_subject_hint", {}).items()}
        self.subjects = {name: [_kw_regex(k) for k in kws] for name, kws in cfg["subjects"].items()}
        self.high = [(re.compile(h["pattern"], re.I), h["points"], h["label"]) for h in cfg["high_signal"]]
        self.low = [(re.compile(h["pattern"], re.I), h["points"], h["label"]) for h in cfg["low_signal"]]
        self.ap_re = re.compile(r"\b(" + "|".join(re.escape(k) for k in cfg["ap_keywords"]) + r")\b", re.I)

    # ------------------------------------------------------------------ pieces
    def ministry_weight(self, ministry: str, title: str = "") -> float:
        """Weight from the ministry name. If the page gave no readable ministry, look in the
        title instead, and failing that use a middle weight so the item is judged on its text."""
        def best_in(text: str):
            best = None
            for key, w in self.ministry_weights.items():
                if key in text:
                    best = w if best is None else max(best, w)
            return best

        m = ministry.lower()
        if m in ("", "unknown"):
            found = best_in(title.lower())
            return found if found is not None else max(self.default_w, 2)
        found = best_in(m)
        return self.default_w if found is None else found

    def _subjects(self, title: str, body: str, ministry: str) -> list[str]:
        t, b = title.lower(), body[:3000].lower()
        scored: list[tuple[float, str]] = []
        for name, regs in self.subjects.items():
            s = 0.0
            for r in regs:
                s += 3 * len(r.findall(t))
                s += min(len(r.findall(b)), 3)  # cap per keyword so one repeated word can't dominate
            if s >= 3:
                scored.append((s, name))
        scored.sort(reverse=True)
        out = [n for _, n in scored[:3]]
        if not out:
            m = ministry.lower()
            for key, subj in self.ministry_hint.items():
                if key in m:
                    out = [subj]
                    break
        return out

    def _hooks(self, title: str, body: str) -> list[str]:
        text = title + "\n" + body[:2500]
        found: list[str] = []

        def add(x: str):
            x = x.strip(" .,;:-")
            if x and x not in found and x.lower() not in {f.lower() for f in found}:
                found.append(x)

        for m in QUOTED_RE.finditer(text):
            add(m.group(1))
        for m in NAMED_RE.finditer(text):
            add(m.group(1))
        counts: dict[str, int] = {}
        for m in ACRONYM_RE.finditer(text):
            a = m.group(0)
            if a.upper() in ACRONYM_STOP or not (3 <= len(a) <= 14):
                continue
            counts[a] = counts.get(a, 0) + 1
        in_title = [a for a in counts if a in title]
        rest = sorted((a for a in counts if a not in in_title), key=lambda a: -counts[a])
        for a in in_title + rest:
            add(a)
        return found[:7]

    def _figures(self, body: str) -> list[str]:
        out: list[str] = []
        for m in FIGURE_RE.finditer(body[:3500]):
            f = re.sub(r"\s+", " ", m.group(0)).strip()
            if f and f not in out:
                out.append(f)
            if len(out) >= 4:
                break
        return out

    # -------------------------------------------------------------------- main
    def classify(self, title: str, ministry: str, body: str, office: str | None = None) -> dict[str, Any]:
        title_l = title.lower()
        body_l = body[:1500].lower()

        w = self.ministry_weight(ministry, title)
        score = float(w)
        reasons: list[str] = []
        type_label, type_pts = None, 0.0

        high_total = 0.0
        for rx, pts, label in self.high:
            in_title = bool(rx.search(title_l))
            in_body = bool(rx.search(body_l))
            if in_title or in_body:
                got = pts if in_title else pts * 0.5
                high_total += got
                reasons.append(label)
                if got > type_pts:
                    type_label, type_pts = label, got
        score += min(high_total, 8.0)

        for rx, pts, label in self.low:
            if rx.search(title_l):
                score -= pts
                reasons.append(label)
            elif rx.search(body_l):
                score -= pts * 0.5

        subjects = self._subjects(title, body, ministry)
        score += 0.5 * min(len(subjects), 3)

        ap_hits = sorted({m.group(1).title() for m in self.ap_re.finditer(title + "\n" + body[:3000])})
        ap = bool(ap_hits) or bool(office and "vijayawada" in office.lower())
        if ap:
            score += self.cfg.get("ap_bonus", 1.5)
            reasons.append("Andhra Pradesh link")

        score = round(score, 1)
        if score >= self.thresholds["must"]:
            priority = "must"
        elif score >= self.thresholds["good"]:
            priority = "good"
        elif score >= self.thresholds["skim"]:
            priority = "skim"
        else:
            priority = "skip"

        return {
            "score": score,
            "priority": priority,
            "type": type_label,
            "subjects": subjects,
            "ap": ap,
            "ap_terms": ap_hits[:4],
            "reasons": list(dict.fromkeys(reasons))[:6],
            "hooks": self._hooks(title, body),
            "figures": self._figures(body),
        }
