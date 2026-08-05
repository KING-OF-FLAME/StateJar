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

from app.schema import valuetype

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


# --- identity spans -----------------------------------------------------------
#
# `name` and `city` capture with the same pattern, because a person and a place
# look identical as text. That makes the trigger word in front of a span the
# only thing choosing its slot — and "I'm ..." and "from ..." occur constantly
# in sentences that name nobody and nowhere:
#
#     "I'm Mumbai based now, switching from Senior Software Engineer to ..."
#
# stored name="Mumbai" and city="Senior Software", overwriting a correct name
# and a correct city from an earlier turn. Both values were one slot away from
# where they belonged.
#
# The two guards below fix that by asking the span, not its position. A capture
# is refused when the phrase it sits in continues past it (the two-word cap cut
# "Senior Software Engineer" in half, and half a phrase is not evidence), and
# when a marker attached to the span itself contradicts the slot the trigger
# chose. Both are structural: they read the shape of the sentence rather than a
# list of words, so they do not need to grow as new job titles and city names
# appear. Refusing costs a fact; storing the wrong one costs the claim.

# A word that is allowed to be part of a name.
_NAME_WORD = r"(?!(?:%s)\b)[A-Za-z][A-Za-z'’-]*" % "|".join(sorted(NAME_STOPWORDS))
_NAME = rf"({_NAME_WORD}(?:\s+{_NAME_WORD})?)"

# Anything that is not a stopword, punctuation or the end of the clause
# continues the noun phrase the capture just truncated.
_PHRASE_CONTINUES = re.compile(
    r"\s+(?!(?:%s)\b)[A-Za-z]" % "|".join(sorted(NAME_STOPWORDS))
)

# Said *of* a place and never of a person: "Mumbai based", "Pune born". These
# words already mark a location for the city rule below, in their pre-posed
# form ("based in Mumbai"); this is the same signal read from the other side.
_LOCATIVE_MARKERS = ("based", "born", "raised", "headquartered", "native")
_LOCATIVE_SUFFIX = re.compile(
    r"\s+(?:%s)\b" % "|".join(_LOCATIVE_MARKERS), re.IGNORECASE
)

# `explicit` marks a trigger that can only be an act of naming. "My name is X"
# and "call me X" are unambiguous; "I'm X" is the copula and takes any
# complement at all, so a span behind it has to earn the slot.
_NAME_PATTERNS = (
    (re.compile(rf"\bmy name is\s+{_NAME}", re.IGNORECASE), True),
    (re.compile(rf"\bi\s*(?:am|'m|m)\s+called\s+{_NAME}", re.IGNORECASE), True),
    (re.compile(rf"\bi\s*(?:am|'m|’m)\s+{_NAME}", re.IGNORECASE), False),
    (re.compile(rf"\bthis is\s+{_NAME}", re.IGNORECASE), True),
    (re.compile(rf"\bcall me\s+{_NAME}", re.IGNORECASE), True),
    (re.compile(rf"\bmera naam\s+{_NAME}", re.IGNORECASE), True),
    (re.compile(rf"\bmain\s+{_NAME}\s+(?:hoon|hu|hun)\b", re.IGNORECASE), True),
    (re.compile(rf"^{_NAME}\s+here\b", re.IGNORECASE), False),
)


def _titlecase(value: str) -> str:
    """Capitalise without destroying an already-correct McName or O'Brien."""
    return " ".join(w if w[:1].isupper() and w[1:].islower() is False and any(
        c.isupper() for c in w[1:]) else w.capitalize() for w in value.split())


def _truncates_phrase(clause: str, end: int) -> bool:
    """Whether the capture stopped in the middle of a longer noun phrase.

    The capture takes at most two words, so "from Senior Software Engineer"
    yields "Senior Software" and looks exactly like a two-word city. What tells
    them apart is what comes next: a real place is followed by a function word
    or the end of the clause, never by a third content word.
    """
    return bool(_PHRASE_CONTINUES.match(clause, end))


def _is_participle(word: str) -> bool:
    """"I'm switching ..." is a verb, not an introduction.

    Grammar rather than vocabulary: every progressive verb behaves this way, so
    this needs no list and does not grow. The length floor keeps the short
    surnames that genuinely end in -ing (Wing, Ling, Xing).
    """
    return len(word) >= 6 and word.lower().endswith("ing")


def find_name(clause: str) -> str | None:
    for pattern, explicit in _NAME_PATTERNS:
        m = pattern.search(clause)
        if not m:
            continue
        candidate = m.group(1).strip(" .'’-")
        words = candidate.split()
        if not words or any(w.lower() in NAME_STOPWORDS for w in words):
            continue
        if len(candidate) < 2 or candidate.isdigit():
            continue
        # A marker on the span itself outranks the trigger in front of it —
        # whether it follows the capture ("I'm Mumbai based") or was swallowed
        # by it, since nothing stops a two-word capture eating the marker
        # ("I'm Bangalore born and raised" captures "Bangalore born").
        if (_LOCATIVE_SUFFIX.match(clause, m.end(1))
                or words[-1].lower() in _LOCATIVE_MARKERS):
            continue
        if not explicit and (_truncates_phrase(clause, m.end(1))
                             or any(_is_participle(w) for w in words)):
            continue
        return _titlecase(candidate)
    return None


# --- city ---------------------------------------------------------------------

_CITY = rf"({_NAME_WORD}(?:\s+{_NAME_WORD})?)"
# A place name, unlike a person's, does not carry an apostrophe here — and
# allowing one lets a contraction be read as the first word of the span.
_PLACE_WORD = r"(?!(?:%s)\b)[A-Za-z][A-Za-z-]*" % "|".join(sorted(NAME_STOPWORDS))
_CITY_PATTERNS = (
    re.compile(rf"\bi\s*(?:am|'m|’m)\s+from\s+{_CITY}", re.IGNORECASE),
    re.compile(rf"\b(?:based|living|live|located|stay|staying)\s+in\s+{_CITY}", re.IGNORECASE),
    re.compile(rf"\bfrom\s+{_CITY}", re.IGNORECASE),
    re.compile(rf"\b{_CITY}\s+se\b", re.IGNORECASE),
    # "Mumbai based", "Pune born" — the locative marker after the span. Last,
    # so "based in X" still wins when a clause carries both forms.
    #
    # This is the only city pattern with no trigger in front of the span, so it
    # is the only one that has to say where a span may *start*. Without the
    # lookbehind and the apostrophe-free word, "I'm Mumbai based" matches from
    # the "I" and stores the city as "I'm Mumbai" — `_NAME_WORD` treats a
    # contraction as one word, which is right for O'Brien and wrong here.
    re.compile(rf"(?<![A-Za-z'’-])({_PLACE_WORD}(?:\s+{_PLACE_WORD})?)"
               rf"(?=\s+(?:%s)\b)" % "|".join(_LOCATIVE_MARKERS),
               re.IGNORECASE),
)


def find_city(clause: str) -> str | None:
    for pattern in _CITY_PATTERNS:
        m = pattern.search(clause)
        if not m:
            continue
        candidate = m.group(1).strip(" .'’-")
        if not candidate or any(w.lower() in NAME_STOPWORDS for w in candidate.split()):
            continue
        if _truncates_phrase(clause, m.end(1)):
            continue
        return _titlecase(candidate)
    return None


# --- money --------------------------------------------------------------------

_CEILING = re.compile(
    r"\b(?:under|below|max(?:imum)?|upto|up\s+to|at\s+most|within|less\s+than|"
    r"no(?:t)?\s+more\s+than|nothing\s+(?:over|above|more\s+than)|not\s+above|"
    r"no\s+higher\s+than|ceiling|capped\s+at|"
    r"tak|se\s+z?y?ada\s+nahi|se\s+jada\s+nahi)\b",
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

# Money nouns that name a concept of their own. An amount beside one of these
# belongs to that concept, not to the user's budget — "turnover pichle saal 42
# lakh" is a company's revenue, and storing it as a shopping ceiling is the
# misrouting the type guard alone cannot catch, because both are money.
_OTHER_MONEY_CONCEPT = re.compile(
    r"\b(?:insured|insurance|premium|turnover|revenue|salary|wage|wages|"
    r"invoice|rent|deposit|emi|instalment|installment|refund|valuation|"
    r"payout|claim|fine|penalty|tax|gst|duty|freight|commission)\b",
    re.IGNORECASE,
)


def names_another_money_concept(clause: str) -> bool:
    """Whether this clause's money belongs to something other than the budget.

    An explicit budget word wins: "rent budget is 35000" says both, and the
    one the user actually named is the budget.
    """
    if _BUDGET_WORD.search(clause):
        return False
    return bool(_OTHER_MONEY_CONCEPT.search(clause))


def find_money(clause: str) -> tuple[int, bool] | None:
    """(amount, is_ceiling), or None when nothing money-like is present.

    The money decision belongs to `valuetype.classify`, not to a second copy
    of the rules here — the two drifted, and this one had the looser test:
    a ceiling word alone ("max", "over") made any nearby number an amount, so
    "max load per container is 24 tonnes" became ₹24. A qualifier says how
    much, never of what.

    `is_ceiling` is still read from this clause, because that part genuinely
    is a matter of phrasing rather than of the value's kind.
    """
    ceiling = bool(_CEILING.search(clause))
    # scan each number in the clause: the first one that reads as money wins,
    # so "16GB RAM and a 5k budget" still finds the budget
    for m in re.finditer(r"[₹$€£]?\s*\d[\d,. ]*\s*[A-Za-z][A-Za-z.]*|[₹$€£]?\s*\d[\d,.]*", clause):
        span = m.group(0).strip()
        if not span:
            continue
        reading = valuetype.classify(span, context=clause)
        if reading.kind != valuetype.MONEY or not reading.number:
            continue
        if reading.number <= 0:
            continue
        return int(reading.number), ceiling
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
# A stated year is part of the date. Without the optional trailing group,
# "15 Aug 2026" captured only "15 Aug" and the year was silently dropped —
# the normalizer then *inferred* a year it had actually been told.
_ABS_DATE = re.compile(
    rf"\b(\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{_MONTHS})\.?(?:,?\s+\d{{4}})?"
    rf"|(?:{_MONTHS})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+\d{{4}})?)\b",
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

# --- capture validation -------------------------------------------------------
#
# A free-text rule captures whatever follows its trigger, so "I need it before
# 15 August" yielded the requirement "it before 15 August": meaningless, a
# duplicate of the deadline, and — because state is append-only — re-sent to
# the model on every later turn with nothing to garbage-collect it.
#
# The trigger word is not the problem; the unvalidated tail is. A capture has
# to name something before it may become a fact.

# leading words that carry no meaning but do not invalidate what follows
_LEADING_FILLER = frozenset({
    "the", "a", "an", "some", "any", "my", "our", "your", "its", "their",
    "one", "at", "least", "about", "around", "approximately", "roughly",
})

# a span *starting* with one of these is a fragment, not a thing
_FRAGMENT_HEADS = frozenset({
    "it", "this", "that", "these", "those", "them", "they", "he", "she",
    "him", "her", "us", "we", "you", "i", "me", "who", "which", "what",
    "before", "after", "by", "with", "from", "to", "for", "of", "in", "on",
    "until", "till", "than", "then", "and", "or", "but", "so", "because",
    "is", "are", "was", "were", "be", "been", "being", "will", "would",
    "not", "no", "yet", "very", "really", "just",
})

# A span that is only a date. The month name is required when letters are
# present — without that, `[a-z]*` swallowed anything, so "8 cores" read as a
# date and a real requirement was thrown away.
_DATEISH = re.compile(
    r"^\d{1,4}[\s./-]*(?:st|nd|rd|th)?"
    r"(?:[\s./-]*(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*)?"
    r"[\s,./-]*\d{0,4}$",
    re.IGNORECASE,
)


def valid_capture(span: str | None) -> str | None:
    """Trim a free-text capture to a real span, or reject it.

    Filler at the head is stripped ("a landing page" -> "landing page") because
    the noun is still there. A pronoun or preposition at the head is fatal: it
    means the rule matched a tail rather than a thing.
    """
    if not span:
        return None
    text = " ".join(str(span).split()).strip(" .,;:!?-–—")
    if not text:
        return None

    words = text.split()
    while words and words[0].lower().strip(".,") in _LEADING_FILLER:
        words = words[1:]
    if not words:
        return None

    if words[0].lower().strip(".,'") in _FRAGMENT_HEADS:
        return None

    cleaned = " ".join(words)
    # a bare date or number belongs in its own typed field, never in free text
    if _DATEISH.match(cleaned) or not re.search(r"[A-Za-z]{2}", cleaned):
        return None
    return cleaned


# --- generic assignments ------------------------------------------------------
#
# Every field above needed its own hand-written pattern, which is why anything
# outside name / city / budget / deadline / contact extracted nothing at all:
# a real user asking about a flight, a flat or a doctor's appointment hit no
# rule and StateJar remembered nothing.
#
# These patterns do not know any field names. They find the *shape* of an
# assertion — "my X is Y", "X: Y", "set X to Y" — and hand the pair to the
# canonical registry, which decides whether X is a field StateJar keeps. Adding
# a field to the registry therefore makes it extractable everywhere at once,
# with no new regex, and an unrecognised X lands in quarantine where it becomes
# the evidence for adding one.

_KEY_CHARS = r"[A-Za-z][A-Za-z _-]{0,28}"
# Stops at a clause boundary, so "my destination is Goa and my budget is 40k"
# does not make the destination "Goa and my budget is 40k". A dot only ends
# the value when it ends the sentence — otherwise "meera@example.com" and
# "Next.js" get truncated mid-token.
_VALUE = r"(?:(?!\s+(?:and|aur|but)\s+)(?!\.(?:\s|$))[^,;!?\n]){1,80}"

_ASSIGNMENT_PATTERNS = (
    # "my budget is 5000", "my preferred contact is email"
    re.compile(rf"\bmy\s+(?P<key>{_KEY_CHARS}?)\s+(?:is|are|=|:)\s+(?P<val>{_VALUE})",
               re.IGNORECASE),
    # "set the deadline to 15 Aug", "change destination to Goa"
    re.compile(rf"\b(?:set|change|update|make)\s+(?:my|the)?\s*(?P<key>{_KEY_CHARS}?)"
               rf"\s+(?:to|as|=)\s+(?P<val>{_VALUE})", re.IGNORECASE),
    # "destination: Goa", "bedrooms = 3" — a labelled field, form-style
    re.compile(rf"(?:^|[,;\n])\s*(?P<key>{_KEY_CHARS}?)\s*[:=]\s+(?P<val>{_VALUE})",
               re.IGNORECASE),
    # "budget of 50k", "a party of 4"
    re.compile(rf"\b(?P<key>{_KEY_CHARS}?)\s+of\s+(?P<val>{_VALUE})", re.IGNORECASE),
    # "prefer window seat", "I want the premium plan"
    re.compile(rf"\b(?:i\s+)?(?:prefer|want|choose|pick|select)\s+(?:the\s+)?"
               rf"(?P<val>{_VALUE})", re.IGNORECASE),
)

# A trailing verb belongs to the sentence, not to the field name: in "my
# deadline is", the key is "deadline". Strip these so "my delivery address is"
# resolves rather than missing by one word.
_KEY_TRIM = re.compile(r"^(?:the|a|an|my|our|your)\s+|\s+(?:is|are|was|were)$",
                       re.IGNORECASE)


def find_assignments(clause: str) -> list[tuple[str, str]]:
    """(raw_key, raw_value) pairs asserted in this clause.

    Deliberately says nothing about which keys are real — that is the
    registry's job. Returning a pair the registry rejects is the intended
    outcome for an unknown field, not a failure.
    """
    found: list[tuple[str, str]] = []
    for pattern in _ASSIGNMENT_PATTERNS:
        for m in pattern.finditer(clause):
            groups = m.groupdict()
            value = (groups.get("val") or "").strip(" .,;:!?")
            if not value:
                continue
            # the preference form has no key; the value names itself and the
            # registry's enum normalizers decide which field it belongs to
            key = (groups.get("key") or "").strip()
            key = _KEY_TRIM.sub("", key).strip().replace(" ", "_").replace("-", "_")
            if key:
                found.append((key.lower(), value))
            else:
                found.append(("", value))
    return found


# Aliases that are also ordinary English. Matched only in an unmistakably
# declarative form, because the loose one turns conversation into facts:
# "the area is nice" became area="nice", "what's the name of that place?"
# named the user "That Place". A wrong fact is worse than a missing one — it
# persists in state and is re-sent to the model on every later turn, which is
# the same harm BUG-2 described, arriving by a different door.
#
# Typed fields are not listed here and do not need to be: a money, date, int
# or enum normalizer rejects "nice" on its own. Only string- and list-valued
# fields accept anything, so only those need the syntax to carry the weight.
GENERIC_ALIASES = frozenset({
    "name", "city", "area", "role", "language", "plan", "item", "task",
    "date", "mode", "number", "count", "people", "place", "from", "channel",
    "brand", "color", "colour", "text", "due", "needs", "goal", "decision",
    "choice", "contact", "address", "condition", "complaint", "location",
    "town", "residence", "org", "company", "technology", "platform",
    "selected", "chosen", "picked", "intent", "purpose", "aim", "objective",
})


def _alternation(surfaces: list[str]) -> str:
    """`payment_method` typed as "payment method" or "payment-method".

    re.escape leaves `_` alone (it has not escaped word characters since 3.7),
    so the substitution happens on the raw alias *before* escaping. Doing it
    after silently matched nothing, which is why every multi-word field looked
    unextractable.
    """
    return "|".join(
        r"[\s_-]".join(re.escape(part) for part in s.split("_"))
        # longest first so "payment method" wins over "payment"
        for s in sorted(surfaces, key=len, reverse=True)
    )


def build_alias_matcher(aliases: dict[str, str]) -> dict[str, Any]:
    """Compile the registry's own vocabulary into matchers.

    The generic patterns above need a separator ("my age is 34"), but people
    write forms too: "age 34", "allergies penicillin", "payment method UPI".
    Matching a bare `<key> <value>` juxtaposition with an *arbitrary* key
    pattern would turn any two adjacent words into a fact, so the key side is
    the registry's actual alias list — an alias that is not a real field
    simply does not exist.

    Distinctive aliases get the loose form. Everyday words (GENERIC_ALIASES)
    get a strict one: a colon, an equals, or an explicit "my X is Y".
    """
    lookup = {s.replace("_", " ").lower(): path for s, path in aliases.items()}
    loose = [s for s in aliases if s.lower() not in GENERIC_ALIASES]
    strict = [s for s in aliases if s.lower() in GENERIC_ALIASES]

    patterns: list[Any] = []
    if loose:
        alt = _alternation(loose)
        patterns.append(re.compile(
            rf"\b(?P<key>{alt})\b\s*(?:is|are|:|=|-|of)?\s+(?P<val>{_VALUE})",
            re.IGNORECASE))
        # "2 passengers", "5 years experience", "3 bedrooms"
        patterns.append(re.compile(
            rf"\b(?P<val>\d[\d,.]*)\s*(?:years?\s+(?:of\s+)?)?(?P<key>{alt})\b",
            re.IGNORECASE))
    if strict:
        alt = _alternation(strict)
        # labelled, form-style: "name: Farhan", at a line or clause start
        patterns.append(re.compile(
            rf"(?:^|[,;\n])\s*(?P<key>{alt})\s*[:=]\s*(?P<val>{_VALUE})",
            re.IGNORECASE))
        # possessive and declarative: "my city is Jaipur"
        patterns.append(re.compile(
            rf"\bmy\s+(?P<key>{alt})\s+(?:is|are|was|:|=)\s+(?P<val>{_VALUE})",
            re.IGNORECASE))
        # A whole short clause that is nothing but the field and its value:
        # "name Aarav", "city Pune". Anchoring to both ends is what keeps this
        # safe — "the name of that place" and "the city was crowded" do not
        # begin with the alias, so they cannot match.
        patterns.append(re.compile(
            rf"^(?P<key>{alt})\s+(?P<val>[^\s,;:]+(?:\s+[^\s,;:]+)?)\s*$",
            re.IGNORECASE))
    return {"patterns": patterns, "lookup": lookup}


def find_alias_assignments(
    clause: str, matcher: dict[str, Any]
) -> list[tuple[str, str]]:
    """(canonical_path, raw_value) pairs, keyed by the registry's vocabulary."""
    lookup = matcher["lookup"]
    found: list[tuple[str, str]] = []
    for pattern in matcher["patterns"]:
        for m in pattern.finditer(clause):
            key = " ".join(m.group("key").replace("_", " ").replace("-", " ").split())
            path = lookup.get(key.lower())
            value = (m.group("val") or "").strip(" .,;:!?")
            if path and value:
                found.append((path, value))
    return found


# "from Pune to Goa" is a journey, not a home town. The city rule reads the
# same words as a residence, so this runs first and claims them when both ends
# are present — one "from X" is where you live, "from X to Y" is a route.
_ROUTE = re.compile(
    rf"\bfrom\s+({_NAME_WORD}(?:\s+{_NAME_WORD})?)\s+to\s+({_NAME_WORD}(?:\s+{_NAME_WORD})?)",
    re.IGNORECASE,
)


# "order 3 t-shirts", "book 2 tickets" — the counted noun is arbitrary, so the
# count is anchored on the verb rather than on a vocabulary of things.
_ORDER_QTY = re.compile(
    r"\b(?:order|book|buy|reserve|get|need|want|add)\s+(\d{1,4})\s+[A-Za-z]",
    re.IGNORECASE,
)

_EMPLOYER = re.compile(
    r"\b(?:work(?:ing|s)?\s+(?:at|for|with)|employed\s+(?:at|by)|"
    r"i(?:'m| am)\s+(?:at|with))\s+"
    rf"({_NAME_WORD}(?:\s+{_NAME_WORD})?)",
    re.IGNORECASE,
)

# Payment is stated in forms the generic patterns miss: "cash on delivery",
# "pay by card", "I'll use UPI". Its vocabulary is small and unambiguous
# enough to be worth its own rule rather than a keyless enum guess, which
# would also fire on "a light lunch".
_PAYMENT = re.compile(
    r"\b(?:pay(?:ing|ment)?\s+(?:by|via|with|using|through|mode|method)?\s*|"
    r"i(?:'ll| will)\s+(?:pay\s+)?(?:use|with)\s+)?"
    r"(cash\s+on\s+delivery|cod|upi|gpay|google\s+pay|phonepe|paytm|"
    r"net\s?banking|credit\s+card|debit\s+card|card|paypal|wallet|cash)\b",
    re.IGNORECASE,
)


def find_order_quantity(clause: str) -> int | None:
    m = _ORDER_QTY.search(clause)
    return int(m.group(1)) if m else None


def find_employer(clause: str) -> str | None:
    m = _EMPLOYER.search(clause)
    if not m:
        return None
    value = m.group(1).strip(" .'’-")
    if not value or any(w.lower() in NAME_STOPWORDS for w in value.split()):
        return None
    # the same two-word cap as the identity spans, and the same failure:
    # "work at Tata Consultancy Services" stored the employer as "Tata
    # Consultancy", which is a different company from the one that was said
    if _truncates_phrase(clause, m.end(1)):
        return None
    return _titlecase(value)


def find_payment(clause: str) -> str | None:
    m = _PAYMENT.search(clause)
    return m.group(1) if m else None


def states_a_route(clause: str) -> bool:
    """Whether the clause names a from/to pair at all.

    Separate from `find_route` because a clause can state a route whose ends
    are not clean enough to store. It still must not fall through to the city
    rule, which would read a shipping origin as the user's home town — the
    exact misread the route rule exists to prevent.
    """
    return _ROUTE.search(clause) is not None


def find_route(clause: str) -> tuple[str, str] | None:
    """(origin, destination) when the clause states both ends *cleanly*."""
    m = _ROUTE.search(clause)
    if not m:
        return None
    origin, destination = m.group(1).strip(" .'’-"), m.group(2).strip(" .'’-")
    for value in (origin, destination):
        if not value or any(w.lower() in NAME_STOPWORDS for w in value.split()):
            return None
    # The origin is fenced by the " to " that follows it; the destination is
    # fenced by nothing, so it truncates exactly as the city span did —
    # "Delhi to Navi Mumbai Airport" delivered to "Navi Mumbai".
    if _truncates_phrase(clause, m.end(2)):
        return None
    return _titlecase(origin), _titlecase(destination)


# --- open extraction ----------------------------------------------------------
#
# Everything above needs a field to aim at. These patterns do not: they find
# "<some noun phrase> <some value>" and hand both back as free text, so a
# container load limit, a firing schedule and a feed conversion ratio are all
# findable without anyone having declared them first.
#
# The caller keeps only values that classify as *measurable* — a quantity, a
# date, an amount, an identifier. That restriction is what stops "the area is
# nice and quiet" becoming a stored fact: open extraction over free-text
# values turns conversation into state, which is the failure mode the whole
# precision pass was about. Categorical concepts are tier 3's job, where a
# model can tell an assertion from small talk.

# A comma between digits belongs to the number, exactly as in the clause
# splitter — excluding it outright truncated "4,200 birds" to "4". A
# coordinating word ends the value, so "MY NAME IS SANJANA AND MY BUDGET IS
# 5000" does not make the name the rest of the sentence.
_OPEN_VALUE = r"(?:(?<=\d),(?=\d)|(?!\s+(?:and|aur|but)\s+)[^,;!?\n]){1,60}"
_OPEN_CONCEPT = r"[A-Za-z][A-Za-z0-9 _/-]{2,44}?"

_OPEN_PATTERNS = (
    # "container load limit is now 26 tonnes", "shipment weighs 1,240 kg"
    re.compile(
        rf"\b(?P<key>{_OPEN_CONCEPT})\s+"
        r"(?:is|are|was|were|weighs|weighed|measures|holds|takes|costs|"
        r"totals|equals|comes\s+to|runs|sits\s+at|stands\s+at)\s+"
        r"(?:now|currently|about|around|approximately|roughly|at)?\s*"
        rf"(?P<val>{_OPEN_VALUE})",
        re.IGNORECASE),
    # "insured for $8,500", "hold at 20 minutes", "bisque at cone 06"
    re.compile(
        rf"\b(?P<key>{_OPEN_CONCEPT})\s+(?:for|at|of|to)\s+(?P<val>{_OPEN_VALUE})",
        re.IGNORECASE),
    # "transit time 11 days", "hold 20 minutes at peak" — a short label
    # followed by a measurement. The value must carry a unit, which is what
    # keeps this from matching any two adjacent tokens.
    re.compile(
        r"\b(?P<key>[A-Za-z][A-Za-z _/-]{2,28}?)\s+"
        r"(?P<val>[₹$€£]?\s*\d[\d,.]*\s*[A-Za-z%]{1,14})\b",
        re.IGNORECASE),
)

# A concept phrase that is really a question or a pronoun is not a concept.
_NOT_A_CONCEPT = re.compile(
    r"^(?:what|which|who|when|where|why|how|can|could|would|should|do|does|"
    r"did|is|are|was|were|the|a|an|it|this|that|there|here|i|we|you|they|"
    r"and|or|but|so|then|now|next|"
    # Discourse labels, and the verbs the qualified-date and update rules
    # already own. "Update:" names no concept, and "ends 19 September" is the
    # end of something else — reading either as a concept of its own is how
    # `dynamic.update` and `dynamic.ends` appeared beside the real fields.
    r"update|updates|correction|note|notes|fyi|also|actually|btw|ps|"
    r"starts?|starting|begins?|beginning|ends?|ending|finishes?|closes?|"
    r"push|move|change|changes|set|shift|bump|revise|ignore|forget|drop)\b",
    re.IGNORECASE,
)


def is_a_concept(name: str) -> bool:
    """Whether a captured phrase can name a concept at all.

    Exported because the same judgement is needed wherever a free-text key
    becomes a dynamic field — otherwise "Update: ..." creates a concept called
    "update" through the labelled-form rule while the open patterns correctly
    refuse it.
    """
    name = re.sub(r"^(?:the|a|an|my|our|your)\s+", "", (name or "").strip(),
                  flags=re.IGNORECASE).strip()
    return bool(name) and not _NOT_A_CONCEPT.match(name)


def find_open_facts(clause: str) -> list[tuple[str, str]]:
    """(concept, value) pairs, with no notion of which fields exist.

    Deliberately says nothing about whether the concept is known — that is the
    router's decision, and an unfamiliar one becomes a dynamic field rather
    than being dropped.
    """
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    claimed: set[str] = set()
    for pattern in _OPEN_PATTERNS:
        for m in pattern.finditer(clause):
            concept = " ".join((m.group("key") or "").split()).strip(" .,;:-")
            value = " ".join((m.group("val") or "").split()).strip(" .,;:-")
            if not concept or not value:
                continue
            if _NOT_A_CONCEPT.match(concept):
                # strip a leading article and retry: "the container load limit"
                concept = re.sub(r"^(?:the|a|an|my|our|your)\s+", "", concept,
                                 flags=re.IGNORECASE).strip()
                if not concept or _NOT_A_CONCEPT.match(concept):
                    continue
            key = concept.lower()
            # One value, one concept. The patterns overlap by design (the verb
            # form is the precise one, the juxtaposition the fallback), so
            # without this "shipment weighs 1,240 kg" yields both "shipment"
            # and "shipment weighs" for the same measurement. Containment, not
            # equality: a looser pattern often captures a *prefix* of the same
            # value — "3rd Nov" and "3rd" are one date read twice.
            lowered = value.lower()
            if key in seen or any(
                lowered in c or c in lowered for c in claimed
            ):
                continue
            seen.add(key)
            claimed.add(lowered)
            found.append((concept, value))
    return found


# --- qualifiers, updates, retractions -----------------------------------------

# "Booking starts 12 September" is not a deadline. Storing it as one is what
# let a later "push the end date" overwrite the *start* and destroy it — the
# unqualified `deadline` field has no way to tell the two apart, so a
# qualified date must never land there.
_QUALIFIED_DATE = re.compile(
    r"(?:\b(?P<key>[A-Za-z][A-Za-z ]{0,28}?)\s+)?"
    r"\b(?P<q>starts?|starting|begins?|beginning|opens?|"
    r"ends?|ending|finishes?|finishing|closes?|closing)\s+"
    r"(?:on\s+|at\s+|from\s+)?(?P<val>[^,;.!?\n]{3,40})",
    re.IGNORECASE,
)
_START_WORDS = ("start", "begin", "open")

# "Push the end date to 22 September" — an update that names which end it means.
_QUALIFIER_UPDATE = re.compile(
    r"\b(?:push|move|change|set|update|shift|make|bump|revise)\s+"
    r"(?:the\s+|my\s+|our\s+)?"
    r"(?P<q>start|end|min|minimum|max|maximum|first|last|final|target)\s*"
    r"(?:date|time|day|value|figure|amount|limit|number)?\s+"
    r"(?:to|=|as|into)\s+(?P<val>[^,;.!?\n]{1,40})",
    re.IGNORECASE,
)

# "Actually ignore the insurance figure" / "we're not insuring this one"
_RETRACTION = re.compile(
    r"\b(?:ignore|forget|disregard|drop|remove|scratch|cancel|delete|"
    r"never\s+mind|nevermind|strike)\s+"
    r"(?:the\s+|that\s+|my\s+|our\s+|any\s+)?"
    r"(?P<key>[A-Za-z][A-Za-z ]{2,38}?)"
    r"(?:\s+(?:figure|value|number|field|entry|detail|bit|part|one))?"
    r"(?=\s*[,;.!?]|\s*$|\s+(?:we|i|for|from|on|please))",
    re.IGNORECASE,
)
_NEGATION = re.compile(
    r"\b(?:we(?:'re| are)|i(?:'m| am)|it(?:'s| is))\s+not\s+"
    r"(?P<key>[A-Za-z][A-Za-z ]{2,38}?)(?=\s*[,;.!?]|\s*$|\s+(?:this|that|it))",
    re.IGNORECASE,
)


def find_qualified_dates(clause: str) -> list[tuple[str, str, str]]:
    """(concept, qualifier, raw_date) for dates that name which end they are."""
    out: list[tuple[str, str, str]] = []
    for m in _QUALIFIED_DATE.finditer(clause):
        verb = m.group("q").lower()
        qualifier = "start" if verb.startswith(_START_WORDS) else "end"
        value = " ".join((m.group("val") or "").split()).strip(" .,;:")
        if not value:
            continue
        concept = " ".join((m.group("key") or "").split()).strip(" .,;:")
        out.append((concept, qualifier, value))
    return out


def find_qualifier_updates(clause: str) -> list[tuple[str, str]]:
    """(qualifier, raw_value) for an update that names the end it targets."""
    out: list[tuple[str, str]] = []
    for m in _QUALIFIER_UPDATE.finditer(clause):
        value = " ".join((m.group("val") or "").split()).strip(" .,;:")
        if value:
            out.append((m.group("q").lower(), value))
    return out


def find_retractions(clause: str) -> list[str]:
    """Concept names the message withdraws rather than asserts."""
    out: list[str] = []
    for pattern in (_RETRACTION, _NEGATION):
        for m in pattern.finditer(clause):
            concept = " ".join((m.group("key") or "").split()).strip(" .,;:")
            concept = re.sub(r"^(?:the|a|an|my|our|that|this)\s+", "", concept,
                             flags=re.IGNORECASE).strip()
            if concept and concept.lower() not in NAME_STOPWORDS:
                out.append(concept)
    return out


def prune_subsumed(items: list[str]) -> list[str]:
    """Drop entries that merely contain a shorter entry.

    `split_clauses` deliberately yields the whole utterance as a final clause
    so full-context patterns still fire, which means a free-text rule matches
    both "landing page" and "landing page and my goal is to launch by Friday".
    Keeping both stores the same requirement twice, the second time with the
    next clause glued on.
    """
    kept: list[str] = []
    for item in sorted(items, key=len):
        lowered = item.lower()
        if not any(re.search(rf"\b{re.escape(k.lower())}\b", lowered) for k in kept):
            kept.append(item)
    return sorted(kept)

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
    "valid_capture", "prune_subsumed", "find_assignments", "find_alias_assignments", "build_alias_matcher", "find_route",
    "find_open_facts", "find_qualified_dates", "find_qualifier_updates",
    "is_a_concept",
    "find_retractions", "find_order_quantity", "find_employer", "find_payment",
    "names_another_money_concept",
    "_DECISION", "_DECISION_HI", "_GOAL", "_REQUIREMENT",
]
