"""What kind of thing a value is, inferred from the span it was written in.

The alias matcher fired on lexical proximity alone: "max load per container is
24 tonnes" put 24 into `constraints.budget.max` as ₹24, because "max" is a
ceiling word and a bare number near a ceiling word was treated as money. The
same path turned 1,240 kg into ₹1,240,000 and a company's turnover into a
shopping budget.

That is worse than extracting nothing. State becomes confidently wrong and the
model repeats it downstream — the reply to the shipment message offered a
"cost estimate against your ₹1,240,000 budget".

So matching fails closed. A value is classified from its own span, and a match
is only accepted when the value's kind is compatible with the field's declared
type. Incompatible means rejected and quarantined, never coerced.

The rule that matters most: **money requires a positive money signal.** A
currency symbol, a currency word, or a money noun in the span. A qualifier
like "max" or "over" is not one. There is no default-to-INR on a bare number —
that single default is what produced the tonnage bug.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.schema import normalizers as norm

# --- kinds --------------------------------------------------------------------

MONEY = "money"
QUANTITY = "quantity"        # a physical measure: 24 tonnes, 1240 kg
DURATION = "duration"        # 11 days, 20 minutes
DATE = "date"
PERCENT = "percent"
RATIO = "ratio"              # 1.68, 4:3
IDENTIFIER = "identifier"    # 27ABCDE1234F1Z5
COUNT = "count"              # a bare number of things: 4200 birds, 2 passengers
TEXT = "text"                # anything not numeric
UNKNOWN = "unknown"


# --- vocabulary ---------------------------------------------------------------

CURRENCY_SYMBOLS = {
    "₹": "INR", "$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY",
}
CURRENCY_WORDS = {
    "inr": "INR", "rs": "INR", "rs.": "INR", "rupee": "INR", "rupees": "INR",
    "rupaye": "INR", "paise": "INR",
    "usd": "USD", "dollar": "USD", "dollars": "USD",
    "eur": "EUR", "euro": "EUR", "euros": "EUR",
    "gbp": "GBP", "pound": "GBP", "pounds": "GBP",
    "yen": "JPY", "jpy": "JPY",
}
# Nouns that make a bare number monetary. Deliberately does NOT include
# qualifiers (max, under, over) — those say how much, not of what.
MONEY_NOUNS = frozenset({
    "budget", "price", "cost", "costs", "spend", "afford", "salary", "wage",
    "fee", "fees", "rent", "turnover", "revenue", "insured", "insurance",
    "premium", "invoice", "payment", "amount", "paisa", "paise", "package",
    "worth", "valued", "value", "charge", "charges", "quote", "quotation",
    "deposit", "emi", "instalment", "installment", "refund", "discount",
})

WEIGHT_UNITS = {
    "kg": "kg", "kgs": "kg", "kilo": "kg", "kilos": "kg", "kilogram": "kg",
    "kilograms": "kg", "g": "g", "gram": "g", "grams": "g",
    "tonne": "tonnes", "tonnes": "tonnes", "ton": "tonnes", "tons": "tonnes",
    "mt": "tonnes", "quintal": "quintal", "lb": "lb", "lbs": "lb",
    "pound": "lb", "pounds": "lb",
}
VOLUME_UNITS = {
    "l": "l", "litre": "l", "litres": "l", "liter": "l", "liters": "l",
    "ml": "ml", "gallon": "gal", "gallons": "gal",
}
LENGTH_UNITS = {
    "m": "m", "metre": "m", "metres": "m", "meter": "m", "meters": "m",
    "km": "km", "cm": "cm", "mm": "mm", "ft": "ft", "feet": "ft", "inch": "in",
    "inches": "in", "sqft": "sqft", "sqm": "sqm",
}
DATA_UNITS = {
    "kb": "kb", "mb": "mb", "gb": "gb", "tb": "tb", "byte": "b", "bytes": "b",
}
# "pound" and "value" are in two tables; a currency reading wins only when a
# currency marker is also present, which _detect_currency checks first.
MEASURE_UNITS = {**WEIGHT_UNITS, **VOLUME_UNITS, **LENGTH_UNITS, **DATA_UNITS}

TIME_UNITS = {
    "second": "seconds", "seconds": "seconds", "sec": "seconds", "secs": "seconds",
    "minute": "minutes", "minutes": "minutes", "min": "minutes", "mins": "minutes",
    "hour": "hours", "hours": "hours", "hr": "hours", "hrs": "hours",
    "day": "days", "days": "days", "week": "weeks", "weeks": "weeks",
    "month": "months", "months": "months", "year": "years", "years": "years",
    "yr": "years", "yrs": "years",
}

# Countable nouns keep a number a count rather than a bare unknown.
COUNT_NOUNS = frozenset({
    "birds", "bird", "head", "units", "unit", "pallets", "pallet", "pieces",
    "piece", "items", "item", "people", "persons", "passengers", "guests",
    "seats", "rooms", "bedrooms", "boxes", "cartons", "bags", "sacks",
    "containers", "container", "tickets", "copies", "students", "employees",
})

RATIO_WORDS = frozenset({"ratio", "rate", "factor", "index", "fcr", "multiple"})

_THIN_SPACES = "    "


# --- number parsing -----------------------------------------------------------

# Grouped: Western (1,240 / 1,240,000) and Indian (12,40,000 / 1,24,000).
# The group sizes differ, so both are accepted and validated rather than
# stripped blindly — "1,2345" is not a grouped number and must not become
# 12345.
_GROUPED = re.compile(r"^\d{1,3}(?:,\d{2,3})+$")
_SPACE_GROUPED = re.compile(r"^\d{1,3}(?:[ %s]\d{3})+$" % re.escape(_THIN_SPACES))
_PLAIN = re.compile(r"^\d+(?:\.\d+)?$")


def parse_number(text: str) -> float | None:
    """A written number to its value, across grouping conventions.

    `1,240` was being read as 1 — the parse split on the comma and took the
    first group, so a 1,240 kg shipment and a 4,200 bird flock both lost three
    digits silently. Grouping is validated rather than stripped, so a string
    that merely contains commas is rejected instead of mangled.
    """
    if text is None:
        return None
    raw = str(text).strip()
    if not raw:
        return None

    # a decimal tail is separated first, so grouping only ever sees the
    # integer part ("12,40,000.50")
    integer, dot, fraction = raw.partition(".")
    if dot and not fraction.isdigit():
        integer, dot, fraction = raw, "", ""

    cleaned: str | None = None
    if _PLAIN.match(integer):
        cleaned = integer
    elif _GROUPED.match(integer):
        cleaned = integer.replace(",", "")
    elif _SPACE_GROUPED.match(integer):
        cleaned = re.sub(r"[ %s]" % re.escape(_THIN_SPACES), "", integer)
    if cleaned is None:
        return None

    try:
        return float(f"{cleaned}.{fraction}") if dot and fraction else float(cleaned)
    except ValueError:
        return None


def format_number(value: float, style: str = "western") -> str:
    """Render a number in a grouping style. Exists so parse/format round-trips
    can be property-tested rather than asserted case by case."""
    negative = value < 0
    value = abs(value)
    whole = int(value)
    fraction = value - whole
    digits = str(whole)

    if style == "plain":
        grouped = digits
    elif style == "indian":
        if len(digits) <= 3:
            grouped = digits
        else:
            head, tail = digits[:-3], digits[-3:]
            parts = []
            while len(head) > 2:
                parts.insert(0, head[-2:])
                head = head[:-2]
            if head:
                parts.insert(0, head)
            grouped = ",".join([*parts, tail])
    elif style == "space":
        grouped = f"{whole:,}".replace(",", " ")
    else:  # western
        grouped = f"{whole:,}"

    out = f"-{grouped}" if negative else grouped
    if fraction:
        out += f"{fraction:.10f}".rstrip("0").lstrip("0")
    return out


# --- classification -----------------------------------------------------------


@dataclass(frozen=True)
class Reading:
    """What a span appears to be saying."""

    kind: str
    number: float | None = None
    unit: str | None = None
    currency: str | None = None

    @property
    def is_numeric(self) -> bool:
        return self.number is not None


_NUMBER_IN_SPAN = re.compile(
    r"\d[\d,%s]*(?:\.\d+)?" % re.escape(_THIN_SPACES)
)
# k / lakh / crore, but never the "k" of "kg" — that k belongs to the unit and
# reading it as a scale turned 1,240 kg into 1,240,000.
_SCALE = re.compile(
    r"\b(k|thousand|lakhs?|lacs?|crores?|cr|m|mn|million|bn|billion)(?![a-z])",
    re.IGNORECASE,
)
_SCALE_VALUES = {
    "k": 1_000, "thousand": 1_000, "lakh": 100_000, "lakhs": 100_000,
    "lac": 100_000, "lacs": 100_000, "crore": 10_000_000, "crores": 10_000_000,
    "cr": 10_000_000, "m": 1_000_000, "mn": 1_000_000, "million": 1_000_000,
    "bn": 1_000_000_000, "billion": 1_000_000_000,
}

_IDENTIFIER = re.compile(r"^(?=.*\d)(?=.*[A-Za-z])[A-Z0-9][A-Z0-9\-/]{5,}$")
_PERCENT = re.compile(r"(\d[\d.,]*)\s*(?:%|per\s*cent|percent)", re.IGNORECASE)
_RATIO_PAIR = re.compile(r"^\d+\s*:\s*\d+$")


def _tokens(span: str) -> list[str]:
    return [t.strip(".,;:!?()") for t in re.split(r"[\s]+", span.lower()) if t]


_ATTACHED_CURRENCY = re.compile(
    r"\d\s*(%s)\b|\b(%s)\s*\d" % ("|".join(CURRENCY_WORDS), "|".join(CURRENCY_WORDS)),
    re.IGNORECASE,
)


def detect_currency(span: str) -> str | None:
    """A currency marker in the span, or None. There is no default.

    Removing the default is the point of this function existing. A bare number
    with no marker is not an amount of money, and the old default-to-INR is
    what let "24 tonnes" be stored as ₹24.
    """
    for symbol, code in CURRENCY_SYMBOLS.items():
        if symbol in span:
            return code
    for token in _tokens(span):
        if code := CURRENCY_WORDS.get(token):
            return code
    # written against the digits: "3000rs", "Rs2000"
    if m := _ATTACHED_CURRENCY.search(span):
        return CURRENCY_WORDS.get((m.group(1) or m.group(2)).lower())
    return None


def _unit_in(span: str, table: dict[str, str]) -> str | None:
    for token in _tokens(span):
        if unit := table.get(token):
            return unit
    # "24t", "1240kg" — the unit written against the digits
    m = re.search(r"\d\s*([A-Za-z]{1,10})\b", span)
    if m and (unit := table.get(m.group(1).lower())):
        return unit
    return None


def classify(span: str, *, context: str = "") -> Reading:
    """Infer what `span` is. `context` is the surrounding clause, if any.

    Money is the only kind that requires a positive signal: a currency marker
    or a money noun. Everything else is read from units and shape.
    """
    if span is None:
        return Reading(UNKNOWN)
    text = str(span).strip()
    if not text:
        return Reading(UNKNOWN)
    whole = f"{text} {context}".strip()

    if _IDENTIFIER.match(text.replace(" ", "")):
        return Reading(IDENTIFIER)

    if m := _PERCENT.search(text):
        return Reading(PERCENT, parse_number(m.group(1)), unit="%")

    if _RATIO_PAIR.match(text):
        return Reading(RATIO)

    # A span that is entirely a date is a date, whatever the sentence around
    # it mentions. Without this, "budget under 1500, deliver by 20 September"
    # read the 20 as money — the money noun was in the sentence, so every
    # number in the sentence inherited it.
    if norm.normalize_date(text) is not None:
        return Reading(DATE)

    number_match = _NUMBER_IN_SPAN.search(text)
    if not number_match:
        return Reading(TEXT)
    number = parse_number(number_match.group(0))
    if number is None:
        return Reading(TEXT)

    # a scale word multiplies, but only when it is its own token
    tail = text[number_match.end():]
    scaled = False
    if scale := _SCALE.match(tail.strip()):
        number *= _SCALE_VALUES[scale.group(1).lower()]
        scaled = True

    # Signals from the value's own span outrank signals from the sentence
    # around it. "4,200 birds" is a count even in a sentence about budgets —
    # otherwise a single money noun anywhere in the message makes every number
    # in it an amount, which is the proximity bug wearing a different hat.
    span_tokens = _tokens(text)
    context_tokens = _tokens(context)

    if unit := _unit_in(text, MEASURE_UNITS):
        # a currency marker never overrides a physical unit: "1,240 kg" is a
        # weight even in a sentence that also mentions price
        return Reading(QUANTITY, number, unit=unit)
    if unit := _unit_in(text, TIME_UNITS):
        return Reading(DURATION, number, unit=unit)
    if any(t in COUNT_NOUNS for t in span_tokens):
        return Reading(COUNT, number)
    if any(t in RATIO_WORDS for t in span_tokens):
        return Reading(RATIO, number)

    span_currency = detect_currency(text)
    if span_currency or any(t in MONEY_NOUNS for t in span_tokens):
        return Reading(MONEY, number, currency=span_currency)

    # nothing in the span itself settled it — now the sentence may speak
    if any(t in COUNT_NOUNS for t in context_tokens):
        return Reading(COUNT, number)
    if any(t in RATIO_WORDS for t in context_tokens):
        return Reading(RATIO, number)

    # Three money signals, none of them a qualifier: a currency marker, a
    # money noun, or a magnitude word. "5k" and "1 lakh" are written that way
    # about amounts far more often than about anything else — but "24" beside
    # "max" is not a signal, and treating it as one is the whole bug.
    currency = detect_currency(whole)
    if currency or any(t in MONEY_NOUNS for t in context_tokens) or scaled:
        return Reading(MONEY, number, currency=currency)

    if number != int(number) and abs(number) < 100:
        return Reading(RATIO, number)
    return Reading(COUNT, number)


# --- compatibility ------------------------------------------------------------

# A field's declared type against the kinds it must refuse. Absent from a set
# means "acceptable" — the field's own normalizer still has the final say.
INCOMPATIBLE: dict[str, frozenset[str]] = {
    # COUNT is refused deliberately: a bare number with no currency, no money
    # noun and no magnitude word is not an amount of money, however close it
    # sits to the word "max". That refusal is the tonnage fix.
    "money": frozenset({QUANTITY, DURATION, DATE, PERCENT, RATIO, IDENTIFIER,
                        COUNT}),
    "int": frozenset({MONEY, DATE, DURATION, IDENTIFIER}),
    "date": frozenset({MONEY, QUANTITY, DURATION, PERCENT, RATIO, IDENTIFIER}),
    "enum": frozenset({MONEY, QUANTITY, DURATION, DATE, PERCENT}),
    # string and list accept prose; their guard is the degenerate-value check
    "string": frozenset(),
    "list": frozenset(),
    "bool": frozenset(),
}


def is_compatible(field_type: str, reading: Reading) -> bool:
    """Whether a value of this kind may be stored in a field of this type."""
    if reading.kind in (UNKNOWN, TEXT):
        return True          # nothing inferred; the normalizer decides
    return reading.kind not in INCOMPATIBLE.get(field_type, frozenset())


__all__ = [
    "MONEY", "QUANTITY", "DURATION", "DATE", "PERCENT", "RATIO",
    "IDENTIFIER", "COUNT", "TEXT", "UNKNOWN",
    "Reading", "classify", "is_compatible", "detect_currency",
    "parse_number", "format_number",
    "CURRENCY_SYMBOLS", "CURRENCY_WORDS", "MONEY_NOUNS",
    "MEASURE_UNITS", "TIME_UNITS", "COUNT_NOUNS", "INCOMPATIBLE",
]
