"""Load YAML while rejecting ambiguous security-policy constructs."""

from collections.abc import Iterator

import yaml
from yaml import AliasEvent, DocumentStartEvent, Event, MappingNode, Node, ScalarNode, SequenceNode
from yaml.composer import ComposerError
from yaml.events import NodeEvent

from streambuild.compiler.access.constants import YAML_MERGE_TAG


def load_strict_yaml(*, contents: str) -> object:
    """Safely load one document after strict syntax validation."""

    document_count: int = 0
    for event in _events(contents=contents):
        if isinstance(event, DocumentStartEvent):
            document_count += 1
            if document_count > 1:
                raise ComposerError(
                    "while composing access policy",
                    event.start_mark,
                    "multiple YAML documents are not allowed",
                    event.start_mark,
                )
        if isinstance(event, AliasEvent):
            raise ComposerError(
                "while composing access policy",
                event.start_mark,
                "YAML aliases are not allowed",
                event.start_mark,
            )
        if isinstance(event, NodeEvent) and event.anchor is not None:
            raise ComposerError(
                "while composing access policy",
                event.start_mark,
                "YAML anchors are not allowed",
                event.start_mark,
            )
    node: Node | None = yaml.compose(contents)
    if node is not None:
        _validate_node(node=node)
    return yaml.safe_load(contents)


def _events(*, contents: str) -> Iterator[Event]:
    yield from yaml.parse(contents)


def _validate_node(*, node: Node) -> None:
    if isinstance(node, MappingNode):
        _validate_mapping(node=node)
        return
    if isinstance(node, SequenceNode):
        for child in node.value:
            _validate_node(node=child)


def _validate_mapping(*, node: MappingNode) -> None:
    seen: set[tuple[str, str]] = set()
    for key_node, value_node in node.value:
        if key_node.tag == YAML_MERGE_TAG:
            raise ComposerError(
                "while composing access policy",
                node.start_mark,
                "YAML merge keys are not allowed",
                key_node.start_mark,
            )
        if not isinstance(key_node, ScalarNode):
            raise ComposerError(
                "while composing access policy",
                node.start_mark,
                "mapping keys must be scalar values",
                key_node.start_mark,
            )
        key: tuple[str, str] = key_node.tag, key_node.value
        if key in seen:
            raise ComposerError(
                "while composing access policy",
                node.start_mark,
                f"duplicate mapping key '{key_node.value}'",
                key_node.start_mark,
            )
        seen.add(key)
        _validate_node(node=value_node)
