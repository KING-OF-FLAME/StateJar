"""The canonical schema registry — the single gate into state.

Before this module, extractors wrote their own key names straight into state.
Nothing stopped two names for one concept coexisting, so `budget_inr` and
`budget_inr_max` both persisted and an update patched only one of them: state
carried a stale value and shipped it to the model. That is not a tuning
problem, it is a missing layer.

So: **no extractor writes to state directly.** Every write resolves through
`canonicalize()`, which maps an alias to exactly one canonical path and runs
the field's normalizer. A key that resolves to nothing goes to the `_unmapped`
quarantine — never into active state — where it stays queryable as the
feedback loop for extending this registry.

Because aliases collapse *before* the write, two names for one concept can no
longer coexist by construction; `assert_no_duplicate_paths()` at the STORE
boundary is the backstop that proves it.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any, Callable, Iterable

from app.schema import normalizers as norm

# merge policies
REPLACE = "replace"          # latest wins (scalars)
APPEND_UNIQUE = "append_unique"  # ordered set (lists)
UNION = "union"              # set semantics, sorted

# sensitivity
PUBLIC = "public"
PII = "pii"
SECRET = "secret"

# confidence floors by tier — a rule match is a deterministic assertion, a
# model score is not
CONFIDENCE = {"rule": 1.0, "rules": 1.0, "gliner": 0.55, "gliner2": 0.55, "llm": 0.5}


@dataclass(frozen=True)
class FieldSpec:
    path: str
    type: str
    aliases: tuple[str, ...]
    normalizer: Callable[[Any], Any]
    merge_policy: str = REPLACE
    sensitivity: str = PUBLIC
    required_confidence: float = 0.0
    description: str = ""
    enum_values: tuple[str, ...] = dc_field(default=())
    # what a zero-shot NER model should be asked for; blank derives it from the
    # leaf, which is right for "city" and wrong for "primary"
    label: str = ""

    @property
    def entity_label(self) -> str:
        return self.label or self.leaf.replace("_", " ")

    @property
    def section(self) -> str:
        return self.path.split(".", 1)[0]

    @property
    def leaf(self) -> str:
        return self.path.rsplit(".", 1)[-1]


_D = norm.normalize_date
_S = norm.normalize_string
_L = norm.normalize_list


REGISTRY: tuple[FieldSpec, ...] = (
    # --- identity ---
    FieldSpec(
        path="facts.name", type="string", normalizer=norm.normalize_name,
        aliases=("name", "full_name", "user_name", "username", "person",
                 "my_name", "caller_name", "first_name"),
        sensitivity=PII, required_confidence=0.6,
        description="The person StateJar is remembering for.",
        label="person name",
    ),
    FieldSpec(
        path="facts.city", type="string", normalizer=norm.normalize_name,
        aliases=("city", "location", "town", "place", "based_in", "from_city",
                 "current_city", "residence"),
        required_confidence=0.5, description="Where the user is.",
        label="city",
    ),
    FieldSpec(
        path="facts.email", type="string", normalizer=_S,
        aliases=("email", "email_address", "mail_id", "e_mail"),
        sensitivity=PII, required_confidence=0.6,
        label="email address",
    ),
    FieldSpec(
        path="facts.phone", type="string", normalizer=_S,
        aliases=("phone", "phone_number", "mobile", "contact_number", "number"),
        sensitivity=PII, required_confidence=0.6,
        label="phone number",
    ),
    FieldSpec(
        path="facts.organization", type="string", normalizer=_S,
        aliases=("organization", "organisation", "company", "employer", "org",
                 "workplace", "brand"),
        label="organization",
    ),
    FieldSpec(
        path="facts.audience", type="string", normalizer=_S,
        aliases=("audience", "target_audience", "target_users", "users_for",
                 "customer_segment"),
        label="target audience",
    ),
    FieldSpec(
        path="facts.role", type="string", normalizer=_S,
        aliases=("role", "job_title", "designation", "occupation", "profession"),
        label="job role",
    ),

    # --- preferences ---
    FieldSpec(
        path="preferences.contact_mode", type="enum",
        normalizer=norm.make_enum(norm.CONTACT_MODES),
        aliases=("contact_mode", "contact", "preferred_contact", "contact_method",
                 "reach_me", "contact_preference", "communication_mode",
                 "preferred_channel", "channel"),
        required_confidence=0.5,
        enum_values=("email", "phone", "sms", "whatsapp"),
        description="How the user wants to be reached.",
        label="contact preference",
    ),
    FieldSpec(
        path="preferences.theme", type="enum",
        normalizer=norm.make_enum(norm.THEMES),
        aliases=("theme", "colour_scheme", "color_scheme", "appearance", "mode"),
        enum_values=("dark", "light"),
        label="visual theme",
    ),
    FieldSpec(
        path="preferences.brand_color", type="string", normalizer=norm.normalize_color,
        aliases=("brand_color", "brand_colour", "accent_color", "accent_colour",
                 "primary_color", "primary_colour", "colour", "color"),
        label="brand colour",
    ),
    FieldSpec(
        path="preferences.language", type="string", normalizer=_S,
        aliases=("language", "preferred_language", "locale", "lang"),
        label="language",
    ),

    # --- constraints ---
    FieldSpec(
        path="constraints.budget.max", type="money", normalizer=norm.normalize_money,
        aliases=("budget", "budget_inr", "budget_inr_max", "max_budget",
                 "price_limit", "budget_max", "budget_limit", "spend_limit",
                 "max_price", "price_cap", "budget_ceiling", "cost_limit",
                 "budget_usd", "budget_amount"),
        required_confidence=0.6,
        description="Most the user will spend. One path, many spellings.",
        label="budget amount",
    ),
    FieldSpec(
        path="constraints.deadline", type="date", normalizer=_D,
        aliases=("deadline", "due_date", "need_by", "before_date", "by_date",
                 "delivery_deadline", "target_date", "due", "needed_by",
                 "delivery_date", "date"),
        required_confidence=0.6,
        description="When it has to be done. Stored ISO-8601.",
        label="deadline date",
    ),
    FieldSpec(
        path="constraints.additional_dates", type="list",
        normalizer=lambda raw: _dates_list(raw),
        aliases=("additional_dates", "other_dates", "secondary_dates"),
        merge_policy=UNION,
        label="other date",
    ),
    FieldSpec(
        path="constraints.requirements", type="list", normalizer=_L,
        aliases=("requirements", "must_have", "requirement", "needs",
                 "required_features", "constraints_list"),
        merge_policy=APPEND_UNIQUE,
        label="requirement",
    ),
    FieldSpec(
        path="constraints.no_ui_libs", type="string", normalizer=_S,
        aliases=("no_ui_libs", "ui_library_ban", "excluded_libraries",
                 "no_ui_libraries"),
        label="excluded library",
    ),
    FieldSpec(
        path="constraints.quantity", type="int", normalizer=norm.normalize_int,
        aliases=("quantity", "qty", "count", "headcount", "seats", "guests",
                 "passengers", "people"),
        label="quantity",
    ),

    # --- decisions ---
    FieldSpec(
        path="decisions.stack", type="string", normalizer=_S,
        aliases=("stack", "tech_stack", "technology", "framework", "platform"),
        label="technology stack",
    ),
    FieldSpec(
        path="decisions.choice", type="string", normalizer=_S,
        aliases=("choice", "decision", "selected", "chosen", "picked", "item"),
        label="decision",
    ),

    # --- goals ---
    FieldSpec(
        path="goals.primary", type="string", normalizer=_S,
        aliases=("primary", "goal", "primary_goal", "objective", "aim",
                 "intent", "purpose", "task"),
        label="goal",
    ),

    # --- cross-domain ---
    #
    # StateJar is not a web-dev tool, but the schema had drifted into being
    # one: outside name/city/budget/deadline/contact, an arbitrary message
    # extracted nothing. These are the fields real messages actually carry
    # across e-commerce, travel, health intake, hiring, food and property.
    # Registering a field is what makes the generic `<key> is <value>` rule
    # able to fill it, so breadth here is breadth everywhere.
    FieldSpec(
        path="facts.age", type="int", normalizer=norm.normalize_int,
        aliases=("age", "years_old", "my_age"),
        sensitivity=PII, label="age",
    ),
    FieldSpec(
        path="facts.address", type="string", normalizer=_S,
        aliases=("address", "delivery_address", "shipping_address", "street",
                 "postal_address", "pincode", "zip", "zipcode", "postcode"),
        sensitivity=PII, label="address",
    ),
    FieldSpec(
        path="facts.experience_years", type="int", normalizer=norm.normalize_int,
        aliases=("experience", "experience_years", "years_experience", "yoe",
                 "work_experience"),
        label="years of experience",
    ),
    FieldSpec(
        path="facts.skills", type="list", normalizer=_L,
        aliases=("skills", "skill", "expertise", "technologies_known"),
        merge_policy=UNION, label="skill",
    ),
    FieldSpec(
        path="constraints.origin", type="string", normalizer=norm.normalize_name,
        aliases=("origin", "from_location", "departure", "departing_from",
                 "source_city", "pickup", "pickup_location"),
        label="origin location",
    ),
    FieldSpec(
        path="constraints.destination", type="string", normalizer=norm.normalize_name,
        aliases=("destination", "to_location", "arrival", "going_to", "drop",
                 "drop_location", "destination_city"),
        label="destination location",
    ),
    FieldSpec(
        path="constraints.dietary", type="list", normalizer=_L,
        aliases=("dietary", "diet", "dietary_restrictions", "food_preference",
                 "cuisine", "veg_preference"),
        merge_policy=UNION, label="dietary preference",
    ),
    FieldSpec(
        path="constraints.allergies", type="list", normalizer=_L,
        aliases=("allergies", "allergy", "allergic_to"),
        merge_policy=UNION, sensitivity=PII, label="allergy",
    ),
    FieldSpec(
        path="constraints.bedrooms", type="int", normalizer=norm.normalize_int,
        aliases=("bedrooms", "bhk", "rooms", "bedroom_count"),
        label="bedroom count",
    ),
    FieldSpec(
        path="constraints.area", type="string", normalizer=_S,
        aliases=("area", "locality", "neighbourhood", "neighborhood",
                 "square_feet", "sqft", "carpet_area"),
        label="area or locality",
    ),
    FieldSpec(
        path="facts.symptoms", type="list", normalizer=_L,
        aliases=("symptoms", "symptom", "complaint", "condition"),
        merge_policy=UNION, sensitivity=PII, label="symptom",
    ),
    FieldSpec(
        path="facts.medications", type="list", normalizer=_L,
        aliases=("medications", "medication", "medicines", "prescriptions",
                 "currently_taking"),
        merge_policy=UNION, sensitivity=PII, label="medication",
    ),
    FieldSpec(
        path="decisions.plan", type="string", normalizer=_S,
        aliases=("plan", "tier", "subscription", "package", "membership"),
        label="plan or tier",
    ),
    FieldSpec(
        path="preferences.time_slot", type="string", normalizer=_S,
        aliases=("time_slot", "timeslot", "preferred_time", "slot", "timing",
                 "appointment_time", "delivery_slot"),
        label="preferred time",
    ),
    FieldSpec(
        path="preferences.payment_method", type="enum",
        normalizer=norm.make_enum(norm.PAYMENT_METHODS),
        aliases=("payment_method", "payment", "pay_by", "payment_mode"),
        enum_values=("card", "upi", "cash", "netbanking", "wallet"),
        label="payment method",
    ),
)


def _dates_list(raw: Any) -> list[str] | None:
    """A list of dates normalizes each element, dropping the ones that fail."""
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return None
    out: list[str] = []
    for item in raw:
        if isinstance(item, dict) and item.get("iso"):
            value = item["iso"]
        else:
            parsed = _D(item)
            value = parsed["iso"] if parsed else None
        if value and value not in out:
            out.append(value)
    return sorted(out) or None


# --- indices ------------------------------------------------------------------

BY_PATH: dict[str, FieldSpec] = {spec.path: spec for spec in REGISTRY}

_BY_ALIAS: dict[str, FieldSpec] = {}
for _spec in REGISTRY:
    for _alias in (_spec.path, _spec.leaf, *_spec.aliases):
        _key = _alias.lower()
        # a leaf like "choice" must not silently shadow another section's; the
        # first registration wins and collisions are a registry bug, not runtime
        _BY_ALIAS.setdefault(_key, _spec)
        _BY_ALIAS.setdefault(f"{_spec.section}.{_alias}".lower(), _spec)


QUARANTINE = "_unmapped"


class UnmappedKey(Exception):
    """A key that resolves to no canonical path."""


def resolve(raw_key: str) -> FieldSpec | None:
    """Alias (bare or dotted) -> its FieldSpec, or None."""
    if not raw_key:
        return None
    key = raw_key.strip().lower().replace("-", "_").replace(" ", "_")
    if spec := _BY_ALIAS.get(key):
        return spec
    if "." in key:  # "constraints.budget_inr_max" -> try the leaf alone
        return _BY_ALIAS.get(key.rsplit(".", 1)[-1])
    return None


def canonicalize(
    raw_key: str, raw_value: Any, *, confidence: float = 1.0, source: str = "rules",
    now: Any = None,
) -> tuple[str, Any] | None:
    """Alias + raw value -> (canonical_path, canonical_value), or None.

    None means "do not write this" and the caller is expected to quarantine it.
    Three separate reasons produce None — unknown alias, value the normalizer
    rejects, confidence below the field's floor — and all three are failures
    of the same kind: we do not know enough to assert a fact.
    """
    spec = resolve(raw_key)
    if spec is None:
        return None
    floor = max(spec.required_confidence, 0.0)
    if confidence < floor:
        return None
    try:
        if spec.type == "date":
            value = spec.normalizer(raw_value, now=now) if now else spec.normalizer(raw_value)
        else:
            value = spec.normalizer(raw_value)
    except (TypeError, ValueError):
        return None
    if value in (None, "", [], {}):
        return None
    return spec.path, value


def gliner_labels() -> list[str]:
    """Labels for tier 2, generated from this registry rather than hardcoded.

    Tier 2 asking for entity types the registry cannot store is wasted work,
    and a registry entry no tier ever fills is dead schema. Deriving one from
    the other keeps them honest.
    """
    seen: list[str] = []
    for spec in REGISTRY:
        label = spec.leaf.replace("_", " ")
        if label not in seen:
            seen.append(label)
    return seen


# --- writing ------------------------------------------------------------------


def write_path(state: dict[str, Any], path: str, value: Any) -> None:
    """Set a dotted canonical path, creating intermediate dicts."""
    parts = path.split(".")
    cursor = state
    for part in parts[:-1]:
        nxt = cursor.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cursor[part] = nxt
        cursor = nxt
    cursor[parts[-1]] = value


def read_path(state: dict[str, Any], path: str) -> Any:
    cursor: Any = state
    for part in path.split("."):
        if not isinstance(cursor, dict) or part not in cursor:
            return None
        cursor = cursor[part]
    return cursor


def quarantine(state: dict[str, Any], raw_key: str, raw_value: Any, reason: str) -> None:
    """Park an unresolvable write where it can be reviewed, not in active state."""
    bucket = state.setdefault(QUARANTINE, {})
    if not isinstance(bucket, dict):
        return
    bucket[raw_key] = {"value": raw_value, "reason": reason}


# --- the STORE-boundary invariant ---------------------------------------------

# sections whose contents are canonical fields; the rest are audit artifacts
ACTIVE_SECTIONS = ("facts", "preferences", "decisions", "constraints", "goals")

# leaves that belong to a canonical path rather than being one themselves
_STRUCTURED_LEAVES = {"value", "currency", "iso", "raw", "ambiguous", "year_inferred"}


def leaf_paths_in(block: Any, section: str) -> Iterable[str]:
    """Every value-bearing path inside one section, dotted and prefixed.

    A dict is only descended into when it is a container. A normalized money
    or date value is *itself* the leaf — descending would report
    `constraints.budget.max.value` as a field of its own.
    """
    if not isinstance(block, dict):
        return
    stack: list[tuple[str, Any]] = [(f"{section}.{k}", v) for k, v in block.items()]
    while stack:
        path, value = stack.pop()
        if isinstance(value, dict) and value and not (_STRUCTURED_LEAVES & set(value)):
            stack.extend((f"{path}.{k}", v) for k, v in value.items())
        else:
            yield path


def _leaf_paths(state: dict[str, Any]) -> Iterable[str]:
    """Every value-bearing path in the active sections."""
    for section in ACTIVE_SECTIONS:
        yield from leaf_paths_in(state.get(section), section)


class DuplicatePathError(AssertionError):
    """Two live values for one canonical concept — the bug this layer exists to stop."""


def assert_no_duplicate_paths(state: dict[str, Any]) -> None:
    """Fail loudly if two keys in active state mean the same thing.

    Called at the STORE boundary. If this ever fires, a write bypassed
    `canonicalize()` — which is exactly the condition that produced a stale
    budget being sent to the model.
    """
    seen: dict[str, str] = {}
    for path in _leaf_paths(state):
        spec = resolve(path)
        canonical = spec.path if spec else path
        if canonical in seen and seen[canonical] != path:
            raise DuplicatePathError(
                f"active state holds two values for {canonical!r}: "
                f"{seen[canonical]!r} and {path!r}"
            )
        seen[canonical] = path


__all__ = [
    "FieldSpec", "REGISTRY", "BY_PATH", "CONFIDENCE", "QUARANTINE",
    "REPLACE", "APPEND_UNIQUE", "UNION", "PUBLIC", "PII", "SECRET",
    "ACTIVE_SECTIONS", "DuplicatePathError",
    "resolve", "canonicalize", "gliner_labels", "write_path", "read_path",
    "quarantine", "assert_no_duplicate_paths", "leaf_paths_in",
]
