"""Tier 1 — the deterministic rule engine.

Split out of extractor.py so the tiering is legible: this module is pure
regex over clauses and is the only tier that always runs. It is also the
only tier whose output is reproducible on any machine, which is why it wins
every merge conflict against the probabilistic tiers above it.

Two bugs this replaces, both from the original single-pattern engine:

  * `[A-Z]` under re.IGNORECASE matches lowercase, so "call me via call"
    extracted a person named "via". Every name capture now runs through a
    stopword blocklist instead of relying on capitalisation.
  * patterns ran once over the whole utterance and stopped at the first
    match, so "hi i am yashraj, i am from pune, i have 3000rs, i prefer
    email" yielded a single field. Text is now split into clauses and every
    pattern runs on every clause.
"""

from __future__ import annotations

import re
from typing import Any

# --- vocabulary ---------------------------------------------------------------

# Words that can follow a name trigger but are never a name. Without this,
# "i am from pune" names you "from" and "call me via call" names you "via".
NAME_STOPWORDS = frozenset({
    "via", "from", "in", "at", "on", "to", "by", "with", "for", "of",
    "the", "a", "an", "and", "or", "but",
    "call", "calling", "email", "mail", "whatsapp", "wa", "sms", "text",
    "phone", "voice", "ring", "message", "msg",
    "now", "just", "also", "here", "there", "then",
    "hi", "hello", "hey", "sorry", "sure", "ok", "okay", "yes", "no",
    "please", "thanks", "thank",
    "am", "is", "are", "was", "were", "be", "been", "being",
    "not", "never", "always", "still", "back", "over", "out", "up", "down",
    "me", "my", "you", "your", "we", "us", "they", "it", "this", "that",
    "going", "doing", "looking", "trying", "getting",
    "budget", "price", "cost", "name", "based", "living", "live",
    "se", "hai", "hoon", "hu", "ka", "ki", "ke", "mera", "meri", "main",
})

CONTACT_SYNONYMS: dict[str, tuple[str, ...]] = {
    "email": ("email", "e-mail", "emails", "mail", "gmail"),
    "call": ("call", "calls", "phone", "phones", "voice", "ring", "telephone"),
    "whatsapp": ("whatsapp", "whats app", "wa"),
    "sms": ("sms", "text message", "texts", "texting"),
}

_MONEY_SCALES = {
    "k": 1_000, "lakh": 100_000, "lakhs": 100_000, "lac": 100_000, "lacs": 100_000,
    "cr": 10_000_000, "crore": 10_000_000, "crores": 10_000_000,
}

# --- clause splitting ---------------------------------------------------------

# Commas, semicolons and coordinating words. Hinglish "aur" behaves like "and".
_CLAUSE_SPLIT = re.compile(
    # a comma between digits belongs to the number ("1,50,000"), and a full
    # stop only ends a clause when followed by space ("Next.js" survives)
    r"(?<!\d)[,;•](?!\d)|[\n]+|\.\s+|\s+(?:and|aur)\s+",
    re.IGNORECASE,
)


def split_clauses(text: str) -> list[str]:
    """Clauses, plus the whole utterance so cross-clause patterns still fire."""
    parts = [c.strip() for c in _CLAUSE_SPLIT.split(text) if c and c.strip()]
    whole = text.strip()
    return [*parts, whole] if whole and whole not in parts else parts


# --- name ---------------------------------------------------------------------

# A word that is allowed to be part of a name.
_NAME_WORD = r"(?!(?:%s)\b)[A-Za-z][A-Za-z'’-]*" % "|".join(sorted(NAME_STOPWORDS))
_NAME = rf"({_NAME_WORD}(?:\s+{_NAME_WORD})?)"

_NAME_PATTERNS = (
    re.compile(rf"\bmy name is\s+{_NAME}", re.IGNORECASE),
    re.compile(rf"\bi\s*(?:am|'m|m)\s+called\s+{_NAME}", re.IGNORECASE),
    re.compile(rf"\bi\s*(?:am|'m|’m)\s+{_NAME}", re.IGNORECASE),
    re.compile(rf"\bthis is\s+{_NAME}", re.IGNORECASE),
    re.compile(rf"\bcall me\s+{_NAME}", re.IGNORECASE),
    re.compile(rf"\bmera naam\s+{_NAME}", re.IGNORECASE),
    re.compile(rf"\bmain\s+{_NAME}\s+(?:hoon|hu|hun)\b", re.IGNORECASE),
    re.compile(rf"^{_NAME}\s+here\b", re.IGNORECASE),
)


def _titlecase(value: str) -> str:
    """Capitalise without destroying an already-correct McName or O'Brien."""
    return " ".join(w if w[:1].isupper() and w[1:].islower() is False and any(
        c.isupper() for c in w[1:]) else w.capitalize() for w in value.split())


def find_name(clause: str) -> str | None:
    for pattern in _NAME_PATTERNS:
        m = pattern.search(clause)
        if not m:
            continue
        candidate = m.group(1).strip(" .'’-")
        words = candidate.split()
        if not words or any(w.lower() in NAME_STOPWORDS for w in words):
            continue
        if len(candidate) < 2 or candidate.isdigit():
            continue
        return _titlecase(candidate)
    return None


# --- city ---------------------------------------------------------------------

_CITY = rf"({_NAME_WORD}(?:\s+{_NAME_WORD})?)"
_CITY_PATTERNS = (
    re.compile(rf"\bi\s*(?:am|'m|’m)\s+from\s+{_CITY}", re.IGNORECASE),
    re.compile(rf"\b(?:based|living|live|located|stay|staying)\s+in\s+{_CITY}", re.IGNORECASE),
    re.compile(rf"\bfrom\s+{_CITY}", re.IGNORECASE),
    re.compile(rf"\b{_CITY}\s+se\b", re.IGNORECASE),
)


def find_city(clause: str) -> str | None:
    for pattern in _CITY_PATTERNS:
        m = pattern.search(clause)
        if not m:
            continue
        candidate = m.group(1).strip(" .'’-")
        if not candidate or any(w.lower() in NAME_STOPWORDS for w in candidate.split()):
            continue
        return _titlecase(candidate)
    return None


# --- money --------------------------------------------------------------------

_CEILING = re.compile(
    r"\b(?:under|below|max(?:imum)?|upto|up\s+to|at\s+most|within|less\s+than|"
    r"no(?:t)?\s+more\s+than|tak|se\s+z?y?ada\s+nahi|se\s+jada\s+nahi)\b",
    re.IGNORECASE,
)
# "only" is deliberately absent: it reads as a ceiling in "only 5k" but not in
# "prefer whatsapp only" or "only 3 sessions", and a ceiling marker is enough
# on its own to classify a bare number as money.

_MONEY = re.compile(
    r"(?P<pre>₹|rs\.?|inr)?\s*"
    r"(?P<num>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<scale>k|lakhs?|lacs?|crores?|cr)?\s*"
    r"(?P<post>₹|rs\.?|inr|rupees?|rupaye|rupee)?",
    re.IGNORECASE,
)

_BUDGET_WORD = re.compile(r"\b(?:budget|price|cost|spend|afford|paisa|paise)\b", re.IGNORECASE)


def find_money(clause: str) -> tuple[int, bool] | None:
    """(amount, is_ceiling), or None when nothing money-like is present.

    A bare number is only money when something says so — a currency token, a
    k/lakh/crore scale, or a budget word in the clause. "16GB RAM" and
    "3 sessions" must not become a budget.
    """
    budgetish = bool(_BUDGET_WORD.search(clause))
    ceiling = bool(_CEILING.search(clause))
    budgetish = budgetish or ceiling
    for m in _MONEY.finditer(clause):
        if not m.group("num"):
            continue
        scale = (m.group("scale") or "").lower().rstrip(".")
        has_currency = bool(m.group("pre") or m.group("post"))
        if not (has_currency or scale or budgetish):
            continue
        # a scale-less number immediately followed by letters is a spec, not
        # money: "16GB", "3bhk"
        tail = clause[m.end("num"):m.end("num") + 2]
        if not has_currency and not scale and re.match(r"[A-Za-z]{2}", tail):
            continue
        try:
            amount = float(m.group("num").replace(",", ""))
        except ValueError:
            continue
        amount *= _MONEY_SCALES.get(scale, 1)
        if amount <= 0:
            continue
        return int(amount), ceiling
    return None


# --- contact mode -------------------------------------------------------------

_PREFER = re.compile(
    r"\b(?:prefer(?:red|s)?|contact me|reach me|message me|ping me|call me|"
    r"mail me|only|instead|rather)\b",
    re.IGNORECASE,
)
_SWITCH = re.compile(r"\b(?:instead of|rather than|not)\s+(?:on\s+|by\s+|via\s+)?(\w+)",
                     re.IGNORECASE)


def _mode_of(word: str) -> str | None:
    lowered = word.lower()
    for mode, synonyms in CONTACT_SYNONYMS.items():
        if lowered in synonyms:
            return mode
    return None


def _mentioned_modes(clause: str) -> list[str]:
    found: list[str] = []
    for mode, synonyms in CONTACT_SYNONYMS.items():
        for synonym in synonyms:
            if re.search(rf"\b{re.escape(synonym)}\b", clause, re.IGNORECASE):
                if mode not in found:
                    found.append(mode)
                break
    return found


def _negated(clause: str, mode: str) -> bool:
    for synonym in CONTACT_SYNONYMS[mode]:
        pattern = (
            r"\b(?:no|not|never|avoid|don'?t|dont|stop|instead of|rather than)\b"
            rf"[^.;,]*?\b{re.escape(synonym)}\b"
        )
        if re.search(pattern, clause, re.IGNORECASE):
            return True
    return False


def find_contact(clause: str) -> tuple[str | None, list[str]]:
    """(preferred mode, rejected modes). Both may be empty."""
    if not _PREFER.search(clause):
        return None, []
    mentioned = _mentioned_modes(clause)
    if not mentioned:
        return None, []
    rejected = [m for m in mentioned if _negated(clause, m)]
    chosen = [m for m in mentioned if m not in rejected]
    if len(chosen) == 1:
        return chosen[0], rejected
    if len(chosen) > 1:
        # "prefer email because calls are hard" mentions two modes but states
        # one preference. The mode nearest after the preference verb is the
        # one being expressed; anything further along is context, not a
        # competing choice.
        trigger = _PREFER.search(clause)
        if trigger:
            ranked = sorted(
                ((_first_mention(clause, mode, trigger.end()), mode) for mode in chosen),
                key=lambda pair: pair[0],
            )
            nearest, mode = ranked[0]
            if nearest < len(clause):
                return mode, rejected
        return None, rejected  # genuinely ambiguous — caller records a conflict
    return None, rejected


def _first_mention(clause: str, mode: str, start: int) -> int:
    """Offset of the earliest synonym for `mode` at or after `start`."""
    best = len(clause)
    for synonym in CONTACT_SYNONYMS[mode]:
        m = re.search(rf"\b{re.escape(synonym)}\b", clause[start:], re.IGNORECASE)
        if m:
            best = min(best, start + m.start())
    return best


# --- dates --------------------------------------------------------------------

_ISO_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_MONTHS = (
    "january|february|march|april|may|june|july|august|september|october|"
    "november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec"
)
_ABS_DATE = re.compile(
    rf"\b(\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{_MONTHS})|(?:{_MONTHS})\s+\d{{1,2}}(?:st|nd|rd|th)?)\b",
    re.IGNORECASE,
)
_WEEKDAY = r"monday|tuesday|wednesday|thursday|friday|saturday|sunday"
_DATE_TRIGGER = r"by|before|due(?:\s+(?:by|on))?|deadline\s+is|till|until|ship(?:\s+it)?\s+by"

# Needs a trigger: "by Friday" is a deadline, "nice today" is small talk.
_REL_DATE_TRIGGERED = re.compile(
    rf"\b(?:{_DATE_TRIGGER})\s+({_WEEKDAY}|today|tonight|tomorrow|kal|parso)\b",
    re.IGNORECASE,
)
# Stands alone: these can only be talking about a future point.
_REL_DATE_STRONG = re.compile(
    rf"\b((?:next|this|coming|agle)\s+(?:week|month|{_WEEKDAY}|hafte|mahine)|"
    rf"tomorrow|parso|end\s+of\s+(?:the\s+)?(?:day|week|month))\b",
    re.IGNORECASE,
)


def find_dates(clause: str) -> list[str]:
    """Every date-ish phrase in a clause, ISO first, in order of appearance."""
    out: list[str] = []
    for m in _ISO_DATE.finditer(clause):
        out.append(m.group(1))
    for m in _ABS_DATE.finditer(clause):
        value = " ".join(m.group(1).split())
        if value not in out:
            out.append(value)
    for pattern in (_REL_DATE_TRIGGERED, _REL_DATE_STRONG):
        for m in pattern.finditer(clause):
            value = " ".join(m.group(1).split()).lower()
            if value and value not in out:
                out.append(value)
    return out


# --- decisions, constraints, goals, unresolved --------------------------------

# Hinglish particles that can sit where a decision value would and mean
# nothing: "decision final hai — ASUS lunga" must choose ASUS, not "hai".
DECISION_NOISE = frozenset({
    "hai", "hain", "hi", "tha", "thi", "ho", "hoga", "karna", "kiya", "ka", "ki", "ke",
})

_DECISION = re.compile(
    r"\b(?:i(?:'ll| will|ll)?\s+go\s+with|i(?:'ve| have)?\s+decided\s+(?:on|to go with)|"
    r"let'?s\s+go\s+with|i(?:'ll| will)\s+take|final(?:ized|ised)?\s*(?:choice|decision)?"
    r"\s*(?:is|hai)?|decided\s+on|going\s+with)\s+"
    r"(?:the\s+)?([A-Za-z0-9][\w /.+-]*?)(?=\s*(?:[.,;!—-]|$))",
    re.IGNORECASE,
)
# Hinglish: "ASUS lunga" / "Dell loonga" — "<thing> lunga" means "I'll take <thing>"
# Only the one or two words immediately before the verb. A lazy capture would
# not help: re.search takes the leftmost match, so "decision final hai — ASUS
# lunga" would swallow the whole clause instead of choosing ASUS.
_DECISION_HI = re.compile(
    r"(?:^|[\s—–-])([A-Za-z0-9][\w./+-]*(?:\s+[A-Za-z0-9][\w./+-]*)?)\s+"
    r"(?:lunga|loonga|lenge|lenga|leta hoon)\b",
    re.IGNORECASE,
)

_REQUIREMENT = re.compile(
    r"\b(?:must\s+(?:have|be)|need(?:s)?|require(?:s|d)?|at\s+least|minimum)\s+"
    r"([A-Za-z0-9][\w %.+-]*?)(?=\s*(?:[.,;!]|$))",
    re.IGNORECASE,
)

_GOAL = re.compile(
    r"\b(?:i want to|my goal is to|i(?:'m| am) (?:trying|looking) to|i need to)\s+"
    r"([^.,;!]+)",
    re.IGNORECASE,
)

_UNRESOLVED = re.compile(
    r"\b(?:i\s+)?(?:haven'?t|have not|didn'?t|did not|not yet|still haven'?t)\s+"
    r"(?:decided|chosen|picked|figured out|final(?:ized|ised)?)\s+(?:on\s+)?"
    r"(?:the\s+|a\s+|my\s+)?([^.,;!]+)",
    re.IGNORECASE,
)
_UNSURE = re.compile(
    r"\b(?:not sure|unsure|undecided)\s+(?:about|on)\s+(?:the\s+|my\s+)?([^.,;!]+)",
    re.IGNORECASE,
)
# Hinglish: "delivery date abhi decide nahi kiya"
_UNRESOLVED_HI = re.compile(
    r"\b([\w\s]+?)\s+(?:abhi\s+)?(?:decide|tay)\s+nahi\s+(?:kiya|hua|hai)\b", re.IGNORECASE
)
_PENDING = re.compile(r"\b([\w\s]+?)\s+(?:is\s+)?pending\b", re.IGNORECASE)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")


# Words that trail an open question without naming it.
_UNRESOLVED_TAIL = re.compile(
    r"\s+(?:yet|so far|as of now|for now|abhi|still|right now|currently)\s*$",
    re.IGNORECASE,
)


def find_unresolved(clause: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for pattern, reason in (
        (_UNRESOLVED, "not provided"),
        (_UNSURE, "user unsure"),
        (_UNRESOLVED_HI, "not provided"),
        (_PENDING, "pending"),
    ):
        for m in pattern.finditer(clause):
            field = slugify(_UNRESOLVED_TAIL.sub('', m.group(1)))
            # a stopword-only capture is noise, not an open question
            if field and field not in {f for f, _ in out} and len(field) > 2:
                out.append((field, reason))
    return out


def find_decision(clause: str) -> str | None:
    """Hinglish first: "<thing> lunga" is unambiguous, "final hai" is not."""
    for pattern in (_DECISION_HI, _DECISION):
        m = pattern.search(clause)
        if not m:
            continue
        value = m.group(1).strip(" .-—'’")
        if not value or value.lower() in DECISION_NOISE:
            continue
        words = [w for w in value.split() if w.lower() not in DECISION_NOISE]
        if not words:
            continue
        return " ".join(words)
    return None



# --- build spec ---------------------------------------------------------------
# The other domain this engine covers: someone briefing a coding assistant.
# These are the constraints re-pasted into every prompt when there is no
# memory, and the instant demo depends on all five.

# A full stop only ends the value when followed by space, so "Next.js" survives.
_CLAUSE_END = r"(?=\s*(?:[.!;](?:\s|$)|,|$))"

_STACK = re.compile(
    r"\b(?:tech\s+)?stack\s*(?:is|:|=)\s*([A-Za-z0-9][\w .+/&-]*?)" + _CLAUSE_END,
    re.IGNORECASE,
)
_THEME = re.compile(
    r"\b(dark|light)\s+theme\b|\btheme\s*(?:is|:|=)\s*(dark|light)\b", re.IGNORECASE
)
_BRAND_COLOR = re.compile(
    r"\b(?:brand|accent|primary)\s+colou?rs?\s*(?:is|to|:|=)?\s*"
    r"(#[0-9A-Fa-f]{3,8}|[A-Za-z]+)",
    re.IGNORECASE,
)
_NO_UI_LIBS = re.compile(
    r"\b(?:no|without\s+(?:any\s+)?)\s*(?:external\s+)?ui\s+(?:librar(?:y|ies)|libs?)\b",
    re.IGNORECASE,
)
_UI_LIB = re.compile(
    r"\b(?:use|using|switch\s+to|add)\s+((?:shadcn(?:/ui)?|mui|material[-\s]?ui|chakra|"
    r"ant\s?design|antd|bootstrap|radix|headless\s?ui|daisy\s?ui)[\w/.-]*)",
    re.IGNORECASE,
)
_AUDIENCE = re.compile(
    r"\b(?:target\s+)?audience\s*(?:is|:|=)\s*([A-Za-z0-9][\w '&-]*?)" + _CLAUSE_END,
    re.IGNORECASE,
)


def find_build_spec(clause: str) -> list[tuple[str, str, object]]:
    """[(section, key, value)] for any build-spec field in this clause."""
    out: list[tuple[str, str, object]] = []

    if m := _STACK.search(clause):
        out.append(("decisions", "stack", m.group(1).strip()))

    if m := _THEME.search(clause):
        out.append(("preferences", "theme", (m.group(1) or m.group(2)).lower()))

    if m := _BRAND_COLOR.search(clause):
        value = m.group(1).strip()
        # hex is identity-bearing: #E07856 and #e07856 must not mint two handles
        out.append(("preferences", "brand_color",
                    value.upper() if value.startswith("#") else value.lower()))

    # a named library is the later, more specific instruction; the
    # contradiction with an earlier ban surfaces via conflict detection
    if m := _UI_LIB.search(clause):
        out.append(("constraints", "no_ui_libs", m.group(1).strip()))
    elif _NO_UI_LIBS.search(clause):
        out.append(("constraints", "no_ui_libs", "none"))

    if m := _AUDIENCE.search(clause):
        out.append(("facts", "audience", m.group(1).strip()))

    return out


__all__ = [
    "CONTACT_SYNONYMS", "DECISION_NOISE", "NAME_STOPWORDS", "find_decision",
    "find_city", "find_contact", "find_dates", "find_money", "find_name",
    "find_unresolved", "find_build_spec", "slugify", "split_clauses",
    "_DECISION", "_DECISION_HI", "_GOAL", "_REQUIREMENT",
]
