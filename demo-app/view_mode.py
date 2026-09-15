"""The single view-mode resolver and its mode-preserving URL helper.

Deliberately free of any web-framework import so the resolver is unit-testable
from plain arguments (a query value plus a user-agent string) as well as through
the application test client.

Precedence, once, here:

1. an explicit ``mode=tv`` query value wins over everything else (source
   ``query``);
2. otherwise a recognised TV user-agent hint yields TV mode (source
   ``user_agent``);
3. otherwise, including for an unrecognised ``mode`` value, the mode is mobile
   (source ``default``).
"""

from __future__ import annotations

from typing import Any, Mapping

MODE_TV = "tv"
MODE_MOBILE = "mobile"

SOURCE_QUERY = "query"
SOURCE_USER_AGENT = "user_agent"
SOURCE_DEFAULT = "default"

QUERY_KEY = "mode"

# The recognised TV user-agent hints, defined exactly once so tests and callers
# reference this constant instead of repeating user-agent strings. Matching is
# case-insensitive substring containment, which is all a hint needs to be.
TV_USER_AGENT_HINTS = (
    "SmartTV",
    "Smart-TV",
    "GoogleTV",
    "AndroidTV",
    "AppleTV",
    "HbbTV",
    "webOS",
    "Tizen",
    "BRAVIA",
    "Roku",
    "VIDAA",
    "CrKey",
)


def is_tv_user_agent(user_agent: Any) -> bool:
    """True when the user agent carries one of TV_USER_AGENT_HINTS.

    ``None``, a non-string and an empty string are all "not a TV".
    """
    if not isinstance(user_agent, str) or not user_agent.strip():
        return False
    folded = user_agent.casefold()
    return any(hint.casefold() in folded for hint in TV_USER_AGENT_HINTS)


def resolve_view_mode(query_mode: Any, user_agent: Any) -> dict:
    """Resolve the view mode for one request into a TYPE_VIEW_MODE mapping.

    The ``source`` field exists so precedence is assertable directly: an
    explicit ``mode=tv`` reports ``query``, a hint reports ``user_agent``, and an
    unrecognised value provably falls back to mobile with ``default`` rather than
    raising.
    """
    if isinstance(query_mode, str) and query_mode.strip().casefold() == MODE_TV:
        return {"mode": MODE_TV, "source": SOURCE_QUERY}
    if is_tv_user_agent(user_agent):
        return {"mode": MODE_TV, "source": SOURCE_USER_AGENT}
    return {"mode": MODE_MOBILE, "source": SOURCE_DEFAULT}


def is_tv(view_mode: Any) -> bool:
    """True when a resolved view mode (or a bare mode string) is TV mode."""
    if isinstance(view_mode, Mapping):
        return view_mode.get("mode") == MODE_TV
    return view_mode == MODE_TV


def mode_url(path: str, view_mode: Any = None) -> str:
    """``path`` with TV mode retained, or unchanged for mobile mode.

    One implementation for detail links, back links and the TV Enter target, so
    no template or script has to concatenate a query string itself.
    """
    if not is_tv(view_mode):
        return path
    marker = f"{QUERY_KEY}={MODE_TV}"
    if marker in path:
        return path
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}{marker}"
