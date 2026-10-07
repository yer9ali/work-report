"""Secrets never leave the digest: passwords, tokens and long base64 blobs are masked."""

from __future__ import annotations

import re

_PASSWORD_ELEMENT = re.compile(
    r"(<((?:[\w.-]+:)?password)(?:\s[^>]*)?>)(.*?)(</\2\s*>)", re.S | re.I
)
# Match prefixed key names: DB_PASSWORD, my_password, access_token, refresh_token, etc.
# Also handle headers like Authorization, X-Internal-Token
# Also handle JSON-style quoted keys: "token", "secret", etc.
# Separator can be : or = with surrounding whitespace captured
# Value pattern differs for authorization vs other keys:
# - authorization: scheme word + credential (both consumed)
# - other keys: single token or quoted string only
_KEY_VALUE_AUTH = re.compile(
    r"""(?ix)
    ("?)
    (authorization)
    \1
    (\s*[:=]\s*)
    ("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|[^\s,;&}\n]+(?:[ \t]+[^\s,;&}\n]+)?)
    """
)

_KEY_VALUE_OTHER = re.compile(
    r"""(?ix)
    ("?)
    ([\w.-]*(?:x-internal-token|password|passwd|secret|token|api[_-]?key)[\w.-]*)
    \1
    (\s*[:=]\s*)
    ("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|[^\s,;&}\n]+)
    """
)

# Bare Bearer, Basic, or Token scheme without a key name
_BARE_SCHEME = re.compile(r"\b(Bearer|Basic|Token)[ \t]+([A-Za-z0-9._~+/=-]{8,})")

_LONG_BASE64 = re.compile(r"[A-Za-z0-9+/]{200,}={0,2}")


def _mask_value(match: re.Match[str]) -> str:
    quote = match.group(1)  # optional quote at start of key
    key = match.group(2)  # the keyword itself
    sep_and_space = match.group(3)  # separator with surrounding whitespace
    value = match.group(4)  # the value

    # Reconstruct the key part with quotes if present
    key_part = f"{quote}{key}{quote}"

    # Handle quoted values (preserve quote type)
    if value[:1] in {'"', "'"}:
        return f"{key_part}{sep_and_space}{value[0]}***{value[0]}"
    return f"{key_part}{sep_and_space}***"


def mask_secrets(text: str) -> str:
    text = _PASSWORD_ELEMENT.sub(r"\1***\4", text)
    # Apply authorization-specific pattern first (allows two-word values)
    text = _KEY_VALUE_AUTH.sub(_mask_value, text)
    # Apply general pattern for other keys (single token/quote only)
    text = _KEY_VALUE_OTHER.sub(_mask_value, text)
    # Mask bare scheme tokens (Bearer abc, Basic xyz, Token 123)
    text = _BARE_SCHEME.sub(r"\1 ***", text)
    # Mask URL userinfo: https://user:password@host → https://user:***@host
    # Restrict to authority part to avoid matching ports and paths
    text = re.sub(r"(://[^\s:/@]+:)([^\s/@]+)(@)", r"\1***\3", text)
    return _LONG_BASE64.sub(lambda m: f"[base64 {len(m.group(0)) * 3 // 4} байт]", text)
