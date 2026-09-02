"""Which adapters exist, and in what order they are reported.

Registration order is reporting order. The anchor comes first, then the file
required alongside it, then the optional formats that are auto-detected when a
repository happens to contain them.

To add a format, write an adapter and a mapping file and add it to
:data:`ADAPTERS`. Nothing else in the codebase needs to change.
"""

from __future__ import annotations

from .base import Adapter
from .biotools import BiotoolsAdapter
from .cargo import CargoAdapter
from .cff import CffAdapter
from .codemeta import CodeMetaAdapter
from .github import GitHubAdapter
from .julia_project import JuliaProjectAdapter
from .oci_labels import DockerfileAdapter
from .package_json import PackageJsonAdapter
from .pyproject import PyprojectAdapter
from .r_description import RDescriptionAdapter
from .zenodo import ZenodoAdapter

__all__ = ["ADAPTERS", "ANCHOR", "companion_adapters", "get_adapter"]

#: The canonical record every other source is compared against.
ANCHOR = CodeMetaAdapter()

ADAPTERS: tuple[Adapter, ...] = (
    ANCHOR,
    CffAdapter(),
    GitHubAdapter(),
    ZenodoAdapter(),
    BiotoolsAdapter(),
    PyprojectAdapter(),
    PackageJsonAdapter(),
    RDescriptionAdapter(),
    CargoAdapter(),
    JuliaProjectAdapter(),
    DockerfileAdapter(),
)


def companion_adapters() -> tuple[Adapter, ...]:
    """Every adapter except the anchor, in reporting order.

    Returns
    -------
    tuple of Adapter
        The formats compared against ``codemeta.json``.

    Examples
    --------
    >>> for adapter in companion_adapters():
    ...     print(adapter.id)
    cff
    github
    zenodo
    biotools
    pyproject
    package-json
    r-description
    cargo
    julia-project
    dockerfile

    The anchor is excluded because the companions are compared *to* it:

    >>> ANCHOR.id in {adapter.id for adapter in companion_adapters()}
    False
    """
    return tuple(adapter for adapter in ADAPTERS if adapter.role != "anchor")


def get_adapter(adapter_id: str) -> Adapter:
    """Look up a registered adapter by its identifier.

    Parameters
    ----------
    adapter_id : str
        The adapter's ``id``, as it appears in a report's ``sources``.

    Returns
    -------
    Adapter
        The registered adapter.

    Raises
    ------
    KeyError
        If nothing is registered under that id.

    Examples
    --------
    >>> get_adapter("cff").format
    'Citation File Format'
    >>> get_adapter("nonexistent")
    Traceback (most recent call last):
        ...
    KeyError: "No adapter registered with id 'nonexistent'."
    """
    for adapter in ADAPTERS:
        if adapter.id == adapter_id:
            return adapter
    raise KeyError(f"No adapter registered with id {adapter_id!r}.")
