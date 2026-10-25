import json
import struct

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("shapely")
from front3d_pano.render import glb_geometry as geometry


def rectangle(x0, y0, x1, y1, z=0):
    return np.array([[[x0, y0, z], [x1, y0, z], [x1, y1, z]],
                     [[x0, y0, z], [x1, y1, z], [x0, y1, z]]], dtype=float)


def test_l_shaped_floor_rejects_empty_bbox_corner():
    from shapely.geometry import Point
    triangles = np.concatenate([rectangle(0, 0, 2, 1), rectangle(0, 1, 1, 2)])
    footprint, _ = geometry.floor_footprint(triangles)
    assert footprint.area == pytest.approx(3)
    assert not footprint.covers(Point(1.5, 1.5))
    assert footprint.covers(Point(0.5, 1.5))


def test_floor_hole_and_disconnected_components():
    triangles = np.concatenate([rectangle(0, 0, 3, 1), rectangle(0, 2, 3, 3),
                                rectangle(0, 1, 1, 2), rectangle(2, 1, 3, 2)])
    footprint, _ = geometry.floor_footprint(triangles)
    assert len(footprint.interiors) == 1
    separate, _ = geometry.floor_footprint(np.concatenate([rectangle(0, 0, 1, 1), rectangle(2, 0, 3, 1)]))
    assert separate.geom_type == "MultiPolygon" and len(separate.geoms) == 2


def test_winding_overlap_and_slab_do_not_double_area():
    floor = rectangle(0, 0, 2, 3)
    slab = np.concatenate([floor, floor[:, ::-1], rectangle(0, 0, 2, 3, -0.1)])
    footprint, _ = geometry.floor_footprint(slab)
    assert footprint.area == pytest.approx(6)


def test_rotated_rectangle_is_not_nonrectangular():
    triangles = rectangle(-1, -1, 1, 1)
    angle = np.pi / 4
    rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    triangles[:, :, :2] = triangles[:, :, :2] @ rotation.T
    footprint, _ = geometry.floor_footprint(triangles)
    assert footprint.area == pytest.approx(4)
    assert footprint.minimum_rotated_rectangle.area == pytest.approx(4)


def test_vertical_walls_not_floor():
    wall = np.array([[[0, 0, 0], [1, 0, 0], [1, 0, 2]]], dtype=float)
    with pytest.raises(ValueError, match="horizontal"):
        geometry.floor_footprint(wall)


def write_fixture(path, indexed=True, translation=(0, 0, 0), matrix=None, mode=4):
    points = np.asarray([[0, 0, 0], [1, 0, 0], [0, 0, 1]], dtype="<f4")
    binary = points.tobytes() + np.asarray([0, 1, 2], dtype="<u2").tobytes() + b"\0\0"
    node = {"mesh": 0, "translation": list(translation)}
    if matrix is not None:
        node = {"mesh": 0, "matrix": matrix.T.reshape(-1).tolist()}
    primitive = {"attributes": {"POSITION": 0}, "mode": mode}
    if indexed:
        primitive["indices"] = 1
    document = {"asset": {"version": "2.0"}, "scene": 0,
                "scenes": [{"nodes": [0]}], "nodes": [{"translation": [10, 20, 30], "children": [1]}, node],
                "meshes": [{"primitives": [primitive]}], "buffers": [{"byteLength": len(binary)}],
                "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 36},
                                {"buffer": 0, "byteOffset": 36, "byteLength": 6}],
                "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"},
                              {"bufferView": 1, "componentType": 5123, "count": 3, "type": "SCALAR"}]}
    content = json.dumps(document).encode()
    content += b" " * (-len(content) % 4)
    path.write_bytes(struct.pack("<4sII", b"glTF", 2, 28+len(content)+len(binary))
                     + struct.pack("<II", len(content), 0x4E4F534A) + content
                     + struct.pack("<II", len(binary), 0x004E4942) + binary)


@pytest.mark.parametrize("indexed", [False, True])
def test_glb_hierarchy_and_axis_conversion(tmp_path, indexed):
    path = tmp_path / "floor.glb"
    write_fixture(path, indexed=indexed, translation=(1, 2, 3))
    triangles = geometry.glb_triangles(path)
    np.testing.assert_allclose(triangles, [[[11, -33, 22], [12, -33, 22], [11, -34, 22]]])


def test_glb_matrix_scale_and_translation(tmp_path):
    path = tmp_path / "floor.glb"
    matrix = np.diag([2., 3., 4., 1.])
    matrix[:3, 3] = [1, 2, 3]
    write_fixture(path, matrix=matrix)
    np.testing.assert_allclose(geometry.glb_triangles(path), [[[11, -33, 22], [13, -33, 22], [11, -37, 22]]])


def test_unsupported_primitives_fail_closed(tmp_path):
    path = tmp_path / "lines.glb"
    write_fixture(path, mode=1)
    with pytest.raises(ValueError, match="TRIANGLES"):
        geometry.glb_triangles(path)
