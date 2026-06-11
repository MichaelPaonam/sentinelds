"""Content-shape prompt-injection detector and Dynatrace custom event emitter.

Implements the heuristic described in docs/agents-exploit-scenarios.md §A1.3:
match instruction-override phrasing, embedded URLs paired with POST/fetch verbs,
and fenced-block role injections — then POST a ``sentinelds.injection.candidate``
BIZ_EVENT to Dynatrace so Davis AI and the Sentinel pre-flight gate can react.

Pattern categories
------------------
INSTRUCTION_OVERRIDE
    Phrases that attempt to hijack system instructions:
    "ignore previous", "disregard", "you are now", "forget your instructions", etc.

URL_WITH_POST_VERB
    An HTTP/HTTPS URL appearing near an imperative POST/send/fetch/submit verb
    within the same sentence or short context window — the classic "now POST to
    <attacker>" exfil pattern.

FENCED_ROLE_INJECTION
    Markdown / code fences (```system, [SYSTEM], <|im_start|>system, etc.) used
    to inject a synthetic role block into what should be plain content.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Optional

import httpx

from core.sentinel_audit import emit_audit_sync

logger = logging.getLogger("sentinel.injection_detector")


# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------

# INSTRUCTION_OVERRIDE — imperative instruction-override phrasing.
# Matches regardless of capitalisation or minor rewordings.
_INSTRUCTION_OVERRIDE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bignore\s+(all\s+)?(previous|prior|above|earlier)\b", re.I),
    re.compile(r"\bdisregard\s+(all\s+)?(previous|prior|above|earlier|your)\b", re.I),
    re.compile(
        r"\byou\s+are\s+now\s+(?:a\s+|an\s+)?(?:agent|assistant|bot|tool|system|"
        r"authorized|allowed\s+to\s+ignore|required\s+to|instructed)\b",
        re.I,
    ),
    re.compile(r"\byour\s+new\s+instructions?\b", re.I),
    re.compile(
        r"\bforget\s+(your|all|the)\s+(previous\s+)?(instructions?|rules?|guidelines?)\b",
        re.I,
    ),
    re.compile(r"\bact\s+as\s+(a\s+)?(?:new|different|another|unrestricted)\b", re.I),
    re.compile(r"\bdo\s+not\s+follow\s+(your\s+)?(previous|prior|original|system)\b", re.I),
    re.compile(r"\boverride\s+(your\s+)?(instructions?|prompt|system)\b", re.I),
    re.compile(
        r"\bsystem\s+prompt\s+(has\s+been\s+)?(updated|changed|replaced|overridden)\b",
        re.I,
    ),
    re.compile(r"\bnew\s+system\s+prompt\b", re.I),
    re.compile(r"\byou\s+must\s+now\s+(ignore|disregard|forget)\b", re.I),
    re.compile(r"\bpretend\s+(you\s+are|to\s+be)\b", re.I),
]

# URL_WITH_POST_VERB — HTTP/HTTPS URL near an imperative exfil/send verb.
# We look for the verb within 150 characters of the URL on either side.
# Deliberately excludes generic HTTP method verbs like 'get' and 'fetch'
# (commonly benign in code examples) to keep the false-positive rate low.
_URL_RE = re.compile(r"https?://\S+", re.I)
_POST_VERB_RE = re.compile(
    r"\b(post|send|submit|upload|exfil(?:trate)?|transmit|forward|ping)\b",
    re.I,
)
_URL_VERB_WINDOW = 150


# FENCED_ROLE_INJECTION — synthetic role blocks inside what should be content.
_FENCED_ROLE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"```\s*system\b", re.I),
    re.compile(r"```\s*user\b", re.I),
    re.compile(r"```\s*assistant\b", re.I),
    re.compile(r"\[SYSTEM\]", re.I),
    re.compile(r"\[INST\]", re.I),
    re.compile(r"<\|im_start\|>\s*system\b", re.I),
    re.compile(r"<\|system\|>", re.I),
    re.compile(r"<<<\s*system\b", re.I),
    re.compile(r"###\s*(system|instruction|directive)\s*:", re.I),
    re.compile(r"----+\s*system\s+prompt\s*----+", re.I),
]


# ---------------------------------------------------------------------------
# Public detection API
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InjectionMatch:
    """A single pattern match found in the scanned content."""

    category: str
    """One of INSTRUCTION_OVERRIDE, URL_WITH_POST_VERB, FENCED_ROLE_INJECTION."""

    excerpt: str
    """The raw substring that triggered the match (≤200 chars)."""

    excerpt_hash: str
    """SHA-256 of the raw excerpt — stable identifier for the event payload."""


def scan_for_injection(content: str) -> list[InjectionMatch]:
    """Scan *content* for prompt-injection signatures.

    Returns a list of :class:`InjectionMatch` objects — one per distinct
    matched location. Empty list means clean. Callers should check
    ``bool(matches)`` and emit an event when non-empty.
    """
    matches: list[InjectionMatch] = []

    # 1. INSTRUCTION_OVERRIDE
    for pat in _INSTRUCTION_OVERRIDE_PATTERNS:
        for m in pat.finditer(content):
            excerpt = _excerpt(content, m.start(), m.end())
            matches.append(
                InjectionMatch(
                    category="INSTRUCTION_OVERRIDE",
                    excerpt=excerpt,
                    excerpt_hash=_sha256(excerpt),
                )
            )

    # 2. URL_WITH_POST_VERB
    for url_m in _URL_RE.finditer(content):
        window_start = max(0, url_m.start() - _URL_VERB_WINDOW)
        window_end = min(len(content), url_m.end() + _URL_VERB_WINDOW)
        window = content[window_start:window_end]
        if _POST_VERB_RE.search(window):
            excerpt = _excerpt(content, url_m.start(), url_m.end())
            matches.append(
                InjectionMatch(
                    category="URL_WITH_POST_VERB",
                    excerpt=excerpt,
                    excerpt_hash=_sha256(excerpt),
                )
            )

    # 3. FENCED_ROLE_INJECTION
    for pat in _FENCED_ROLE_PATTERNS:
        for m in pat.finditer(content):
            excerpt = _excerpt(content, m.start(), m.end())
            matches.append(
                InjectionMatch(
                    category="FENCED_ROLE_INJECTION",
                    excerpt=excerpt,
                    excerpt_hash=_sha256(excerpt),
                )
            )

    return matches


# ---------------------------------------------------------------------------
# Dynatrace custom event emitter
# ---------------------------------------------------------------------------


def emit_injection_candidate(
    *,
    matches: list[InjectionMatch],
    span_id: str,
    workspace_entity_id: str,
    dynatrace_api_url: str,
    dynatrace_api_token: str,
    source_url: str = "",
) -> bool:
    """POST a ``sentinelds.injection.candidate`` BIZ_EVENT to Dynatrace.

    Uses the Dynatrace Events API v2 (``/api/v2/events/ingest``). The event is
    attached to the workspace entity so Davis AI and the Sentinel DQL can find
    it by entity.

    Args:
        matches: Non-empty list of matches from :func:`scan_for_injection`.
        span_id: OTel span ID of the ``llm.completion`` / ``tool.web_fetch``
            span that ingested the malicious content.
        workspace_entity_id: Dynatrace entity ID of the workspace
            (e.g. ``CUSTOM_DEVICE-abc123``).
        dynatrace_api_url: Base URL of the Dynatrace tenant
            (e.g. ``https://abc12345.live.dynatrace.com``).
        dynatrace_api_token: API token with ``events.ingest`` scope.
        source_url: URL that was fetched (included in the payload for
            correlation; not required).

    Returns:
        True if Dynatrace accepted the event (HTTP 2xx), False otherwise.
        Failures are logged as warnings — this must never raise, so a broken
        telemetry path cannot block tool execution.
    """
    if not matches:
        return False

    categories = list({m.category for m in matches})
    top_match = matches[0]

    event_body: dict = {
        "eventType": "CUSTOM_INFO",
        "title": "sentinelds.injection.candidate",
        "properties": {
            "event.type": "sentinelds.injection.candidate",
            "event.kind": "BIZ_EVENT",
            "span.id": span_id,
            "matched_categories": ", ".join(sorted(categories)),
            "match_count": str(len(matches)),
            "excerpt_hash": top_match.excerpt_hash,
            "source_url": source_url,
            "workspace_entity_id": workspace_entity_id,
        },
    }
    # Only attach the entitySelector when we have a real Dynatrace entity ID.
    # A placeholder like "WORKSPACE-1" causes a 400 from events/ingest.
    # Without it the event is still ingested and queryable via DQL.
    if workspace_entity_id and not workspace_entity_id.startswith("WORKSPACE-"):
        event_body["entitySelector"] = f'type("CUSTOM_DEVICE"),entityId("{workspace_entity_id}")'

    endpoint = f"{dynatrace_api_url.rstrip('/')}/api/v2/events/ingest"
    headers = {
        "Authorization": f"Api-Token {dynatrace_api_token}",
        "Content-Type": "application/json; charset=utf-8",
    }

    # Best-effort fan-out to the Sentinel audit sidecar. No-op when
    # SENTINEL_AUDIT_URL is unset; never raises (see core.sentinel_audit).
    # We mirror the BIZ_EVENT properties so the sidecar can wrap them in an
    # OTel span and re-emit on the sentinelds-sentinel service entity.
    emit_audit_sync(
        {
            "event.type": "sentinelds.injection.candidate",
            "span.id": span_id,
            "matched_categories": sorted(categories),
            "match_count": len(matches),
            "excerpt_hash": top_match.excerpt_hash,
            "source_url": source_url,
            "workspace_entity_id": workspace_entity_id,
        }
    )

    try:
        response = httpx.post(endpoint, json=event_body, headers=headers, timeout=5.0)
        if response.is_success:
            logger.info(
                "sentinelds.injection.candidate event ingested (span=%s categories=%s)",
                span_id,
                categories,
            )
            return True
        logger.warning(
            "Dynatrace events/ingest returned %s: %s",
            response.status_code,
            response.text[:200],
        )
        return False
    except Exception as exc:
        logger.warning("Failed to emit injection candidate event: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _excerpt(content: str, start: int, end: int, context: int = 80) -> str:
    """Return a ≤200-char excerpt centred on the match, with surrounding context."""
    lo = max(0, start - context)
    hi = min(len(content), end + context)
    raw = content[lo:hi]
    # Truncate to 200 chars total
    return raw[:200]


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


# ---------------------------------------------------------------------------
# Convenience: scan + emit in one call (used by fetch_url)
# ---------------------------------------------------------------------------


def check_and_emit(
    content: str,
    *,
    span_id: str,
    workspace_entity_id: str,
    source_url: str = "",
    dynatrace_api_url: Optional[str] = None,
    dynatrace_api_token: Optional[str] = None,
) -> list[InjectionMatch]:
    """Scan *content* and emit a Dynatrace event if injection signatures are found.

    Does not touch the active OTel span — the caller is responsible for setting
    ``prompt.injection_signature`` and related span attributes based on the
    returned matches. This keeps the function testable without a live tracer.

    Returns the list of matches (empty means clean content).
    """
    matches = scan_for_injection(content)
    if not matches:
        return []

    if dynatrace_api_url and dynatrace_api_token:
        emit_injection_candidate(
            matches=matches,
            span_id=span_id,
            workspace_entity_id=workspace_entity_id,
            dynatrace_api_url=dynatrace_api_url,
            dynatrace_api_token=dynatrace_api_token,
            source_url=source_url,
        )
    else:
        logger.warning(
            "Injection signatures detected but Dynatrace credentials not configured "
            "— event not emitted. span=%s categories=%s",
            span_id,
            [m.category for m in matches],
        )

    return matches
