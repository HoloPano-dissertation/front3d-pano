import json
import struct
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union


DTYPES = {5120: "i1", 5121: "u1", 5122: "<i2", 5123: "<u2",
          5125: "<u4", 5126: "<f4"}
COMPONENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def load_glb(path):
    with Path(path).open("rb") as stream:
        magic, version, length = struct.unpack("<4sII", stream.read(12))
        if magic != b"glTF" or version != 2 or length != Path(path).stat().st_size:
            raise ValueError(f"Invalid GLB header: {path}")
        document, binary = None, None
        while stream.tell() < length:
            size, kind = struct.unpack("<II", stream.read(8))
            chunk = stream.read(size)
            if len(chunk) != size:
                raise ValueError("Truncated GLB")
            if kind == 0x4E4F534A:
                document = json.loads(chunk.decode().rstrip("\x00 \t\n\r"))
            elif kind == 0x004E4942:
                binary = chunk
    if document is None or binary is None:
        raise ValueError("Expected JSON and BIN chunks")
    if any("uri" in entry for entry in document.get("buffers", [])):
        raise ValueError("External GLB buffers are not supported")
    return document, binary


def accessor(document, binary, index):
    item = document["accessors"][index]
    if "sparse" in item or item.get("normalized", False):
        raise ValueError("Sparse/normalized accessors are not supported")
    view = document["bufferViews"][item["bufferView"]]
    if view.get("buffer", 0) != 0 or view.get("extensions"):
        raise ValueError("Unsupported buffer or compressed buffer view")
    dtype = np.dtype(DTYPES[item["componentType"]])
    count, width = int(item["count"]), COMPONENTS[item["type"]]
    offset = int(view.get("byteOffset", 0)) + int(item.get("byteOffset", 0))
    stride = int(view.get("byteStride", width * dtype.itemsize))
    return np.ndarray((count, width), dtype=dtype, buffer=binary,
                      offset=offset, strides=(stride, dtype.itemsize)).copy()


def node_transform(node):
    if "matrix" in node:
        return np.asarray(node["matrix"], dtype=float).reshape(4, 4).T
    q = np.asarray(node.get("rotation", [0, 0, 0, 1]), dtype=float)
    norm = np.linalg.norm(q)
    if norm == 0:
        raise ValueError("Zero rotation quaternion")
    x, y, z, w = q / norm
    rotation = np.array([
        [1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
        [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
        [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)],
    ])
    matrix = np.eye(4)
    matrix[:3, :3] = rotation @ np.diag(node.get("scale", [1, 1, 1]))
    matrix[:3, 3] = node.get("translation", [0, 0, 0])
    return matrix


def glb_triangles(path):
    document, binary = load_glb(path)
    parts = []

    def visit(index, parent, ancestors):
        if index in ancestors:
            raise ValueError("Cyclic scene graph")
        node = document["nodes"][index]
        if "skin" in node:
            raise ValueError("Skinned geometry is not supported")
        transform = parent @ node_transform(node)
        if "mesh" in node:
            for primitive in document["meshes"][node["mesh"]]["primitives"]:
                if primitive.get("mode", 4) != 4 or primitive.get("targets"):
                    raise ValueError("Expected static TRIANGLES primitives")
                if primitive.get("extensions"):
                    raise ValueError("Compressed/extended primitives are not supported")
                points = accessor(document, binary, primitive["attributes"]["POSITION"])
                points = np.column_stack((points, np.ones(len(points)))) @ transform.T
                points = points[:, [0, 2, 1]]
                points[:, 1] *= -1
                if "indices" in primitive:
                    indices = accessor(document, binary, primitive["indices"]).reshape(-1)
                else:
                    indices = np.arange(len(points))
                if len(indices) % 3 or np.any(indices < 0) or np.any(indices >= len(points)):
                    raise ValueError("Invalid triangle indices")
                parts.append(points[indices.reshape(-1, 3)])
        for child in node.get("children", []):
            visit(child, transform, ancestors | {index})

    for root in document["scenes"][document.get("scene", 0)]["nodes"]:
        visit(root, np.eye(4), set())
    if not parts:
        raise ValueError(f"No triangles in {path}")
    triangles = np.concatenate(parts)
    if not np.isfinite(triangles).all():
        raise ValueError("Non-finite geometry")
    return triangles


def obj_triangles(path):
    points, faces = [], []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("v "):
            points.append([float(v) for v in line.split()[1:4]])
        elif line.startswith("f "):
            corners = [int(part.split("/")[0]) for part in line.split()[1:]]
            corners = [c-1 if c > 0 else len(points)+c for c in corners]
            for index in range(1, len(corners)-1):
                faces.append((corners[0], corners[index], corners[index+1]))
    if not faces:
        return np.zeros((0, 3, 3))
    return np.asarray(points, dtype=float)[np.asarray(faces, dtype=int)]


def glb_bounds(path):
    with Path(path).open("rb") as stream:
        magic, version, _ = struct.unpack("<4sII", stream.read(12))
        if magic != b"glTF" or version != 2:
            raise ValueError("Invalid GLB header")
        size, kind = struct.unpack("<II", stream.read(8))
        if kind != 0x4E4F534A:
            raise ValueError("Expected JSON as first GLB chunk")
        document = json.loads(stream.read(size).decode().rstrip("\x00 \t\n\r"))
    corners = []

    def visit(index, parent):
        node = document["nodes"][index]
        transform = parent @ node_transform(node)
        if "mesh" in node:
            for primitive in document["meshes"][node["mesh"]]["primitives"]:
                item = document["accessors"][primitive["attributes"]["POSITION"]]
                lower, upper = item["min"], item["max"]
                box_corners = np.array([[x, y, z, 1] for x in (lower[0], upper[0])
                                        for y in (lower[1], upper[1]) for z in (lower[2], upper[2])])
                points = (box_corners @ transform.T)[:, [0, 2, 1]]
                points[:, 1] *= -1
                corners.append(points)
        for child in node.get("children", []):
            visit(child, transform)

    for root in document["scenes"][document.get("scene", 0)]["nodes"]:
        visit(root, np.eye(4))
    points = np.concatenate(corners)
    return points.min(0), points.max(0)


def horizontal_triangles(triangles, min_normal_z=0.95):
    normals = np.cross(triangles[:, 1] - triangles[:, 0],
                       triangles[:, 2] - triangles[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    return triangles[(lengths > 1e-12) & (np.abs(normals[:, 2]) >= min_normal_z * lengths)]


def floor_footprint(triangles):
    horizontal = horizontal_triangles(triangles)
    polygons = [Polygon(triangle[:, :2]) for triangle in horizontal]
    polygons = [polygon for polygon in polygons if polygon.area > 1e-12]
    if not polygons:
        raise ValueError("No near-horizontal floor triangles")
    footprint = unary_union(polygons)
    if footprint.is_empty or not footprint.is_valid or footprint.area <= 1e-10:
        raise ValueError("Invalid floor footprint")
    return footprint, horizontal


def triangle_samples(triangles, spacing):
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    edge_one, edge_two = b - a, c - a
    area = 0.5 * np.linalg.norm(np.cross(edge_one, edge_two), axis=1)
    steps = np.maximum(2, np.ceil(np.sqrt(area * 4.0) / spacing).astype(int) + 1)
    points = [triangles.reshape(-1, 3)]
    for count in np.unique(steps):
        chosen = steps == count
        grid = [(i / count, j / count) for i in range(count + 1)
                for j in range(count + 1 - i)]
        weights = np.asarray(grid, dtype=float)
        points.append((a[chosen][:, None, :]
                       + weights[None, :, 0, None] * edge_one[chosen][:, None, :]
                       + weights[None, :, 1, None] * edge_two[chosen][:, None, :]
                       ).reshape(-1, 3))
    return np.concatenate(points, axis=0)
