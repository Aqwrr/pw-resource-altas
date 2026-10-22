"""Coordinate-only gathering loops; no game input or live resource tracking."""

import math

MAX_POINTS = 120
WORLD_KEYS = ("world", "a21", "a22")


def validate_route(points):
    if not isinstance(points, (list, tuple)) or len(points) > MAX_POINTS:
        raise ValueError("В круге может быть не больше 120 точек.")
    result = []
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError("Точка маршрута должна содержать две координаты.")
        if any(
            isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
            for v in point
        ):
            raise ValueError("Некорректные координаты маршрута.")
        result.append(list(point))
    return result


def world_routes(routes=None, legacy=None):
    if routes is None:
        routes = {"world": legacy or []}
    if not isinstance(routes, dict):
        raise ValueError("Некорректный список маршрутов.")
    return {world: validate_route(routes.get(world, [])) for world in WORLD_KEYS}


def build_loop(points, start):
    # Co-located herbs/materials are one stop, regardless of their icon offsets.
    nodes = sorted({(round(x, 4), round(y, 4)) for x, y in points})
    if len(nodes) < 2:
        raise ValueError("Для круга нужны хотя бы две выбранные точки в видимой области.")
    if len(nodes) > MAX_POINTS:
        raise ValueError(
            f"В кадре {len(nodes)} точек. Приблизьте район или сократите выбор до 120 точек."
        )
    route = []
    current = start
    while nodes:
        current = min(nodes, key=lambda xy: math.dist(xy, current))
        route.append(current)
        nodes.remove(current)
    # Shorten the closed loop, including the return leg, while keeping its start.
    for _ in range(8):
        changed = False
        for i in range(len(route) - 2):
            for j in range(i + 2, len(route)):
                if i == 0 and j == len(route) - 1:
                    continue
                a, b, c, d = route[i], route[i + 1], route[j], route[(j + 1) % len(route)]
                if math.dist(a, c) + math.dist(b, d) < math.dist(a, b) + math.dist(c, d) - 1e-8:
                    route[i + 1 : j + 1] = reversed(route[i + 1 : j + 1])
                    changed = True
        if not changed:
            break
    return [list(point) for point in route]
