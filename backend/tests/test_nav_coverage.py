"""Every authenticated route must be reachable by clicking.

`/profile` shipped working and unreachable: the page rendered, the API served
it, the route was registered, and nothing in the console shell linked to it. The
only way in was the marketing header's account menu, so reaching your own
profile meant leaving the console. Every test passed, because no test asked the
question a user asks first — how do I get there?

This asks it. Routes come from `main.jsx`, links from the shells that render for
a signed-in user, and a route in the first set with no link in the second fails
the build.

Parsed rather than executed because the repo has no JS test runner; adding one
for a single assertion would be a heavier dependency than the assertion is
worth. The parsing is deliberately blunt and will over-collect rather than
under-collect: a false "this is linked" is the failure mode that lets the bug
back in, so anything that looks like a link counts, and the test errors out if a
file it depends on stops matching the shape it expects.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"
ROUTER = FRONTEND / "main.jsx"

# Shells rendered for a signed-in user. A link from any of these is a way in.
# Landing is here because it renders the account menu when authenticated, and a
# link from the marketing header is a real (if roundabout) route.
LINK_SOURCES = (
    FRONTEND / "components" / "Layout.jsx",
    FRONTEND / "components" / "AccountMenu.jsx",
    FRONTEND / "pages" / "Landing.jsx",
    FRONTEND / "pages" / "Dashboard.jsx",
)

# Routes that are deliberately not linked, each with a reason.
UNLINKED_BY_DESIGN: dict[str, str] = {
    "/login": "reached by signing out or by an expired session, not by a link",
    "/signup": "linked from the public header only, which is correct — a signed-in "
               "user has no reason to see it",
}

_ROUTE = re.compile(r'<Route\s+path="(/[^"]*)"')
# Four shapes count as a way in, and all four are in use:
#   to="/x" / href="/x"   JSX attribute, used by NavLink and <a>
#   to: '/x'              object literal, which is how the sidebar NAV list is
#                         written — missing this shape made the first run of
#                         this test report /audit as unreachable when it is the
#                         fifth item in the sidebar
#   navigate('/x')        imperative, including the ternary form
#                         navigate(cond ? '/a' : '/b')
_LINK = re.compile(
    r"""(?:to|href)=["'](/[^"'?#]*)"""
    r"""|(?:to|href)\s*:\s*['"](/[^'"?#]*)"""
    r"""|navigate\(\s*[^)]*?['"`](/[^'"`?#]*)"""
)


def declared_routes() -> set[str]:
    text = ROUTER.read_text(encoding="utf-8")
    routes = {m.group(1) for m in _ROUTE.finditer(text)}
    assert routes, f"no <Route path=...> found in {ROUTER} — did the router change shape?"
    return routes


def linked_paths() -> set[str]:
    found: set[str] = set()
    for path in LINK_SOURCES:
        assert path.is_file(), f"link source missing: {path}"
        text = path.read_text(encoding="utf-8")
        for m in _LINK.finditer(text):
            found.add(m.group(1) or m.group(2) or m.group(3))
    assert found, "no links found in any shell — did the parser stop matching?"
    return found


@pytest.fixture(scope="module")
def routes() -> set[str]:
    return declared_routes()


def test_every_authenticated_route_is_linked(routes: set[str]) -> None:
    links = linked_paths()
    missing = sorted(
        r for r in routes
        if r not in links and r not in UNLINKED_BY_DESIGN and r != "/"
    )
    assert not missing, (
        "Routes a signed-in user cannot click their way to:\n"
        + "\n".join(f"  {r}  -> add it to the sidebar in Layout.jsx" for r in missing)
        + "\n\nIf it is deliberately unlinked, add it to UNLINKED_BY_DESIGN "
          "with a reason."
    )


def test_profile_is_in_the_console_sidebar() -> None:
    """The specific regression. The account menu is not enough: it renders on
    the marketing header, so relying on it means leaving the console to reach
    your own profile."""
    nav = re.search(
        r"const NAV = \[(.*?)\n\]",
        (FRONTEND / "components" / "Layout.jsx").read_text(encoding="utf-8"),
        re.DOTALL,
    )
    assert nav, "NAV list not found in Layout.jsx"
    assert "'/profile'" in nav.group(1), (
        "/profile is missing from the console sidebar NAV — it would be "
        "reachable only from the marketing header again"
    )


def test_unlinked_exceptions_are_real_routes(routes: set[str]) -> None:
    """An exception for a route that no longer exists is noise."""
    for path, reason in UNLINKED_BY_DESIGN.items():
        assert path in routes, f"{path} is excused but is not a declared route"
        assert len(reason.split()) >= 5, f"{path}: give a real reason, not {reason!r}"


def test_every_sidebar_link_goes_somewhere(routes: set[str]) -> None:
    """The other direction: a sidebar entry pointing at nothing is a dead link."""
    nav = re.search(
        r"const NAV = \[(.*?)\n\]",
        (FRONTEND / "components" / "Layout.jsx").read_text(encoding="utf-8"),
        re.DOTALL,
    )
    assert nav
    for target in re.findall(r"to:\s*'(/[^']*)'", nav.group(1)):
        assert target in routes, f"sidebar links {target}, which is not a route"
