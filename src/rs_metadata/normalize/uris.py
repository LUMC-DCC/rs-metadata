"""URL normalization.

One repository is written half a dozen ways across a research project's
metadata: with and without ``https``, with and without ``www.``, with a
trailing slash, with a ``.git`` suffix, as an SSH remote, or as an npm
shorthand. All of them address the same resource.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from .scalars import normalize_text

__all__ = ["normalize_uri"]

_SSH_URL_RE = re.compile(r"^(?:ssh://)?git@([^:/]+)[:/](.+)$")
_NPM_SHORTHAND_RE = re.compile(
    r"^(?:(github|gitlab|bitbucket):)?([\w.\-]+)/([\w.\-]+)$", re.IGNORECASE
)

#: npm's shorthand hosts. Expansion is opt-in because a bare ``owner/name``
#: is only unambiguous in an npm context; elsewhere it may be a real path.
_HOSTS = {"github": "github.com", "gitlab": "gitlab.com", "bitbucket": "bitbucket.org"}


def normalize_uri(raw: Any, *, expand_shorthand: bool = False) -> str | None:
    """Normalize a URL so cosmetic differences do not read as disagreement.

    Parameters
    ----------
    raw : Any
        A URL, an SSH remote, or (with ``expand_shorthand``) an npm shorthand.
    expand_shorthand : bool, optional
        Expand npm's ``owner/name`` and ``github:owner/name`` forms. Off by
        default because a bare ``owner/name`` is only unambiguous in an npm
        context.

    Returns
    -------
    str or None
        A comparison key: host and path, without the scheme for ``http`` and
        ``https``. ``None`` if empty.

    Notes
    -----
    The scheme is dropped only for ``http`` and ``https``, which address the
    same resource. Other schemes are meaningful and are kept, so a ``mailto:``
    can never collide with a web address.

    Examples
    --------
    Every spelling of one repository collapses to the same key:

    >>> spellings = [
    ...     "https://github.com/org/tool",
    ...     "http://github.com/org/tool",
    ...     "https://github.com/org/tool/",
    ...     "https://github.com/org/tool.git",
    ...     "https://www.github.com/org/tool",
    ...     "git+https://github.com/org/tool.git",
    ...     "git@github.com:org/tool.git",
    ...     "https://github.com:443/org/tool",
    ... ]
    >>> {normalize_uri(spelling) for spelling in spellings}
    {'github.com/org/tool'}

    Different repositories stay different:

    >>> normalize_uri("https://github.com/a/tool") == normalize_uri(
    ...     "https://github.com/b/tool"
    ... )
    False

    npm shorthand is expanded only when asked:

    >>> normalize_uri("org/tool", expand_shorthand=True)
    'github.com/org/tool'
    >>> normalize_uri("github:org/tool", expand_shorthand=True)
    'github.com/org/tool'
    >>> normalize_uri("org/tool")
    'org/tool'

    Non-web schemes keep their scheme:

    >>> normalize_uri("mailto:rse@example.org")
    'mailto:rse@example.org'
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None

    text = re.sub(r"^git\+", "", text)
    ssh = _SSH_URL_RE.match(text)
    if ssh:
        text = f"https://{ssh.group(1)}/{ssh.group(2)}"
    elif expand_shorthand:
        shorthand = _NPM_SHORTHAND_RE.match(text)
        if shorthand and "://" not in text:
            host = _HOSTS[(shorthand.group(1) or "github").lower()]
            text = f"https://{host}/{shorthand.group(2)}/{shorthand.group(3)}"

    parts = urlsplit(text)
    if not parts.scheme:
        return normalize_text(text)

    host = re.sub(r"^www\.", "", parts.netloc.casefold())
    host = re.sub(r":(?:80|443)$", "", host)
    path = re.sub(r"\.git$", "", parts.path.rstrip("/"))
    scheme = parts.scheme.casefold()
    prefix = "" if scheme in {"http", "https"} else f"{scheme}:"
    query = f"?{parts.query}" if parts.query else ""
    return f"{prefix}{host}{path}{query}" or None
