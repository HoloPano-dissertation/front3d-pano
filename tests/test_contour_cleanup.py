import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("shapely")
from shapely.geometry import Polygon, mapping


@pytest.fixture
def cleanup(monkeypatch):
    from front3d_pano.dataset import contour_cleanup
    return contour_cleanup


def ring(polygon):
    return [tuple(round(v, 6) for v in p) for p in polygon.exterior.coords[:-1]]


def test_a_vertex_on_a_straight_wall_is_dropped_even_at_the_ring_start(cleanup):
    polygon = Polygon([(0, 1.9), (0, 2), (1.5, 2), (1.5, 0), (0, 0)])
    cleaned, report = cleanup.clean_contour(polygon, [(0.5, 0.5)])
    assert len(ring(cleaned)) == 4
    assert report["straight_vertices_removed"] == 1
    assert cleaned.area == pytest.approx(polygon.area)


def test_the_result_runs_clockwise(cleanup):
    counter_clockwise = Polygon([(0, 0), (4, 0), (4, 3), (0, 3)])
    assert counter_clockwise.exterior.is_ccw
    cleaned, _ = cleanup.clean_contour(counter_clockwise, [(1, 1)])
    assert not cleaned.exterior.is_ccw


def test_a_door_reveal_is_flattened_into_the_wall(cleanup):
    polygon = Polygon([(0, 0), (4, 0), (4, 3), (2.4, 3), (2.4, 3.24), (1.5, 3.24),
                       (1.5, 3), (0, 3)])
    cleaned, report = cleanup.clean_contour(polygon, [(2, 1.5)])
    assert sorted(ring(cleaned)) == [(0, 0), (0, 3), (4, 0), (4, 3)]
    assert report["steps_flattened"] >= 1
    assert report["area_change"] == pytest.approx(-0.9 * 0.24 / polygon.area, rel=1e-6)


def test_a_niche_deeper_than_the_threshold_stays(cleanup):
    polygon = Polygon([(0, 0), (4, 0), (4, 3), (2.4, 3), (2.4, 3.5), (1.5, 3.5),
                       (1.5, 3), (0, 3)])
    cleaned, report = cleanup.clean_contour(polygon, [(2, 1.5)])
    assert len(ring(cleaned)) == 8
    assert report["steps_flattened"] == 0


def test_a_wall_stub_is_real_geometry_and_stays(cleanup):
    polygon = Polygon([(0, 0), (4, 0), (4, 3), (2.15, 3), (2.15, 2.4), (2.0, 2.4),
                       (2.0, 3), (0, 3)])
    cleaned, _ = cleanup.clean_contour(polygon, [(1, 1)])
    assert len(ring(cleaned)) == 8


def test_millimetre_slivers_at_a_door_trim_vanish(cleanup):
    polygon = Polygon([(0, 0), (4, 0), (4, 3), (2.004, 3), (2.002, 3.006), (1.998, 3.004),
                       (1.995, 3.0), (0, 3)])
    cleaned, _ = cleanup.clean_contour(polygon, [(2, 1.5)])
    assert sorted(ring(cleaned)) == [(0, 0), (0, 3), (4, 0), (4, 3)]


def test_a_step_is_kept_when_flattening_it_would_cut_off_a_camera(cleanup):
    polygon = Polygon([(0, 0), (4, 0), (4, 3), (2.4, 3), (2.4, 3.24), (1.5, 3.24),
                       (1.5, 3), (0, 3)])
    cleaned, report = cleanup.clean_contour(polygon, [(2, 1.5), (2, 3.15)])
    assert cleaned.contains(polygon.representative_point())
    assert len(ring(cleaned)) == 8
    assert report["steps_refused"] >= 1


def test_thresholds_are_metres_whatever_the_contour_units(cleanup):
    scale = 3.0
    metric = [(0, 0), (4, 0), (4, 3), (2.4, 3), (2.4, 3.24), (1.5, 3.24), (1.5, 3), (0, 3)]
    polygon = Polygon([(x / scale, y / scale) for x, y in metric])
    cleaned, _ = cleanup.clean_contour(polygon, [(2 / scale, 1.5 / scale)], metres_per_unit=scale)
    assert len(ring(cleaned)) == 4
    unscaled, _ = cleanup.clean_contour(polygon, [(2 / scale, 1.5 / scale)])
    assert len(ring(unscaled)) == 4
    niche = Polygon([(x / scale, y / scale) for x, y in
                     [(0, 0), (4, 0), (4, 3), (2.4, 3), (2.4, 3.5), (1.5, 3.5), (1.5, 3), (0, 3)]])
    kept, _ = cleanup.clean_contour(niche, [(2 / scale, 1.5 / scale)], metres_per_unit=scale)
    assert len(ring(kept)) == 8


def test_an_l_shaped_room_keeps_all_six_corners(cleanup):
    polygon = Polygon([(0, 0), (3, 0), (3, 1), (1, 1), (1, 3), (0, 3)])
    cleaned, report = cleanup.clean_contour(polygon, [(0.5, 0.5)])
    assert len(ring(cleaned)) == 6
    assert report["area_change"] == pytest.approx(0.0)


def test_holes_survive_the_cleanup(cleanup):
    polygon = Polygon([(0, 0), (4, 0), (4, 4), (0, 4)], holes=[[(1, 1), (2, 1), (2, 2), (1, 2)]])
    cleaned, _ = cleanup.clean_contour(polygon, [(3, 3)])
    assert len(cleaned.interiors) == 1
    assert cleaned.area == pytest.approx(polygon.area)


def test_clean_layout_updates_area_bounds_and_records_the_report(cleanup):
    polygon = Polygon([(0, 0), (4, 0), (4, 3), (2.4, 3), (2.4, 3.24), (1.5, 3.24),
                       (1.5, 3), (0, 3)])
    layout = {"polygon": mapping(polygon), "area": polygon.area, "floor_z": 0.0,
              "ceiling_z": 2.6, "bounds_min": [0, 0, 0.0], "bounds_max": [4, 3.24, 2.6]}
    cleaned = cleanup.clean_layout(layout, [(2, 1.5)])
    assert cleaned["area"] == pytest.approx(12.0)
    assert cleaned["bounds_max"] == pytest.approx([4, 3, 2.6])
    assert cleaned["contour_cleanup"]["vertices_before"] == 8
    assert cleaned["contour_cleanup"]["vertices_after"] == 4
    assert layout["area"] == pytest.approx(polygon.area)


def test_a_finely_sampled_wall_is_thinned_vertex_by_vertex(cleanup):
    xs = np.linspace(0.0, 4.0, 81)
    top = [(float(x), 3.0 + 0.004 * ((i % 2) * 2 - 1)) for i, x in enumerate(xs)][::-1]
    polygon = Polygon([(0, 0), (4, 0)] + top)
    cleaned, report = cleanup.clean_contour(polygon, [(2, 1.5)])
    assert len(ring(cleaned)) <= 6
    assert report["straight_vertices_removed"] >= 75
