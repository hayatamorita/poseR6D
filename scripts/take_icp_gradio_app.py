#!/usr/bin/env python3
"""Gradio MVP for CAD-A depth ICP and CAD-B same-view rendering."""

from __future__ import annotations

import argparse
import importlib
import json
import math
import os
import signal
import subprocess
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any


os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

REQUIRED_PACKAGES = {
    "numpy": "numpy",
    "trimesh": "trimesh",
    "open3d": "open3d",
    "pyrender": "pyrender",
    "PIL": "Pillow",
    "gradio": "gradio",
    "plotly": "plotly",
}


def require_module(import_name: str):
    try:
        return importlib.import_module(import_name)
    except ImportError as exc:
        package = REQUIRED_PACKAGES.get(import_name, import_name)
        raise RuntimeError(
            f"Missing or unusable dependency '{package}': {exc}"
        ) from exc


def np():
    return require_module("numpy")


def append_log(logs: list[str], message: str) -> None:
    logs.append(message)


def format_exception(exc: BaseException) -> str:
    return "".join(traceback.format_exception_only(type(exc), exc)).strip()


@dataclass
class PipelineResult:
    image: Any
    depth_image: Any
    pose_json: str
    score_json: str
    log: str


def matrix_to_list(T):
    return np().asarray(T, dtype=float).round(8).tolist()


def pointcloud_bounds(pcd):
    n = np()
    points = n.asarray(pcd.points)
    if len(points) == 0:
        return None
    return {
        "min": points.min(axis=0).round(6).tolist(),
        "max": points.max(axis=0).round(6).tolist(),
    }


def create_camera_intrinsics(fx: float, fy: float, cx: float, cy: float):
    n = np()
    return n.array([[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]], dtype=float)


def normalize_vector(vec, eps: float = 1e-12):
    n = np()
    length = n.linalg.norm(vec)
    if length < eps:
        raise ValueError("Cannot normalize near-zero vector.")
    return vec / length


def invert_pose(T):
    n = np()
    T = n.asarray(T, dtype=float)
    if T.shape != (4, 4):
        raise ValueError(f"Pose must be 4x4, got {T.shape}.")
    R = T[:3, :3]
    t = T[:3, 3]
    T_inv = n.eye(4)
    T_inv[:3, :3] = R.T
    T_inv[:3, 3] = -R.T @ t
    return T_inv


def rotation_about_axis(axis, angle_rad: float):
    n = np()
    axis = normalize_vector(n.asarray(axis, dtype=float))
    x, y, z = axis
    c = math.cos(angle_rad)
    s = math.sin(angle_rad)
    C = 1.0 - c
    return n.array(
        [
            [c + x * x * C, x * y * C - z * s, x * z * C + y * s],
            [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
            [z * x * C - y * s, z * y * C + x * s, c + z * z * C],
        ],
        dtype=float,
    )


def create_camera_pose_from_view_params(
    azimuth: float,
    elevation: float,
    roll: float,
    distance: float,
    target: tuple[float, float, float],
):
    """Return T_A_C. OpenCV camera axes: +X right, +Y down, +Z forward."""
    n = np()
    if distance <= 0:
        raise ValueError("distance must be positive.")

    az = math.radians(azimuth)
    el = math.radians(elevation)
    camera_position = n.array(
        [
            distance * math.cos(el) * math.sin(az),
            -distance * math.sin(el),
            distance * math.cos(el) * math.cos(az),
        ],
        dtype=float,
    )
    target_vec = n.asarray(target, dtype=float)
    camera_position = camera_position + target_vec

    z_axis = normalize_vector(target_vec - camera_position)
    world_up = n.array([0.0, 1.0, 0.0], dtype=float)
    if abs(float(n.dot(z_axis, world_up))) > 0.98:
        world_up = n.array([1.0, 0.0, 0.0], dtype=float)
    x_axis = normalize_vector(n.cross(z_axis, world_up))
    y_axis = normalize_vector(n.cross(z_axis, x_axis))

    if roll:
        R_roll = rotation_about_axis(z_axis, math.radians(roll))
        x_axis = R_roll @ x_axis
        y_axis = R_roll @ y_axis

    T_A_C = n.eye(4)
    T_A_C[:3, :3] = n.column_stack([x_axis, y_axis, z_axis])
    T_A_C[:3, 3] = camera_position
    return T_A_C


def create_camera_pose_from_eye_target_up(eye, target, up):
    """Return T_A_C from explicit object-space camera eye, target, and up."""
    n = np()
    eye = n.asarray(eye, dtype=float)
    target = n.asarray(target, dtype=float)
    up = n.asarray(up, dtype=float)
    z_axis = normalize_vector(target - eye)
    x_axis = normalize_vector(n.cross(z_axis, up))
    y_axis = normalize_vector(n.cross(z_axis, x_axis))
    T_A_C = n.eye(4)
    T_A_C[:3, :3] = n.column_stack([x_axis, y_axis, z_axis])
    T_A_C[:3, 3] = eye
    return T_A_C


def mesh_bounds(mesh):
    n = np()
    vertices = n.asarray(mesh.vertices, dtype=float)
    min_xyz = vertices.min(axis=0)
    max_xyz = vertices.max(axis=0)
    center = (min_xyz + max_xyz) * 0.5
    radius = float(n.linalg.norm(max_xyz - min_xyz) * 0.5)
    return min_xyz, max_xyz, center, max(radius, 1e-6)


def create_camera_pose_from_plotly_view(view_state_json: str | None, mesh, fallback_pose):
    n = np()
    if not view_state_json or not str(view_state_json).strip():
        return fallback_pose, "fallback numeric camera: empty preview view state"
    try:
        state = json.loads(view_state_json)
        camera = state.get("camera", state)
        eye_raw = camera.get("eye") or {}
        up_raw = camera.get("up") or {}
        center_raw = camera.get("center") or {}
        eye_vec = n.array(
            [
                float(eye_raw.get("x", 1.25)),
                float(eye_raw.get("y", 1.25)),
                float(eye_raw.get("z", 1.25)),
            ],
            dtype=float,
        )
        up_vec = n.array(
            [
                float(up_raw.get("x", 0.0)),
                float(up_raw.get("y", 0.0)),
                float(up_raw.get("z", 1.0)),
            ],
            dtype=float,
        )
        center_offset = n.array(
            [
                float(center_raw.get("x", 0.0)),
                float(center_raw.get("y", 0.0)),
                float(center_raw.get("z", 0.0)),
            ],
            dtype=float,
        )
        _, _, bbox_center, bbox_radius = mesh_bounds(mesh)
        target = bbox_center + center_offset * bbox_radius
        eye = target + eye_vec * bbox_radius
        return (
            create_camera_pose_from_eye_target_up(eye, target, up_vec),
            "preview camera: "
            f"source={state.get('source', 'unknown')} "
            f"eye={eye_vec.round(4).tolist()} "
            f"up={up_vec.round(4).tolist()} "
            f"center={center_offset.round(4).tolist()}",
        )
    except Exception as exc:
        return fallback_pose, f"fallback numeric camera: invalid preview view state ({format_exception(exc)})"


def opencv_to_opengl_camera_pose(T_object_camera):
    """Convert camera pose from OpenCV axes to OpenGL/pyrender camera axes."""
    n = np()
    cv_to_gl = n.eye(4)
    cv_to_gl[:3, :3] = n.diag([1.0, -1.0, -1.0])
    return n.asarray(T_object_camera, dtype=float) @ cv_to_gl


def parse_matrix4x4(text: str | None):
    n = np()
    if not text or not text.strip():
        return n.eye(4)
    data = json.loads(text)
    matrix = n.asarray(data, dtype=float)
    if matrix.shape != (4, 4):
        raise ValueError(f"T_BA must be 4x4, got {matrix.shape}.")
    return matrix


def ensure_trimesh_mesh(mesh_or_scene):
    trimesh = require_module("trimesh")
    if isinstance(mesh_or_scene, trimesh.Scene):
        meshes = [geom for geom in mesh_or_scene.geometry.values() if hasattr(geom, "vertices")]
        if not meshes:
            raise ValueError("Scene has no mesh geometry.")
        return trimesh.util.concatenate(meshes)
    return mesh_or_scene


def _read_vtk_header_lines(blob: bytes):
    lines: list[bytes] = []
    pos = 0
    for _ in range(16):
        end = blob.find(b"\n", pos)
        if end < 0:
            break
        line = blob[pos:end].strip()
        lines.append(line)
        pos = end + 1
        if line.startswith(b"POINTS "):
            return lines, pos
    raise ValueError("VTK POINTS header was not found.")


def _vtk_int_dtype(type_name: bytes):
    n = np()
    normalized = type_name.lower()
    if normalized in {b"vtktypeint64", b"long", b"long_long"}:
        return n.dtype(">i8")
    if normalized in {b"int", b"vtktypeint32"}:
        return n.dtype(">i4")
    raise ValueError(f"Unsupported VTK integer type: {type_name.decode(errors='replace')}")


def _triangulate_cells(cells):
    faces: list[list[int]] = []
    for cell in cells:
        if len(cell) == 3:
            faces.append([int(cell[0]), int(cell[1]), int(cell[2])])
        elif len(cell) > 3:
            first = int(cell[0])
            for i in range(1, len(cell) - 1):
                faces.append([first, int(cell[i]), int(cell[i + 1])])
    if not faces:
        raise ValueError("VTK file did not contain polygonal cells.")
    return faces


def _load_ascii_vtk_mesh(text: str):
    n = np()
    trimesh = require_module("trimesh")
    tokens = text.split()
    try:
        points_idx = tokens.index("POINTS")
    except ValueError as exc:
        raise ValueError("ASCII VTK POINTS section was not found.") from exc

    point_count = int(tokens[points_idx + 1])
    point_start = points_idx + 3
    point_end = point_start + point_count * 3
    vertices = n.asarray(tokens[point_start:point_end], dtype=float).reshape((-1, 3))

    section_name = None
    section_idx = -1
    for candidate in ("POLYGONS", "CELLS"):
        if candidate in tokens:
            section_name = candidate
            section_idx = tokens.index(candidate)
            break
    if section_name is None:
        raise ValueError("ASCII VTK POLYGONS/CELLS section was not found.")

    cell_count = int(tokens[section_idx + 1])
    cursor = section_idx + 3
    cells = []
    for _ in range(cell_count):
        width = int(tokens[cursor])
        cursor += 1
        cells.append([int(v) for v in tokens[cursor : cursor + width]])
        cursor += width

    faces = _triangulate_cells(cells)
    return trimesh.Trimesh(vertices=vertices, faces=n.asarray(faces, dtype=n.int64), process=False)


def _load_binary_vtk_mesh(blob: bytes):
    n = np()
    trimesh = require_module("trimesh")
    lines, data_start = _read_vtk_header_lines(blob)
    points_line = lines[-1].split()
    point_count = int(points_line[1])
    point_type = points_line[2].lower()
    if point_type == b"float":
        point_dtype = n.dtype(">f4")
    elif point_type == b"double":
        point_dtype = n.dtype(">f8")
    else:
        raise ValueError(f"Unsupported VTK point type: {point_type.decode(errors='replace')}")

    point_values = n.frombuffer(blob, dtype=point_dtype, count=point_count * 3, offset=data_start)
    vertices = point_values.astype(float).reshape((-1, 3))
    cursor = data_start + point_values.nbytes
    while cursor < len(blob) and blob[cursor] in b"\r\n\t ":
        cursor += 1

    polygon_pos = blob.find(b"POLYGONS", cursor)
    if polygon_pos < 0:
        raise ValueError("Binary VTK POLYGONS section was not found.")
    line_end = blob.find(b"\n", polygon_pos)
    polygon_parts = blob[polygon_pos:line_end].split()
    polygon_count = int(polygon_parts[1])
    legacy_size = int(polygon_parts[2])
    cursor = line_end + 1

    next_line_end = blob.find(b"\n", cursor)
    next_line = blob[cursor:next_line_end].split()
    cells = []
    if next_line and next_line[0] == b"OFFSETS":
        offset_dtype = _vtk_int_dtype(next_line[1])
        cursor = next_line_end + 1
        connectivity_header_pos = blob.find(b"CONNECTIVITY", cursor)
        if connectivity_header_pos < 0:
            raise ValueError("Binary VTK CONNECTIVITY section was not found.")
        offset_count = (connectivity_header_pos - cursor)
        while offset_count > 0 and blob[cursor + offset_count - 1] in b"\r\n\t ":
            offset_count -= 1
        offsets = n.frombuffer(blob, dtype=offset_dtype, count=offset_count // offset_dtype.itemsize, offset=cursor).astype(n.int64)
        if len(offsets) not in {polygon_count, polygon_count + 1}:
            raise ValueError(f"Unexpected VTK offset count: {len(offsets)} for {polygon_count} polygons.")
        cursor += offsets.nbytes
        while cursor < len(blob) and blob[cursor] in b"\r\n\t ":
            cursor += 1
        conn_line_end = blob.find(b"\n", cursor)
        conn_line = blob[cursor:conn_line_end].split()
        if not conn_line or conn_line[0] != b"CONNECTIVITY":
            raise ValueError("Binary VTK CONNECTIVITY section was not found.")
        conn_dtype = _vtk_int_dtype(conn_line[1])
        cursor = conn_line_end + 1
        connectivity_count = legacy_size if len(offsets) == polygon_count else int(offsets[-1])
        connectivity = n.frombuffer(blob, dtype=conn_dtype, count=connectivity_count, offset=cursor).astype(n.int64)
        if len(offsets) == polygon_count:
            ends = n.concatenate([offsets[1:], n.array([connectivity_count], dtype=n.int64)])
        else:
            ends = offsets[1:]
            offsets = offsets[:-1]
        widths = ends - offsets
        if n.all(widths == 3):
            faces = connectivity.reshape((-1, 3))
            return trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
        for i in range(polygon_count):
            cells.append(connectivity[offsets[i] : ends[i]])
    else:
        values = n.frombuffer(blob, dtype=n.dtype(">i4"), count=legacy_size, offset=cursor).astype(n.int64)
        i = 0
        for _ in range(polygon_count):
            width = int(values[i])
            i += 1
            cells.append(values[i : i + width])
            i += width

    faces = _triangulate_cells(cells)
    return trimesh.Trimesh(vertices=vertices, faces=n.asarray(faces, dtype=n.int64), process=False)


def load_legacy_vtk_mesh(path: Path):
    blob = path.read_bytes()
    header = blob[:256].upper()
    if b"BINARY" in header:
        return _load_binary_vtk_mesh(blob)
    return _load_ascii_vtk_mesh(blob.decode("utf-8", errors="replace"))


def load_mesh(path: str | Path):
    n = np()
    trimesh = require_module("trimesh")
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(str(path))

    if path.suffix.lower() == ".vtk":
        try:
            return load_legacy_vtk_mesh(path)
        except Exception:
            pass

    try:
        mesh = ensure_trimesh_mesh(trimesh.load(path, force="mesh", process=False))
        if len(mesh.vertices) > 0 and len(mesh.faces) > 0:
            return mesh
    except Exception:
        pass

    open3d = require_module("open3d")
    o3d_mesh = open3d.io.read_triangle_mesh(str(path))
    if not o3d_mesh.has_vertices() or not o3d_mesh.has_triangles():
        raise ValueError(f"Could not load triangle mesh: {path}")
    vertices = n.asarray(o3d_mesh.vertices)
    faces = n.asarray(o3d_mesh.triangles)
    return trimesh.Trimesh(vertices=vertices, faces=faces, process=False)


def mesh_to_plotly_edge_trace(vertices, faces, max_edge_faces: int = 2500):
    n = np()
    graph_objects = require_module("plotly.graph_objects")
    if len(faces) > max_edge_faces:
        idx = n.linspace(0, len(faces) - 1, int(max_edge_faces), dtype=n.int64)
        edge_faces = faces[idx]
    else:
        edge_faces = faces

    xs: list[float | None] = []
    ys: list[float | None] = []
    zs: list[float | None] = []
    for tri in edge_faces:
        pts = vertices[tri]
        for a, b in ((0, 1), (1, 2), (2, 0)):
            xs.extend([float(pts[a, 0]), float(pts[b, 0]), None])
            ys.extend([float(pts[a, 1]), float(pts[b, 1]), None])
            zs.extend([float(pts[a, 2]), float(pts[b, 2]), None])
    return graph_objects.Scatter3d(
        x=xs,
        y=ys,
        z=zs,
        mode="lines",
        line={"color": "rgba(22, 30, 46, 0.23)", "width": 1},
        hoverinfo="skip",
        showlegend=False,
    )


def mesh_to_plotly_figure(mesh):
    n = np()
    graph_objects = require_module("plotly.graph_objects")
    vertices = n.asarray(mesh.vertices, dtype=float)
    faces = n.asarray(mesh.faces, dtype=n.int64)
    min_xyz, max_xyz, center, radius = mesh_bounds(mesh)
    mesh_trace = graph_objects.Mesh3d(
        x=vertices[:, 0],
        y=vertices[:, 1],
        z=vertices[:, 2],
        i=faces[:, 0],
        j=faces[:, 1],
        k=faces[:, 2],
        color="#b8c0cc",
        opacity=1.0,
        flatshading=False,
        lighting={
            "ambient": 0.42,
            "diffuse": 0.82,
            "specular": 0.28,
            "roughness": 0.55,
            "fresnel": 0.12,
        },
        lightposition={"x": 80, "y": -120, "z": 160},
        hoverinfo="skip",
        showlegend=False,
    )
    fig = graph_objects.Figure(data=[mesh_trace])
    fig.update_layout(
        paper_bgcolor="#f5f7fa",
        plot_bgcolor="#f5f7fa",
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        scene={
            "aspectmode": "data",
            "bgcolor": "#f5f7fa",
            "xaxis": {
                "visible": False,
                "showbackground": False,
                "range": [float(min_xyz[0]), float(max_xyz[0])],
            },
            "yaxis": {
                "visible": False,
                "showbackground": False,
                "range": [float(min_xyz[1]), float(max_xyz[1])],
            },
            "zaxis": {
                "visible": False,
                "showbackground": False,
                "range": [float(min_xyz[2]), float(max_xyz[2])],
            },
            "camera": {
                "eye": {"x": 1.4, "y": 1.4, "z": 1.1},
                "up": {"x": 0.0, "y": 0.0, "z": 1.0},
                "center": {"x": 0.0, "y": 0.0, "z": 0.0},
            },
        },
        uirevision="cad-a-preview",
        height=520,
    )
    fig.update_layout(meta={"bbox_center": center.tolist(), "bbox_radius": radius})
    return fig


def update_cad_a_preview(cad_a_file):
    path = _file_path(cad_a_file)
    if not path:
        return None, "CAD-Aをアップロードしてください。"
    try:
        mesh = load_mesh(path)
        fig = mesh_to_plotly_figure(mesh)
        return fig, f"CAD-A preview loaded: vertices={len(mesh.vertices)} faces={len(mesh.faces)}"
    except Exception as exc:
        return None, format_exception(exc)


def mesh_to_pointcloud(mesh, n_points: int = 20000):
    n = np()
    open3d = require_module("open3d")
    if n_points < 10:
        raise ValueError("n_points must be at least 10.")
    points, _ = mesh.sample(n_points, return_index=True)
    pcd = open3d.geometry.PointCloud()
    pcd.points = open3d.utility.Vector3dVector(n.asarray(points, dtype=float))
    return pcd


def trimesh_to_pyrender_mesh(mesh):
    pyrender = require_module("pyrender")
    return pyrender.Mesh.from_trimesh(mesh, smooth=False)


def _build_pyrender_scene(mesh, T_object_camera, K, width: int, height: int):
    pyrender = require_module("pyrender")
    scene = pyrender.Scene(bg_color=[0.0, 0.0, 0.0, 0.0], ambient_light=[0.25, 0.25, 0.25])
    scene.add(trimesh_to_pyrender_mesh(mesh), pose=np().eye(4))
    camera = pyrender.IntrinsicsCamera(
        fx=float(K[0, 0]),
        fy=float(K[1, 1]),
        cx=float(K[0, 2]),
        cy=float(K[1, 2]),
        znear=0.001,
        zfar=10000.0,
    )
    camera_pose = opencv_to_opengl_camera_pose(T_object_camera)
    scene.add(camera, pose=camera_pose)
    scene.add(pyrender.DirectionalLight(color=[1.0, 1.0, 1.0], intensity=3.0), pose=camera_pose)
    return scene


def render_depth(mesh, T_object_camera, K, width: int, height: int):
    try:
        pyrender = require_module("pyrender")
        scene = _build_pyrender_scene(mesh, T_object_camera, K, width, height)
        renderer = pyrender.OffscreenRenderer(viewport_width=int(width), viewport_height=int(height))
        try:
            _, depth = renderer.render(scene)
        finally:
            renderer.delete()
        return depth
    except Exception:
        depth, _ = render_open3d_raycast(mesh, T_object_camera, K, width, height)
        return depth


def render_rgb(mesh, T_object_camera, K, width: int, height: int):
    try:
        pyrender = require_module("pyrender")
        scene = _build_pyrender_scene(mesh, T_object_camera, K, width, height)
        renderer = pyrender.OffscreenRenderer(viewport_width=int(width), viewport_height=int(height))
        try:
            color, _ = renderer.render(scene)
        finally:
            renderer.delete()
        return color
    except Exception:
        _, color = render_open3d_raycast(mesh, T_object_camera, K, width, height)
        return color


def trimesh_to_open3d_legacy(mesh):
    n = np()
    open3d = require_module("open3d")
    o3d_mesh = open3d.geometry.TriangleMesh()
    o3d_mesh.vertices = open3d.utility.Vector3dVector(n.asarray(mesh.vertices, dtype=float))
    o3d_mesh.triangles = open3d.utility.Vector3iVector(n.asarray(mesh.faces, dtype=n.int32))
    o3d_mesh.compute_vertex_normals()
    return o3d_mesh


def render_open3d_raycast(mesh, T_object_camera, K, width: int, height: int):
    n = np()
    open3d = require_module("open3d")
    legacy_mesh = trimesh_to_open3d_legacy(mesh)
    tensor_mesh = open3d.t.geometry.TriangleMesh.from_legacy(legacy_mesh)
    scene = open3d.t.geometry.RaycastingScene()
    scene.add_triangles(tensor_mesh)

    intrinsic = open3d.core.Tensor(n.asarray(K, dtype=n.float32))
    extrinsic = open3d.core.Tensor(invert_pose(T_object_camera).astype(n.float32))
    rays = open3d.t.geometry.RaycastingScene.create_rays_pinhole(
        intrinsic, extrinsic, int(width), int(height)
    )
    ans = scene.cast_rays(rays)
    t_hit = ans["t_hit"].numpy()
    valid = n.isfinite(t_hit)
    rays_np = rays.numpy()
    hit_points = rays_np[..., :3] + rays_np[..., 3:] * n.where(valid, t_hit, 0.0)[..., None]
    hit_points_h = n.concatenate([hit_points.reshape(-1, 3), n.ones((hit_points.size // 3, 1))], axis=1)
    z = (invert_pose(T_object_camera) @ hit_points_h.T).T[:, 2].reshape(int(height), int(width))
    depth = n.where(valid, z, 0.0).astype(n.float32)

    color = n.zeros((int(height), int(width), 3), dtype=n.uint8)
    if "primitive_normals" in ans:
        normals = ans["primitive_normals"].numpy()
        shaded = ((normals + 1.0) * 0.5 * 255.0).clip(0, 255).astype(n.uint8)
        color[valid] = shaded[valid]
    elif valid.any():
        finite_depth = depth[valid]
        denom = max(float(finite_depth.max() - finite_depth.min()), 1e-9)
        gray = ((1.0 - (depth - finite_depth.min()) / denom) * 255.0).clip(0, 255).astype(n.uint8)
        color[valid] = n.repeat(gray[..., None], 3, axis=2)[valid]
    return depth, color


def depth_to_display_image(depth):
    n = np()
    depth = n.asarray(depth, dtype=float)
    valid = n.isfinite(depth) & (depth > 0.0)
    image = n.zeros(depth.shape + (3,), dtype=n.uint8)
    if not valid.any():
        return image
    values = depth[valid]
    near = float(n.percentile(values, 2.0))
    far = float(n.percentile(values, 98.0))
    if far <= near:
        far = float(values.max())
        near = float(values.min())
    denom = max(far - near, 1e-9)
    normalized = (1.0 - (depth - near) / denom).clip(0.0, 1.0)
    gray = (normalized * 255.0).astype(n.uint8)
    image[valid] = n.repeat(gray[..., None], 3, axis=2)[valid]
    return image


def depth_to_pointcloud(depth, K, depth_scale: float = 1.0):
    n = np()
    open3d = require_module("open3d")
    depth = n.asarray(depth, dtype=float) * float(depth_scale)
    valid = n.isfinite(depth) & (depth > 0.0)
    if int(valid.sum()) < 10:
        raise ValueError("Depth has too few valid pixels.")
    v, u = n.nonzero(valid)
    z = depth[v, u]
    x = (u.astype(float) - float(K[0, 2])) * z / float(K[0, 0])
    y = (v.astype(float) - float(K[1, 2])) * z / float(K[1, 1])
    points = n.column_stack([x, y, z])
    pcd = open3d.geometry.PointCloud()
    pcd.points = open3d.utility.Vector3dVector(points)
    return pcd


def transform_pointcloud(pcd, T):
    n = np()
    open3d = require_module("open3d")
    transformed = open3d.geometry.PointCloud()
    transformed.points = open3d.utility.Vector3dVector(n.asarray(pcd.points).copy())
    if pcd.has_normals():
        transformed.normals = open3d.utility.Vector3dVector(n.asarray(pcd.normals).copy())
    transformed.transform(n.asarray(T, dtype=float))
    return transformed


def preprocess_pointcloud(pcd, voxel_size: float):
    open3d = require_module("open3d")
    if len(pcd.points) < 10:
        raise ValueError("Point cloud has too few points.")
    processed = pcd
    if voxel_size > 0:
        processed = processed.voxel_down_sample(float(voxel_size))
    if len(processed.points) >= 50:
        processed, _ = processed.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)
    if len(processed.points) < 10:
        raise ValueError("Point cloud became too small after preprocessing.")
    radius = max(float(voxel_size) * 3.0, 1e-3)
    processed.estimate_normals(
        search_param=open3d.geometry.KDTreeSearchParamHybrid(radius=radius, max_nn=30)
    )
    return processed


def run_point_to_plane_icp(source_pcd, target_pcd, max_distance: float, max_iteration: int):
    n = np()
    open3d = require_module("open3d")
    if not target_pcd.has_normals():
        raise ValueError("Target point cloud needs normals for point-to-plane ICP.")
    result = open3d.pipelines.registration.registration_icp(
        source_pcd,
        target_pcd,
        float(max_distance),
        n.eye(4),
        open3d.pipelines.registration.TransformationEstimationPointToPlane(),
        open3d.pipelines.registration.ICPConvergenceCriteria(max_iteration=int(max_iteration)),
    )
    return result.transformation, float(result.fitness), float(result.inlier_rmse)


def transfer_pose_to_cad_b(T_A_C, T_BA, scale: float = 1.0):
    n = np()
    T_B_C = n.asarray(T_BA, dtype=float) @ n.asarray(T_A_C, dtype=float)
    if scale <= 0:
        raise ValueError("scale must be positive.")
    T_B_C = T_B_C.copy()
    T_B_C[:3, 3] = T_B_C[:3, 3] / float(scale)
    return T_B_C


def create_small_translation(dx: float, dy: float, dz: float):
    n = np()
    T = n.eye(4)
    T[:3, 3] = [float(dx), float(dy), float(dz)]
    return T


def _file_path(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (str, Path)):
        return str(value)
    if hasattr(value, "name"):
        return str(value.name)
    if isinstance(value, dict) and value.get("name"):
        return str(value["name"])
    return None


def _json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def run_pipeline(
    cad_a_file,
    cad_b_file,
    width: int,
    height: int,
    fx: float,
    fy: float,
    cx: float,
    cy: float,
    azimuth: float,
    elevation: float,
    roll: float,
    distance: float,
    target_x: float,
    target_y: float,
    target_z: float,
    depth_scale: float,
    voxel_size: float,
    max_correspondence_distance: float,
    max_iteration: int,
    n_points: int,
    t_ba_json: str,
    scale: float,
    perturb_x: float,
    perturb_y: float,
    perturb_z: float,
    preview_view_json: str = "",
) -> PipelineResult:
    logs: list[str] = []
    try:
        cad_a_path = _file_path(cad_a_file)
        cad_b_path = _file_path(cad_b_file)
        if not cad_a_path:
            raise ValueError("CAD-A file is required.")
        if not cad_b_path:
            raise ValueError("CAD-B file is required.")
        if int(width) <= 0 or int(height) <= 0:
            raise ValueError("width and height must be positive.")

        append_log(logs, f"PYOPENGL_PLATFORM={os.environ.get('PYOPENGL_PLATFORM', '')}")
        K = create_camera_intrinsics(float(fx), float(fy), float(cx), float(cy))
        fallback_T_A_C = create_camera_pose_from_view_params(
            float(azimuth),
            float(elevation),
            float(roll),
            float(distance),
            (float(target_x), float(target_y), float(target_z)),
        )
        T_BA = parse_matrix4x4(t_ba_json)
        append_log(logs, "camera intrinsics created")

        mesh_a = load_mesh(cad_a_path)
        mesh_b = load_mesh(cad_b_path)
        append_log(logs, f"CAD-A vertices={len(mesh_a.vertices)} faces={len(mesh_a.faces)}")
        append_log(logs, f"CAD-B vertices={len(mesh_b.vertices)} faces={len(mesh_b.faces)}")
        T_A_C_initial, view_message = create_camera_pose_from_plotly_view(
            preview_view_json, mesh_a, fallback_T_A_C
        )
        append_log(logs, view_message)

        depth = render_depth(mesh_a, T_A_C_initial, K, int(width), int(height))
        valid_depth = int((np().asarray(depth) > 0).sum())
        if valid_depth < 10:
            raise ValueError("Rendered depth has too few valid pixels. Check camera distance and target.")
        append_log(logs, f"rendered depth valid pixels={valid_depth}")
        depth_image = depth_to_display_image(depth)

        P_obs_C = depth_to_pointcloud(depth, K, float(depth_scale))
        P_obs_A = transform_pointcloud(P_obs_C, T_A_C_initial)
        if any(abs(v) > 0 for v in (perturb_x, perturb_y, perturb_z)):
            T_perturb = create_small_translation(float(perturb_x), float(perturb_y), float(perturb_z))
            P_obs_A = transform_pointcloud(P_obs_A, T_perturb)
            append_log(logs, f"applied observed-point perturbation: {[perturb_x, perturb_y, perturb_z]}")
        append_log(logs, f"P_obs_A points={len(P_obs_A.points)} bounds={pointcloud_bounds(P_obs_A)}")

        P_cad_A = mesh_to_pointcloud(mesh_a, int(n_points))
        source = preprocess_pointcloud(P_obs_A, float(voxel_size))
        target = preprocess_pointcloud(P_cad_A, float(voxel_size))
        append_log(logs, f"source points after preprocess={len(source.points)}")
        append_log(logs, f"target points after preprocess={len(target.points)}")

        T_A_Aobs, fitness, rmse = run_point_to_plane_icp(
            source, target, float(max_correspondence_distance), int(max_iteration)
        )
        T_A_C_refined = T_A_Aobs @ T_A_C_initial
        T_B_C = transfer_pose_to_cad_b(T_A_C_refined, T_BA, float(scale))
        append_log(logs, f"ICP fitness={fitness:.6f} inlier_rmse={rmse:.6f}")

        image = render_rgb(mesh_b, T_B_C, K, int(width), int(height))
        pose = {
            "T_A_C_initial": matrix_to_list(T_A_C_initial),
            "T_A_Aobs_icp": matrix_to_list(T_A_Aobs),
            "T_A_C_refined": matrix_to_list(T_A_C_refined),
            "T_BA": matrix_to_list(T_BA),
            "T_B_C": matrix_to_list(T_B_C),
            "K": matrix_to_list(K),
        }
        scores = {
            "fitness": fitness,
            "inlier_rmse": rmse,
            "valid_depth_pixels": valid_depth,
            "source_points": len(source.points),
            "target_points": len(target.points),
        }
        return PipelineResult(
            image=image,
            depth_image=depth_image,
            pose_json=_json_dumps(pose),
            score_json=_json_dumps(scores),
            log="\n".join(logs),
        )
    except Exception as exc:
        append_log(logs, format_exception(exc))
        return PipelineResult(image=None, depth_image=None, pose_json="{}", score_json="{}", log="\n".join(logs))


def run_self_test(mesh_path: str | None = None) -> int:
    n = np()
    logs: list[str] = []
    K = create_camera_intrinsics(500.0, 500.0, 320.0, 240.0)
    T = create_camera_pose_from_view_params(30.0, 20.0, 0.0, 2.0, (0.0, 0.0, 0.0))
    T_inv = invert_pose(T)
    identity_error = float(n.max(n.abs(T @ T_inv - n.eye(4))))
    if identity_error > 1e-9:
        raise AssertionError(f"Pose inverse error too large: {identity_error}")
    append_log(logs, f"K shape: {K.shape}")
    append_log(logs, f"pose inverse max error: {identity_error:.3e}")

    T_BA = parse_matrix4x4(None)
    T_B_C = T_BA @ T
    if not n.allclose(T_B_C, T):
        raise AssertionError("Identity T_BA transfer failed.")
    append_log(logs, "identity T_BA transfer: ok")

    synthetic_depth = n.ones((4, 4), dtype=float)
    synthetic_pcd = depth_to_pointcloud(synthetic_depth, create_camera_intrinsics(2.0, 2.0, 1.5, 1.5), 1.0)
    if len(synthetic_pcd.points) != 16:
        raise AssertionError(f"Unexpected synthetic depth point count: {len(synthetic_pcd.points)}")
    append_log(logs, "synthetic depth_to_pointcloud: ok")

    if mesh_path:
        mesh = load_mesh(mesh_path)
        pcd = mesh_to_pointcloud(mesh, n_points=256)
        point_count = len(pcd.points)
        if point_count != 256:
            raise AssertionError(f"Unexpected sampled point count: {point_count}")
        append_log(logs, f"mesh vertices={len(mesh.vertices)} faces={len(mesh.faces)} sampled={point_count}")

    print("\n".join(logs))
    return 0


def build_gradio_app():
    gr = require_module("gradio")
    with gr.Blocks(title="竹ICP MVP") as demo:
        gr.Markdown("# 竹ICP MVP")
        with gr.Row():
            with gr.Column():
                cad_a_file = gr.File(label="CAD-A")
                cad_a_plot = gr.Plot(label="CAD-A preview", elem_id="cad-a-plot")
                cad_a_depth = gr.Image(label="CAD-A depth from current preview", type="numpy")
                preview_view_json = gr.Textbox(label="Preview view state", visible=False, value="")
                with gr.Accordion("Fallback camera", open=False):
                    with gr.Row():
                        width = gr.Number(label="width", value=320, precision=0)
                        height = gr.Number(label="height", value=240, precision=0)
                    with gr.Row():
                        fx = gr.Number(label="fx", value=300.0)
                        fy = gr.Number(label="fy", value=300.0)
                        cx = gr.Number(label="cx", value=160.0)
                        cy = gr.Number(label="cy", value=120.0)
                    with gr.Row():
                        azimuth = gr.Number(label="azimuth", value=0.0)
                        elevation = gr.Number(label="elevation", value=10.0)
                        roll = gr.Number(label="roll", value=0.0)
                        distance = gr.Number(label="distance", value=3.0)
                    with gr.Row():
                        target_x = gr.Number(label="target_x", value=0.0)
                        target_y = gr.Number(label="target_y", value=0.0)
                        target_z = gr.Number(label="target_z", value=0.0)
                with gr.Accordion("ICP", open=True):
                    depth_scale = gr.Number(label="depth_scale", value=1.0)
                    voxel_size = gr.Number(label="voxel_size", value=0.02)
                    max_correspondence_distance = gr.Number(label="max_correspondence_distance", value=0.08)
                    max_iteration = gr.Number(label="max_iteration", value=40, precision=0)
                    n_points = gr.Number(label="cad sample points", value=20000, precision=0)
                with gr.Accordion("Transfer and debug", open=False):
                    t_ba_json = gr.Textbox(
                        label="T_BA JSON",
                        value="",
                        lines=5,
                        placeholder="empty means identity matrix",
                    )
                    scale = gr.Number(label="scale", value=1.0)
                    with gr.Row():
                        perturb_x = gr.Number(label="perturb_x", value=0.0)
                        perturb_y = gr.Number(label="perturb_y", value=0.0)
                        perturb_z = gr.Number(label="perturb_z", value=0.0)
                start = gr.Button("Start", variant="primary")
            with gr.Column():
                cad_b_file = gr.File(label="CAD-B")
                image = gr.Image(label="CAD-B same-view rendering", type="numpy")
                pose_json = gr.Code(label="Pose", language="json")
                score_json = gr.Code(label="ICP score", language="json")
                log = gr.Textbox(label="Log", lines=16)

        inputs = [
            cad_a_file,
            cad_b_file,
            width,
            height,
            fx,
            fy,
            cx,
            cy,
            azimuth,
            elevation,
            roll,
            distance,
            target_x,
            target_y,
            target_z,
            depth_scale,
            voxel_size,
            max_correspondence_distance,
            max_iteration,
            n_points,
            t_ba_json,
            scale,
            perturb_x,
            perturb_y,
            perturb_z,
            preview_view_json,
        ]

        def _run(*values):
            result = run_pipeline(*values)
            return result.depth_image, result.image, result.pose_json, result.score_json, result.log

        capture_preview_camera_js = """
        (...args) => {
            const plot = document.querySelector("#cad-a-plot .js-plotly-plot");
            function mergeCameraPatch(base, patch) {
                const camera = JSON.parse(JSON.stringify(base || {}));
                if (!patch) return camera;
                if (patch["scene.camera"]) {
                    return patch["scene.camera"];
                }
                for (const [key, value] of Object.entries(patch)) {
                    if (!key.startsWith("scene.camera.")) continue;
                    const parts = key.replace("scene.camera.", "").split(".");
                    let cursor = camera;
                    while (parts.length > 1) {
                        const part = parts.shift();
                        cursor[part] = cursor[part] || {};
                        cursor = cursor[part];
                    }
                    cursor[parts[0]] = value;
                }
                return camera;
            }
            function installRelayoutCapture(gd) {
                if (!gd || gd.__cadAViewCaptureInstalled || !gd.on) return;
                gd.__cadAViewCaptureInstalled = true;
                gd.on("plotly_relayout", (eventData) => {
                    const base = window.__cadAPlotlyCamera || gd.layout?.scene?.camera || gd._fullLayout?.scene?.camera || {};
                    window.__cadAPlotlyCamera = mergeCameraPatch(base, eventData);
                });
            }
            if (plot) {
                installRelayoutCapture(plot);
            }
            const camera =
                window.__cadAPlotlyCamera ||
                plot?.layout?.scene?.camera ||
                plot?._fullLayout?.scene?.camera ||
                null;
            const state = {
                source: "plotly",
                camera,
                captured_at: new Date().toISOString()
            };
            args[args.length - 1] = JSON.stringify(state);
            return args;
        }
        """

        cad_a_file.change(update_cad_a_preview, inputs=[cad_a_file], outputs=[cad_a_plot, log])
        start.click(
            _run,
            inputs=inputs,
            outputs=[cad_a_depth, image, pose_json, score_json, log],
            js=capture_preview_camera_js,
        )
    return demo


def kill_existing_listeners(port: int) -> list[int]:
    try:
        completed = subprocess.run(
            ["lsof", f"-tiTCP:{int(port)}", "-sTCP:LISTEN"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return []
    pids = []
    current_pid = os.getpid()
    for line in completed.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pid = int(line)
        except ValueError:
            continue
        if pid == current_pid:
            continue
        try:
            os.kill(pid, signal.SIGTERM)
            pids.append(pid)
        except ProcessLookupError:
            pass
    return pids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CAD-A Depth ICP to CAD-B same-view Gradio MVP.")
    parser.add_argument("--self-test", action="store_true", help="Run lightweight self tests.")
    parser.add_argument("--mesh", help="Optional mesh path for self-test loading.")
    parser.add_argument("--host", default="127.0.0.1", help="Gradio server host.")
    parser.add_argument("--port", type=int, default=7865, help="Gradio server port.")
    parser.add_argument(
        "--no-kill-existing",
        action="store_true",
        help="Do not stop an existing listener on the selected port before launch.",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test(args.mesh)

    if not args.no_kill_existing:
        killed = kill_existing_listeners(args.port)
        if killed:
            print(f"Stopped existing listener(s) on port {args.port}: {killed}")

    demo = build_gradio_app()
    demo.launch(server_name=args.host, server_port=args.port)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(format_exception(exc), file=sys.stderr)
        raise SystemExit(1)
