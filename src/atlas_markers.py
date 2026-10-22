"""Shared coordinate grouping and icon layout for Qt and baked game maps."""

from collections import defaultdict
from math import ceil, sqrt


def group_nodes(nodes):
    groups = defaultdict(dict)
    for resource, x, y in nodes:
        groups[round(x, 4), round(y, 4)].setdefault(resource["key"], (resource, x, y))
    return [list(group.values()) for group in groups.values()]


def icon_offsets(count, step):
    if count < 1:
        return []
    columns = min(3, ceil(sqrt(count)))
    rows = ceil(count / columns)
    result = []
    for row in range(rows):
        width = min(columns, count - row * columns)
        for column in range(width):
            result.append(((column - (width - 1) / 2) * step, (row - (rows - 1) / 2) * step))
    return result
