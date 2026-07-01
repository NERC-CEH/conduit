from collections.abc import Callable, Collection
from typing import Any

import hamilton.node as node
from hamilton.function_modifiers.base import NodeTransformer, TargetType


class NoOpDecorator(NodeTransformer):
    """A no-op decorator that does nothing.

    Used when a decorator needs to be conditionally applied based on config.
    """

    def __init__(self):
        pass

    def validate(self, fn: Callable):
        pass

    def transform_node(
        self, node_: node.Node, config: dict[str, Any], fn: Callable
    ) -> Collection[node.Node]:
        return [node_]

    def transform_dag(
        self, nodes: Collection[node.Node], config: dict[str, Any], fn: Callable
    ) -> Collection[node.Node]:
        return nodes

    @staticmethod
    def select_nodes(
        target: TargetType, nodes: Collection[node.Node]
    ) -> Collection[node.Node]:
        return []

    @classmethod
    def allows_multiple(cls) -> bool:
        return True

    @classmethod
    def get_lifecycle_name(cls):
        return "transform"
