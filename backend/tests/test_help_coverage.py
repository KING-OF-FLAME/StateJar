"""Every surface the product exposes must have a help entry.

Documentation that depends on someone remembering to update it drifts, and the
drift is invisible until a user hits it. So this test enumerates the real
surfaces from the code itself — registered routes, the settings model, the
provider registry, the tier names, the decline reasons, the value types — and
fails when one of them has no entry in the help centre.

Adding an entry is the cheap way to make it pass: one markdown file under
`frontend/src/content/help/` with the id named in the failure message. Skipping
is the expensive way: `ALLOWED_UNDOCUMENTED` demands a reason string, and the
reason is read by a human at review time.

The test also reads the guards' own source so the decline-reason list cannot
quietly fall behind: a new `reason="..."` literal in the extraction path fails
here until it is registered in `app.schema.declines` and documented.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from app.config import Settings
from app.llm.providers import KEYED_PROVIDERS
from app.main import app
from app.memory.extractor import SOURCE_GLINER, SOURCE_LLM, SOURCE_RULES
from app.schema import declines
from app.schema import valuetype as vt

HELP_DIR = (
    Path(__file__).resolve().parents[2] / "frontend" / "src" / "content" / "help"
)

# Routes that are infrastructure, not product surface: FastAPI's own docs and
# the schema they are generated from.
INTERNAL_PREFIXES = ("/docs", "/redoc", "/openapi.json")

# UI surfaces are not reflectable from Python, so they are listed. Adding a
# panel, tab or chip to the console means adding a line here — which is the
# point: the line is the reminder that a user has to be told what it does.
UI_SURFACES: tuple[tuple[str, str], ...] = (
    ("ui.sidebar", "the console sidebar and what each destination is for"),
    ("ui.dashboard", "Dashboard screen"),
    ("ui.playground", "Playground screen"),
    ("ui.api_keys", "API Keys screen"),
    ("ui.api_docs", "API Docs screen"),
    ("ui.audit_log", "Audit Log screen"),
    ("ui.about", "About page"),
    ("ui.help", "this help centre"),
    ("ui.session_selector", "session dropdown and + New session"),
    ("ui.model_selector", "model picker, including custom model ids"),
    ("ui.message_box", "the chat input"),
    ("ui.pipeline_tracker", "the seven-stage strip and its sublabels"),
    ("ui.tab_memory_state", "Memory State tab"),
    ("ui.tab_retrieved_context", "Retrieved Context tab"),
    ("ui.tab_handles", "Handles tab"),
    ("ui.tab_audit", "Audit tab"),
    ("ui.tier_chips", "the rules / GLiNER2 / LLM chips and the amber chip"),
    ("ui.declined_section", "the declined values list and its reasons"),
    ("ui.handle_display", "the handle line and its copy button"),
    ("ui.restore_handle", "the restore-a-handle control"),
    ("ui.token_savings", "the token savings badge and its baseline"),
    ("ui.instant_demo", "the scripted demo and the 17-turn relief demo"),
)

# Deliberate exclusions, keyed `<kind>:<id>`. Every item needs a reason a
# reviewer can disagree with — the point of the list is that skipping
# documentation is visible and argued for, not silent.
#
# Currently empty: every surface is documented. Keep it that way if you can;
# `test_exclusions_actually_exclude` proves the mechanism still works while the
# list is empty, so an entry added here in a hurry is not the first exercise it
# has had.
ALLOWED_UNDOCUMENTED: dict[str, str] = {}


# --------------------------------------------------------------------------
# reading the help index
# --------------------------------------------------------------------------

_FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)


def parse_entry(path: Path) -> dict[str, str]:
    """Frontmatter + body, in the same shape the frontend loader produces.

    Kept deliberately simple — a `key: value` scalar block. If the content ever
    needs nested frontmatter, both this and `frontend/src/lib/help.js` change
    together, and the entries below will say so loudly.
    """
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER.match(text)
    if not match:
        raise AssertionError(f"{path.name}: missing --- frontmatter --- block")
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise AssertionError(f"{path.name}: frontmatter line is not key: value → {line!r}")
        meta[key.strip()] = value.strip().strip('"')
    meta["body"] = text[match.end():]
    meta["file"] = path.name
    return meta


@pytest.fixture(scope="module")
def entries() -> dict[str, dict[str, str]]:
    assert HELP_DIR.is_dir(), f"help content directory missing: {HELP_DIR}"
    found: dict[str, dict[str, str]] = {}
    for path in sorted(HELP_DIR.glob("*.md")):
        entry = parse_entry(path)
        entry_id = entry.get("id", "")
        assert entry_id, f"{path.name}: frontmatter has no id"
        assert entry_id not in found, (
            f"duplicate help id {entry_id!r} in {path.name} and "
            f"{found[entry_id]['file']}"
        )
        found[entry_id] = entry
    assert found, f"no help entries found in {HELP_DIR}"
    return found


# --------------------------------------------------------------------------
# enumerating the product's real surfaces
# --------------------------------------------------------------------------

def endpoint_id(path: str) -> str:
    """`/api/v1/memory/state/{handle}` -> `api.memory.state`.

    Path parameters are dropped, so the routes that differ only by a parameter
    describe one resource and share one entry — `GET /apikeys` and
    `DELETE /apikeys/{key_id}` are the same thing to explain.
    """
    trimmed = path.removeprefix("/api/v1").strip("/")
    segments = [s for s in trimmed.split("/") if s and not s.startswith("{")]
    return ".".join(["api", *segments])


def registered_endpoints() -> dict[str, str]:
    """id -> a readable `METHOD /path` label, for the failure message.

    Only routes whose handler is defined inside the `app` package count.
    `tests/test_auth.py` and `tests/test_security.py` hang fixture endpoints
    (`/auth/me`, `/auth/whoami`) off the shared router at import time, so a
    full-suite run would otherwise demand documentation for two things no user
    can call. Filtering on the handler's module rather than listing those two
    paths keeps the next such fixture from failing the build either.
    """
    out: dict[str, str] = {}
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = (getattr(route, "methods", None) or set()) - {"HEAD", "OPTIONS"}
        if not methods or path.startswith(INTERNAL_PREFIXES):
            continue
        origin = getattr(getattr(route, "endpoint", None), "__module__", "")
        if not origin.startswith("app."):
            continue
        label = f"{'/'.join(sorted(methods))} {path}"
        out.setdefault(endpoint_id(path), label)
    return out


def declared_reasons() -> set[str]:
    return set(declines.REASONS)


GUARD_SOURCES = (
    "app/memory/extractor.py",
    "app/memory/rules.py",
    "app/schema/canonical.py",
    "app/schema/dynamic.py",
)


def _static_prefix(node: ast.JoinedStr) -> str:
    """The literal head of an f-string: f"user rejected {x}…" -> "user rejected"."""
    first = node.values[0] if node.values else None
    return first.value.strip() if isinstance(first, ast.Constant) else ""


def emitted_reasons() -> set[str]:
    """Reason strings the extraction path can actually produce.

    Read from the source rather than trusted from a list, so a reason added in
    a guard is caught here instead of reaching a user undocumented. Three
    shapes appear in the code and all three are collected: `reason = "..."`,
    `reason="..."` / `"reason": "..."`, and the `for pattern, reason in ((...))`
    table in `rules.find_unresolved`.
    """
    root = Path(__file__).resolve().parents[1]
    found: set[str] = set()

    def record(node: ast.AST) -> None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.add(node.value)
        elif isinstance(node, ast.JoinedStr):
            prefix = _static_prefix(node)
            if prefix:
                found.add(prefix)

    for rel in GUARD_SOURCES:
        tree = ast.parse((root / rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                if any(isinstance(t, ast.Name) and t.id == "reason" for t in node.targets):
                    record(node.value)
            elif isinstance(node, ast.keyword) and node.arg == "reason":
                record(node.value)
            elif isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if isinstance(key, ast.Constant) and key.value == "reason":
                        record(value)
            elif isinstance(node, ast.For) and isinstance(node.target, ast.Tuple):
                slots = [
                    i for i, el in enumerate(node.target.elts)
                    if isinstance(el, ast.Name) and el.id == "reason"
                ]
                if not slots or not isinstance(node.iter, (ast.Tuple, ast.List)):
                    continue
                for row in node.iter.elts:
                    if isinstance(row, (ast.Tuple, ast.List)):
                        for i in slots:
                            if i < len(row.elts):
                                record(row.elts[i])
    # `routed.reason or "rejected_value"` and friends resolve at runtime; the
    # literal on either side of the `or` is collected above, so the runtime
    # value is always one this scan has already seen.
    return {r for r in found if r}


def value_types() -> set[str]:
    return {
        vt.MONEY, vt.QUANTITY, vt.DURATION, vt.DATE, vt.PERCENT,
        vt.RATIO, vt.IDENTIFIER, vt.COUNT, vt.TEXT, vt.UNKNOWN,
    }


def required_ids() -> list[tuple[str, str, str]]:
    """(kind, id, label) for every surface that must be documented."""
    required: list[tuple[str, str, str]] = []
    for entry_id, label in sorted(registered_endpoints().items()):
        required.append(("endpoint", entry_id, label))
    for name in Settings.model_fields:
        required.append(("setting", f"settings.{name}", name.upper()))
    for name in KEYED_PROVIDERS:
        required.append(("provider", f"provider.{name}", name))
    for name in (SOURCE_RULES, SOURCE_GLINER, SOURCE_LLM):
        required.append(("tier", f"tier.{name}", name))
    for reason in sorted(declared_reasons()):
        required.append(("decline", declines.help_id(reason), reason))
    for name in sorted(value_types()):
        required.append(("valuetype", f"valuetype.{name}", name))
    for entry_id, label in UI_SURFACES:
        required.append(("ui", entry_id, label))
    return required


# --------------------------------------------------------------------------
# the tests
# --------------------------------------------------------------------------

def undocumented(
    documented: set[str], allowed: dict[str, str] | None = None,
) -> list[tuple[str, str, str]]:
    """Surfaces with no entry and no written excuse. Split out so the
    exclusion mechanism can be tested while the exclusion list is empty."""
    allowed = ALLOWED_UNDOCUMENTED if allowed is None else allowed
    return [
        (kind, entry_id, label)
        for kind, entry_id, label in required_ids()
        if entry_id not in documented and f"{kind}:{entry_id}" not in allowed
    ]


def report(missing: list[tuple[str, str, str]]) -> str:
    width = max(len(label) for _, _, label in missing)
    lines = "\n".join(
        f"  {kind:<10} {label:<{width}}  -> add help entry id: {entry_id}"
        for kind, entry_id, label in missing
    )
    return (
        f"Undocumented surfaces ({len(missing)}):\n{lines}\n\n"
        f"Add one markdown file per id under {HELP_DIR}, or list it in "
        "ALLOWED_UNDOCUMENTED with a reason."
    )


def test_every_surface_has_a_help_entry(entries: dict[str, dict[str, str]]) -> None:
    missing = undocumented(set(entries))
    if missing:
        raise AssertionError(report(missing))


def test_exclusions_actually_exclude(entries: dict[str, dict[str, str]]) -> None:
    """Pretend one documented surface lost its entry, and check both halves:
    without an excuse it is reported, with one it is not."""
    kind, victim, _ = required_ids()[0]
    thinned = set(entries) - {victim}

    reported = undocumented(thinned, allowed={})
    assert any(e == victim for _, e, _ in reported), (
        f"removing {victim} should have been reported and was not"
    )
    assert victim in report(reported)

    excused = undocumented(thinned, allowed={f"{kind}:{victim}": "test fixture"})
    assert all(e != victim for _, e, _ in excused), (
        f"{victim} was excused and should not have been reported"
    )


def test_every_decline_reason_the_guards_emit_is_registered() -> None:
    """The declared reason list cannot fall behind the guards that emit them."""
    declared = declared_reasons()
    unregistered = sorted(
        r for r in emitted_reasons()
        if r not in declared and not any(r.startswith(t) for t in declines.TEMPLATES)
    )
    assert not unregistered, (
        "Reason strings emitted by the extraction path but not registered in "
        f"app/schema/declines.py: {unregistered}\n"
        "Register each one, then add its help entry (decline.<slug>)."
    )


def test_registered_reasons_are_actually_emitted() -> None:
    """The other direction: a reason nobody emits is documentation debt."""
    emitted = emitted_reasons()
    stale = sorted(r for r in declared_reasons() if r not in emitted)
    assert not stale, (
        f"Registered in declines.REASONS but no guard emits them: {stale}. "
        "Remove them, or fix the source scan if the shape changed."
    )


def test_allowed_undocumented_entries_have_reasons() -> None:
    for key, reason in ALLOWED_UNDOCUMENTED.items():
        assert ":" in key, f"{key!r} must be '<kind>:<id>'"
        assert len(reason.split()) >= 5, (
            f"{key}: give a real reason, not {reason!r} — this list is read at "
            "review time and a one-word excuse defeats the purpose"
        )


def test_allowed_undocumented_has_no_stale_entries(
    entries: dict[str, dict[str, str]],
) -> None:
    """An exclusion for something that is documented, or gone, is noise."""
    live = {f"{kind}:{entry_id}" for kind, entry_id, _ in required_ids()}
    for key in ALLOWED_UNDOCUMENTED:
        assert key in live, f"{key} is in ALLOWED_UNDOCUMENTED but is no longer a surface"
        assert key.split(":", 1)[1] not in entries, (
            f"{key} is excused but also documented — drop the exclusion"
        )


def test_entries_are_well_formed(entries: dict[str, dict[str, str]]) -> None:
    date = re.compile(r"\A\d{4}-\d{2}-\d{2}\Z")
    for entry_id, entry in entries.items():
        for field in ("title", "category", "updated_at"):
            assert entry.get(field), f"{entry_id}: frontmatter is missing {field}"
        assert date.match(entry["updated_at"]), (
            f"{entry_id}: updated_at must be YYYY-MM-DD, got {entry['updated_at']!r}"
        )
        assert len(entry["body"].split()) >= 20, (
            f"{entry_id}: body is too short to answer anything ("
            f"{len(entry['body'].split())} words)"
        )


def test_every_entry_is_in_a_known_category(entries: dict[str, dict[str, str]]) -> None:
    known = {
        "getting-started", "concepts", "interface", "providers", "api",
        "settings", "demo", "troubleshooting", "faq", "reference",
    }
    for entry_id, entry in entries.items():
        assert entry["category"] in known, (
            f"{entry_id}: unknown category {entry['category']!r}; "
            f"expected one of {sorted(known)}"
        )
