"""Value normalizers — raw extractor output to canonical form.

Every canonical field declares one of these. They are pure functions with no
knowledge of state or storage: given whatever an extractor scraped out of a
sentence, return the canonical value or None to reject the write.

Rejection is the important half. A normalizer that guesses turns a typo into
a fact; returning None sends the value to the `_unmapped` quarantine where it
can be reviewed instead of silently corrupting state.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

# --- money --------------------------------------------------------------------

_SCALES = {
    "k": 1_000, "thousand": 1_000,
    "lakh": 100_000, "lakhs": 100_000, "lac": 100_000, "lacs": 100_000,
    "m": 1_000_000, "million": 1_000_000, "mn": 1_000_000,
    "cr": 10_000_000, "crore": 10_000_000, "crores": 10_000_000,
    "b": 1_000_000_000, "billion": 1_000_000_000,
}

_CURRENCY_TOKENS = {
    "INR": ("₹", "rs", "rs.", "inr", "rupee", "rupees", "rupaye"),
    "USD": ("$", "usd", "dollar", "dollars"),
    "EUR": ("€", "eur", "euro", "euros"),
    "GBP": ("£", "gbp", "pound", "pounds"),
}

DEFAULT_CURRENCY = "INR"

_WORD_UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}
_WORD_MULTIPLIERS = {"hundred": 100, "thousand": 1_000, "lakh": 100_000,
                     "million": 1_000_000, "crore": 10_000_000}

_NUMERIC = re.compile(r"(\d[\d,]*(?:\.\d+)?)")


def _words_to_number(text: str) -> int | None:
    """"seventy five thousand" -> 75000. None when it is not a number phrase."""
    words = [w for w in re.split(r"[\s-]+", text.lower()) if w and w != "and"]
    if not words or not all(w in _WORD_UNITS or w in _WORD_MULTIPLIERS for w in words):
        return None
    total = 0
    current = 0
    for word in words:
        if word in _WORD_UNITS:
            current += _WORD_UNITS[word]
        else:
            multiplier = _WORD_MULTIPLIERS[word]
            if multiplier == 100:
                current = max(current, 1) * 100
            else:
                total += max(current, 1) * multiplier
                current = 0
    return (total + current) or None


def _detect_currency(text: str) -> str | None:
    lowered = text.lower()
    for code, tokens in _CURRENCY_TOKENS.items():
        for token in tokens:
            if token in lowered:
                return code
    return None


def normalize_money(raw: Any) -> dict[str, Any] | None:
    """"₹75,000" / "75k" / "Rs. 75000" / "seventy five thousand" ->
    {"value": 75000, "currency": "INR"}.

    A bare int is accepted and assumed INR — extractors that already parsed
    a figure must not be forced to re-render it as a string first.
    """
    if isinstance(raw, dict):
        value = raw.get("value")
        if not isinstance(value, (int, float)) or value <= 0:
            return None
        return {"value": int(value), "currency": str(raw.get("currency") or DEFAULT_CURRENCY)}
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return {"value": int(raw), "currency": DEFAULT_CURRENCY} if raw > 0 else None
    if not isinstance(raw, str):
        return None

    text = raw.strip()
    if not text:
        return None
    currency = _detect_currency(text) or DEFAULT_CURRENCY

    match = _NUMERIC.search(text)
    if match:
        try:
            amount = float(match.group(1).replace(",", ""))
        except ValueError:
            return None
        # a scale word may follow the digits ("75 k", "1.5 lakh")
        tail = text[match.end():].strip().lower()
        scale_word = re.match(r"([a-z]+)", tail)
        if scale_word and scale_word.group(1) in _SCALES:
            amount *= _SCALES[scale_word.group(1)]
    else:
        spelled = _words_to_number(re.sub(r"[^\w\s-]", " ", text))
        if spelled is None:
            return None
        amount = float(spelled)

    return {"value": int(amount), "currency": currency} if amount > 0 else None


# --- date ---------------------------------------------------------------------

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_DMY = re.compile(rf"^(\d{{1,2}})(?:st|nd|rd|th)?\s+({'|'.join(_MONTHS)})\.?(?:\s+(\d{{4}}))?$", re.I)
_MDY = re.compile(rf"^({'|'.join(_MONTHS)})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?$", re.I)
_IN_N = re.compile(r"^in\s+(\d+)\s+(day|days|week|weeks|month|months)$", re.I)
_NEXT_WEEKDAY = re.compile(rf"^(?:next|coming|this)\s+({'|'.join(_WEEKDAYS)})$", re.I)


def _result(iso: str, raw: str, *, year_inferred: bool = False,
            ambiguous: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {"iso": iso, "raw": raw, "ambiguous": ambiguous}
    if year_inferred:
        # provenance, so a downstream reader knows the year was a guess
        out["year_inferred"] = True
    return out


def normalize_date(raw: Any, *, now: datetime | None = None) -> dict[str, Any] | None:
    """Any of the date shapes users type -> {"iso", "raw", "ambiguous"}.

    Relative forms resolve against `now` (the session start), and a missing
    year becomes the next future occurrence with year_inferred set — never a
    silent choice of the current year, which would put deadlines in the past.
    """
    if isinstance(raw, dict):
        return raw if raw.get("iso") else None
    if not isinstance(raw, str):
        return None
    text = " ".join(raw.strip().split())
    if not text:
        return None
    lowered = text.lower().rstrip(".,")
    today = (now or datetime.now(timezone.utc)).date()

    if m := _ISO.match(lowered):
        try:
            return _result(date(*map(int, m.groups())).isoformat(), text)
        except ValueError:
            return None

    for pattern, order in ((_DMY, "dmy"), (_MDY, "mdy")):
        if m := pattern.match(lowered):
            if order == "dmy":
                day, month_name, year = m.group(1), m.group(2), m.group(3)
            else:
                month_name, day, year = m.group(1), m.group(2), m.group(3)
            month = _MONTHS[month_name.lower()]
            try:
                if year:
                    return _result(date(int(year), month, int(day)).isoformat(), text)
                candidate = date(today.year, month, int(day))
                if candidate < today:                       # next occurrence
                    candidate = date(today.year + 1, month, int(day))
                return _result(candidate.isoformat(), text, year_inferred=True)
            except ValueError:
                return None

    if lowered in ("today",):
        return _result(today.isoformat(), text)
    if lowered in ("tomorrow", "kal"):
        return _result((today + timedelta(days=1)).isoformat(), text)
    if lowered in ("day after tomorrow", "parso"):
        return _result((today + timedelta(days=2)).isoformat(), text)

    if m := _IN_N.match(lowered):
        count, unit = int(m.group(1)), m.group(2).lower()
        days = count * {"day": 1, "days": 1, "week": 7, "weeks": 7,
                        "month": 30, "months": 30}[unit]
        return _result((today + timedelta(days=days)).isoformat(), text)

    if m := _NEXT_WEEKDAY.match(lowered):
        target = _WEEKDAYS[m.group(1).lower()]
        ahead = (target - today.weekday()) % 7 or 7
        return _result((today + timedelta(days=ahead)).isoformat(), text)

    if lowered in _WEEKDAYS:
        target = _WEEKDAYS[lowered]
        ahead = (target - today.weekday()) % 7 or 7
        # a bare weekday could mean either side of the week
        return _result((today + timedelta(days=ahead)).isoformat(), text, ambiguous=True)

    if lowered in ("end of week", "end of the week"):
        return _result((today + timedelta(days=(4 - today.weekday()) % 7)).isoformat(), text)
    if lowered in ("end of month", "end of the month"):
        first_next = date(today.year + today.month // 12, today.month % 12 + 1, 1)
        return _result((first_next - timedelta(days=1)).isoformat(), text)

    return None


# --- enum ---------------------------------------------------------------------


def make_enum(mapping: dict[str, str]) -> Callable[[Any], str | None]:
    """Case-folding synonym map. An unknown value is rejected, not passed through."""
    lookup = {k.lower(): v for k, v in mapping.items()}

    def normalize(raw: Any) -> str | None:
        if not isinstance(raw, str):
            return None
        text = raw.strip().lower().strip(".!,")
        if text in lookup:
            return lookup[text]
        # "email me", "by phone" — the synonym embedded in a short phrase
        for token in re.split(r"[\s/_-]+", text):
            if token in lookup:
                return lookup[token]
        return None

    return normalize


CONTACT_MODES = {
    "email": "email", "e-mail": "email", "emails": "email", "mail": "email",
    "gmail": "email", "email me": "email",
    "phone": "phone", "call": "phone", "calls": "phone", "voice": "phone",
    "ring": "phone", "telephone": "phone", "phone call": "phone",
    "sms": "sms", "text": "sms", "texts": "sms", "texting": "sms",
    "text message": "sms",
    "whatsapp": "whatsapp", "wa": "whatsapp", "whats app": "whatsapp",
}

THEMES = {"dark": "dark", "light": "light", "night": "dark", "day": "light"}

PAYMENT_METHODS = {
    "card": "card", "credit card": "card", "debit card": "card",
    "creditcard": "card", "visa": "card", "mastercard": "card",
    "upi": "upi", "gpay": "upi", "phonepe": "upi", "paytm": "upi",
    "google pay": "upi",
    "cash": "cash", "cod": "cash", "cash on delivery": "cash",
    "netbanking": "netbanking", "net banking": "netbanking", "bank": "netbanking",
    "wallet": "wallet", "paypal": "wallet",
}


# --- scalars ------------------------------------------------------------------


def normalize_string(raw: Any) -> str | None:
    """Trim, collapse whitespace, strip trailing punctuation."""
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        raw = str(raw)
    if not isinstance(raw, str):
        return None
    text = " ".join(raw.split()).strip(" .,;:!—–-")
    return text or None


def normalize_int(raw: Any) -> int | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return int(raw)
    if isinstance(raw, str) and (m := _NUMERIC.search(raw)):
        try:
            return int(float(m.group(1).replace(",", "")))
        except ValueError:
            return None
    return None


def normalize_bool(raw: Any) -> bool | None:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        lowered = raw.strip().lower()
        if lowered in ("true", "yes", "y", "1"):
            return True
        if lowered in ("false", "no", "n", "0"):
            return False
    return None


def normalize_list(raw: Any) -> list[Any] | None:
    """Sorted, de-duplicated, normalized strings — order must not affect a handle."""
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return None
    cleaned: list[str] = []
    for item in raw:
        value = normalize_string(item) if not isinstance(item, dict) else None
        if value and value not in cleaned:
            cleaned.append(value)
    return sorted(cleaned) or None


def normalize_color(raw: Any) -> str | None:
    """Hex is identity-bearing, so case is normalized; names are lowercased."""
    text = normalize_string(raw)
    if not text:
        return None
    if re.fullmatch(r"#[0-9A-Fa-f]{3,8}", text):
        return text.upper()
    return text.lower() if text.isalpha() else text


def normalize_name(raw: Any) -> str | None:
    """Title-case a person or place without mangling McName or O'Brien.

    A SHOUTED word is title-cased too: "MY NAME IS SANJANA" is the same person
    as "my name is Sanjana", and storing both spellings would make two states
    that mean one thing hash differently. Short all-caps runs are left alone so
    an initialism survives.
    """
    text = normalize_string(raw)
    if not text or any(ch.isdigit() for ch in text):
        return None
    words = []
    for word in text.split():
        if word.isupper() and len(word) > 3:
            words.append(word[:1] + word[1:].lower())
        elif word.islower():
            words.append(word[:1].upper() + word[1:])
        else:
            words.append(word)
    return " ".join(words)
