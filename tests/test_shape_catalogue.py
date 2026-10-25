import pytest

np = pytest.importorskip("numpy")

from front3d_pano.dataset import export_shape

IDENTITY = np.eye(3)


def cube_triangles(low, high):
    corners = np.array([[x, y, z] for x in (low[0], high[0])
                        for y in (low[1], high[1]) for z in (low[2], high[2])], dtype=float)
    faces = [(0, 1, 3), (0, 3, 2), (4, 6, 7), (4, 7, 5), (0, 4, 5), (0, 5, 1),
             (2, 3, 7), (2, 7, 6), (0, 2, 6), (0, 6, 4), (1, 5, 7), (1, 7, 3)]
    return np.array([[corners[a], corners[b], corners[c]] for a, b, c in faces])


def test_mesh_is_placed_in_the_unit_box_of_the_instance():
    triangles = cube_triangles((2.0, 2.0, 0.0), (3.0, 4.0, 1.0))
    bbox = {"center": [3.0, 4.0, 0.0], "size": [2.0, 4.0, 2.0], "basis": IDENTITY.tolist()}
    vertices, faces = export_shape.unit_mesh(
        triangles, bbox, camera=np.array([2.0, 2.0, 1.0]), scale=2.0)
    assert vertices.min() == pytest.approx(-0.5)
    assert vertices.max() == pytest.approx(0.5)
    assert len(faces) == len(triangles)


def test_a_rotated_instance_maps_onto_the_same_unit_box():
    triangles = cube_triangles((-0.5, -1.0, -0.25), (0.5, 1.0, 0.25))
    angle = np.pi / 3
    basis = np.array([[np.cos(angle), np.sin(angle), 0.0],
                      [-np.sin(angle), np.cos(angle), 0.0], [0.0, 0.0, 1.0]])
    rotated = triangles.reshape(-1, 3) @ basis
    bbox = {"center": [0.0, 0.0, 0.0], "size": [1.0, 2.0, 0.5], "basis": basis.tolist()}
    vertices, _ = export_shape.unit_mesh(
        rotated.reshape(triangles.shape), bbox, camera=np.zeros(3), scale=1.0)
    assert vertices.min() == pytest.approx(-0.5, abs=1e-9)
    assert vertices.max() == pytest.approx(0.5, abs=1e-9)


def test_object_id_is_unique_per_instance_and_keeps_the_source_path():
    first = export_shape.object_id("house/room/Bed_uuid_1.glb")
    second = export_shape.object_id("house/other-room/Bed_uuid_1.glb")
    assert first != second
    assert first == "house__room__Bed_uuid_1"
