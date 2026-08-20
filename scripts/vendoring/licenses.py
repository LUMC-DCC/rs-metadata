"""Parser for the SPDX license list."""

from __future__ import annotations

from typing import Any


def build_spdx_index(licenses_document: dict[str, Any]) -> dict[str, Any]:
    """Distil the SPDX license list down to what the validator needs.

    The upstream file is ~330 kB of cross-reference URLs; the validator only
    resolves an identifier to a name and needs to know whether it is
    deprecated, so the vendored copy keeps just that.
    """
    licenses = {}
    for entry in licenses_document["licenses"]:
        licenses[entry["licenseId"]] = {
            "name": entry["name"],
            "deprecated": bool(entry.get("isDeprecatedLicenseId", False)),
            "osiApproved": bool(entry.get("isOsiApproved", False)),
        }
    return {
        "licenseListVersion": licenses_document.get("licenseListVersion"),
        "releaseDate": licenses_document.get("releaseDate"),
        "licenses": dict(sorted(licenses.items())),
    }
