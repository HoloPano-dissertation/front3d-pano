import math

import numpy as np
from shapely.geometry import Point, Polygon, mapping, shape
from shapely.geometry.polygon import orient

TOLERANCE = 0.03
STEP = 0.30
MAX_AREA_CHANGE = 0.03
MAX_SHIFT = 2.0
CAMERA_CLEARANCE = 0.05
ALIGNED = math.sin(math.radians(5.0))


def _segment_distance(point, start, end):
    along = end - start
    length = float(along @ along)
    if length <= 1e-18:
        return float(np.linalg.norm(point - start))
    t = min(1.0, max(0.0, float((point - start) @ along) / length))
    return float(np.linalg.norm(point - (start + t * along)))


def _drop_straight(ring, tolerance, accept):
    removed = 0
    while len(ring) > 3:
        n = len(ring)
        deviations = [_segment_distance(ring[i], ring[i - 1], ring[(i + 1) % n]) for i in range(n)]
        for index in sorted((i for i in range(n) if deviations[i] < tolerance),
                            key=lambda i: deviations[i]):
            candidate = np.delete(ring, index, axis=0)
            if accept(candidate):
                ring, removed = candidate, removed + 1
                break
        else:
            break
    return ring, removed


def _unit(vector):
    length = float(np.hypot(*vector))
    return vector / length if length > 1e-12 else vector * 0.0


def _cross(a, b):
    return float(a[0] * b[1] - a[1] * b[0])


def _step_moves(ring, index, step, max_shift):
    n = len(ring)
    edge = ring[(index + 1) % n] - ring[index]
    if not 0.0 < float(np.hypot(*edge)) < step:
        return []
    before, after = ring[index] - ring[index - 1], ring[(index + 2) % n] - ring[(index + 1) % n]
    u_before, u_after, u_edge = _unit(before), _unit(after), _unit(edge)
    if abs(_cross(u_before, u_after)) > ALIGNED or float(u_before @ u_after) <= 0.0:
        return []
    if abs(float(u_edge @ u_before)) > ALIGNED:
        return []
    if float(np.hypot(*after)) <= float(np.hypot(*before)):
        moved_length, beyond, shifted, offset = (
            float(np.hypot(*after)), ring[(index + 3) % n] - ring[(index + 2) % n],
            (index + 1, index + 2), -edge)
    else:
        moved_length, beyond, shifted, offset = (
            float(np.hypot(*before)), ring[index - 1] - ring[index - 2],
            (index - 1, index), edge)
    if moved_length > max_shift or abs(_cross(_unit(beyond), u_edge)) > ALIGNED:
        return []
    moved = ring.copy()
    for k in shifted:
        moved[k % n] = moved[k % n] + offset
    return [moved]


def _acceptable(ring, holes, cameras, area_limit, original_area):
    if len(ring) < 3:
        return False
    polygon = Polygon(ring, holes)
    if not polygon.is_valid or polygon.is_empty:
        return False
    if abs(polygon.area - original_area) > area_limit:
        return False
    for point, clearance in cameras:
        if not polygon.contains(point) or polygon.boundary.distance(point) < clearance:
            return False
    return True


def _dedupe(ring):
    keep = [0]
    for i in range(1, len(ring)):
        if np.hypot(*(ring[i] - ring[keep[-1]])) > 1e-9:
            keep.append(i)
    ring = ring[keep]
    if len(ring) > 1 and np.hypot(*(ring[0] - ring[-1])) <= 1e-9:
        ring = ring[:-1]
    return ring


def clean_contour(polygon, cameras, metres_per_unit=1.0, step=STEP, tolerance=TOLERANCE,
                  max_area_change=MAX_AREA_CHANGE, max_shift=MAX_SHIFT):
    polygon = shape(polygon) if isinstance(polygon, dict) else polygon
    unit = 1.0 / float(metres_per_unit)
    step, tolerance, clearance = step * unit, tolerance * unit, CAMERA_CLEARANCE * unit
    max_shift = max_shift * unit
    holes = [list(interior.coords) for interior in polygon.interiors]
    original_area = float(polygon.area)
    area_limit = max_area_change * original_area
    cameras = [Point(np.asarray(c, dtype=float)[:2]) for c in cameras]
    cameras = [(point, min(clearance, polygon.boundary.distance(point) - 1e-9))
               for point in cameras]
    def accept(candidate):
        return _acceptable(candidate, holes, cameras, area_limit, original_area)

    ring = _dedupe(np.asarray(polygon.exterior.coords, dtype=float)[:-1])
    before = len(ring)
    ring, straight = _drop_straight(ring, tolerance, accept)
    flattened = refused = 0
    while True:
        n = len(ring)
        lengths = [float(np.hypot(*(ring[(i + 1) % n] - ring[i]))) for i in range(n)]
        progress = False
        for index in sorted(range(n), key=lambda i: lengths[i]):
            if lengths[index] >= step:
                break
            candidates = _step_moves(ring, index, step, max_shift)
            for candidate in candidates:
                candidate = _dedupe(candidate)
                if accept(candidate):
                    ring, dropped = _drop_straight(candidate, tolerance, accept)
                    straight, flattened = straight + dropped, flattened + 1
                    progress = True
                    break
            else:
                refused += bool(candidates)
                continue
            break
        if not progress:
            break
    cleaned = orient(Polygon(ring, holes), sign=-1.0)
    report = {
        "vertices_before": before,
        "vertices_after": len(cleaned.exterior.coords) - 1,
        "straight_vertices_removed": straight,
        "steps_flattened": flattened,
        "steps_refused": refused,
        "area_change": (float(cleaned.area) - original_area) / original_area if original_area else 0.0,
    }
    return cleaned, report


def clean_layout(layout, cameras, metres_per_unit=1.0, **options):
    polygon, report = clean_contour(layout["polygon"], cameras, metres_per_unit, **options)
    cleaned = dict(layout)
    cleaned["polygon"] = mapping(polygon)
    cleaned["area"] = float(polygon.area)
    low_x, low_y, high_x, high_y = polygon.bounds
    if layout.get("bounds_min") is not None:
        cleaned["bounds_min"] = [low_x, low_y, float(layout["bounds_min"][2])]
    if layout.get("bounds_max") is not None:
        cleaned["bounds_max"] = [high_x, high_y, float(layout["bounds_max"][2])]
    cleaned["contour_cleanup"] = dict(report, step_m=options.get("step", STEP),
                                      tolerance_m=options.get("tolerance", TOLERANCE))
    return cleaned
