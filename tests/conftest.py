"""Shared test fixtures for lemur tests.

Provides fake objects mimicking php-parser-py API at the system boundary.
"""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock


class FakeEdge:
    """Mimics php-parser-py Edge API."""

    def __init__(self, from_nid: str, to_nid: str, edge_type: str = "PARENT_OF", **props: object) -> None:
        self.from_nid = from_nid
        self.to_nid = to_nid
        self.type = edge_type
        self._props = props

    def get(self, key: str) -> object:
        return self._props.get(key)

    def get_property(self, key: str) -> object:
        return self._props.get(key)


class FakeNode:
    """Mimics php-parser-py Node API."""

    def __init__(self, node_id: str, node_type: str, **props: object) -> None:
        self.id = node_id
        self.node_type = node_type
        self._props: dict[str, object] = {"nodeType": node_type, **props}
        self.start_line: int = int(props.get("startLine", 1))
        self.end_line: int = int(props.get("endLine", 1))

    def get_property(self, key: str, default: object = None) -> object:
        return self._props.get(key, default)

    def set_property(self, key: str, value: object) -> None:
        self._props[key] = value

    def set_properties(self, props: dict[str, object]) -> None:
        self._props.update(props)

    def __getitem__(self, key: str) -> object:
        return self._props[key]


class FakeModifier:
    """Mimics php-parser-py Modifier API."""

    def __init__(self, ast: FakeAST) -> None:
        self._ast = ast
        self.ast = ast

    def add_node(self, node_id: str, node_type: str, **props: object) -> FakeNode:
        node = FakeNode(node_id, node_type, **props)
        self._ast._nodes[node_id] = node
        return node

    def add_edge(self, from_id: str, to_id: str, field: str = "", index: int | None = None, edge_type: str = "PARENT_OF") -> None:
        props: dict[str, object] = {"field": field}
        if index is not None:
            props["index"] = index
        edge = FakeEdge(from_id, to_id, edge_type, **props)
        self._ast._edges.append(edge)

    def remove_edge(self, from_id: str, to_id: str, edge_type: str = "PARENT_OF") -> None:
        self._ast._edges = [
            e for e in self._ast._edges
            if not (e.from_nid == from_id and e.to_nid == to_id and e.type == edge_type)
        ]

    def remove_node(self, node_id: str) -> None:
        self._ast._nodes.pop(node_id, None)
        self._ast._edges = [
            e for e in self._ast._edges
            if e.from_nid != node_id and e.to_nid != node_id
        ]


class FakeAST:
    """Mimics php-parser-py AST API."""

    def __init__(self) -> None:
        self._nodes: dict[str, FakeNode] = {}
        self._edges: list[FakeEdge] = []
        self._project: FakeNode | None = None
        self._files: list[FakeNode] = []

    def node(self, node_id: str) -> FakeNode:
        if node_id not in self._nodes:
            raise KeyError(f"Node {node_id} not found")
        return self._nodes[node_id]

    def nodes(self, pred: object = None) -> list[FakeNode]:
        all_nodes = list(self._nodes.values())
        if pred is not None:
            return [n for n in all_nodes if pred(n)]
        return all_nodes

    def first_node(self, pred: object) -> FakeNode | None:
        for n in self._nodes.values():
            if pred(n):
                return n
        return None

    def prev(self, node: FakeNode) -> list[FakeNode]:
        """Return parent nodes (incoming PARENT_OF edges)."""
        parents = []
        for e in self._edges:
            if e.to_nid == node.id and e.type == "PARENT_OF":
                if e.from_nid in self._nodes:
                    parents.append(self._nodes[e.from_nid])
        return parents

    def succ(self, node: FakeNode) -> list[FakeNode]:
        """Return child nodes (outgoing PARENT_OF edges)."""
        children = []
        for e in self._edges:
            if e.from_nid == node.id and e.type == "PARENT_OF":
                if e.to_nid in self._nodes:
                    children.append(self._nodes[e.to_nid])
        return children

    def edge(self, from_id: str, to_id: str, edge_type: str) -> FakeEdge | None:
        for e in self._edges:
            if e.from_nid == from_id and e.to_nid == to_id and e.type == edge_type:
                return e
        return None

    def edges(self, pred: object = None) -> list[FakeEdge]:
        if pred is not None:
            return [e for e in self._edges if pred(e)]
        return list(self._edges)

    def ancestors(self, node: FakeNode) -> list[FakeNode]:
        """BFS ancestors."""
        visited: set[str] = set()
        result: list[FakeNode] = []
        queue = list(self.prev(node))
        while queue:
            current = queue.pop(0)
            if current.id in visited:
                continue
            visited.add(current.id)
            result.append(current)
            queue.extend(self.prev(current))
        return result

    def descendants(self, node: FakeNode) -> list[FakeNode]:
        """BFS descendants."""
        visited: set[str] = set()
        result: list[FakeNode] = []
        queue = list(self.succ(node))
        while queue:
            current = queue.pop(0)
            if current.id in visited:
                continue
            visited.add(current.id)
            result.append(current)
            queue.extend(self.succ(current))
        return result

    def project_node(self) -> FakeNode:
        if self._project is None:
            raise KeyError("No project node")
        return self._project

    def files(self) -> list[FakeNode]:
        return self._files

    def get_file(self, node_id: str) -> FakeNode:
        """Find File node containing node_id by walking ancestors."""
        node = self.node(node_id)
        for ancestor in self.ancestors(node):
            if ancestor.node_type == "File":
                return ancestor
        raise KeyError(f"No File node found for {node_id}")


def build_parent_child(
    ast: FakeAST,
    parent: FakeNode,
    child: FakeNode,
    field: str,
    index: int | None = None,
) -> FakeEdge:
    """Wire parent -> child with a PARENT_OF edge in FakeAST."""
    props: dict[str, object] = {"field": field}
    if index is not None:
        props["index"] = index
    edge = FakeEdge(parent.id, child.id, "PARENT_OF", **props)
    ast._edges.append(edge)
    return edge


@pytest.fixture()
def fake_ast() -> FakeAST:
    """Return an empty FakeAST."""
    return FakeAST()
