"""Source positions for YAML text.

PyYAML's ``compose`` builds a node tree in which every node carries a start
mark, so unlike JSON no separate scanner is needed — the positions are already
there, they only need walking.
"""

from __future__ import annotations

import yaml

from .base import Path, SourceMap

__all__ = ["yaml_source_map"]


def yaml_source_map(text: str) -> SourceMap:
    """Build a source map for YAML text using PyYAML's node marks.

    Parameters
    ----------
    text : str
        The YAML document as it appears on disk.

    Returns
    -------
    SourceMap
        Positions for every node in the document. Empty if the text could not
        be composed; this function never raises.

    Notes
    -----
    Composed with :class:`yaml.SafeLoader`, so no arbitrary Python objects are
    constructed while resolving positions.

    Examples
    --------
    >>> document = "title: MyTool\\nversion: '1.0.0'\\n"
    >>> source_map = yaml_source_map(document)
    >>> source_map.locate(("version",))
    (2, 1)

    Sequence entries are addressed by index, and mapping keys inside them by
    name:

    >>> document = "authors:\\n  - family-names: Doe\\n    given-names: Jane\\n"
    >>> yaml_source_map(document).locate(("authors", 0, "given-names"))
    (3, 5)

    Malformed YAML yields an empty map rather than an exception:

    >>> bool(yaml_source_map("key: [unclosed\\n"))
    False
    """
    try:
        root = yaml.compose(text, Loader=yaml.SafeLoader)
    except yaml.YAMLError:
        return SourceMap()
    if root is None:
        return SourceMap()

    positions: dict[Path, tuple[int, int]] = {}

    def walk(node: yaml.Node, path: Path) -> None:
        mark = node.start_mark
        positions.setdefault(path, (mark.line + 1, mark.column + 1))
        if isinstance(node, yaml.MappingNode):
            for key_node, value_node in node.value:
                key = getattr(key_node, "value", None)
                if not isinstance(key, str):
                    continue
                child = (*path, key)
                positions[child] = (
                    key_node.start_mark.line + 1,
                    key_node.start_mark.column + 1,
                )
                walk(value_node, child)
        elif isinstance(node, yaml.SequenceNode):
            for position, item in enumerate(node.value):
                walk(item, (*path, position))

    walk(root, ())
    return SourceMap(positions)
