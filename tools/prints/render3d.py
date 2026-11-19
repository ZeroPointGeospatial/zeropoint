"""Path-traced relief rendering (Mitsuba 3) for the 3D plates.

The scene is always the same simple studio: the model sits on a large
paper-coloured floor, lit by one soft "sun" from the north-west plus an even
sky, and is photographed by an orthographic camera tilted down from the
south. Lighting is normalised so that a flat, unshadowed, white surface
renders at 1.0; colours you put on the model are the colours you get back.

World axes: x = east, y = north, z = up. Units are whatever the mesh uses.
"""
import math
import os
import tempfile
from pathlib import Path

import numpy as np

_mi = None


def mitsuba():
    global _mi
    if _mi is None:
        import mitsuba as mi
        variant = os.environ.get("ZP_MI_VARIANT")
        for v in ([variant] if variant else ["llvm_ad_rgb", "scalar_rgb"]):
            try:
                mi.set_variant(v)
                break
            except Exception:
                continue
        _mi = mi
    return _mi


# --------------------------------------------------------------------------
# meshes
# --------------------------------------------------------------------------
def write_ply(path, verts, faces, uv=None):
    """Binary little-endian PLY with optional texture coordinates."""
    verts = np.asarray(verts, dtype="<f4")
    faces = np.asarray(faces, dtype="<i4")
    vt = [("x", "<f4"), ("y", "<f4"), ("z", "<f4")]
    if uv is not None:
        vt += [("s", "<f4"), ("t", "<f4")]
    v = np.empty(len(verts), dtype=vt)
    v["x"], v["y"], v["z"] = verts[:, 0], verts[:, 1], verts[:, 2]
    if uv is not None:
        v["s"], v["t"] = uv[:, 0], uv[:, 1]
    f = np.empty(len(faces), dtype=[("n", "u1"), ("a", "<i4"), ("b", "<i4"), ("c", "<i4")])
    f["n"] = 3
    f["a"], f["b"], f["c"] = faces[:, 0], faces[:, 1], faces[:, 2]
    head = ["ply", "format binary_little_endian 1.0", f"element vertex {len(v)}",
            "property float x", "property float y", "property float z"]
    if uv is not None:
        head += ["property float s", "property float t"]
    head += [f"element face {len(f)}", "property list uchar int vertex_indices", "end_header"]
    with open(path, "wb") as fh:
        fh.write(("\n".join(head) + "\n").encode())
        v.tofile(fh)
        f.tofile(fh)


def heightfield_mesh(z, cell, valid=None, base=None):
    """Triangulate a height grid.

    z      (rows, cols) heights, row 0 = north
    cell   ground size of a cell
    valid  optional boolean grid; cells outside are cut away
    base   if given, add vertical walls from the cut edge down to this height

    Returns (surface_verts, surface_faces, uv, wall_verts, wall_faces).
    The model is centred on the origin in x and y.
    """
    nr, nc = z.shape
    xs = (np.arange(nc) - (nc - 1) / 2) * cell
    ys = ((nr - 1) / 2 - np.arange(nr)) * cell
    X, Y = np.meshgrid(xs, ys)
    verts = np.column_stack([X.ravel(), Y.ravel(), np.nan_to_num(z).ravel()]).astype("float32")
    U, V = np.meshgrid((np.arange(nc) + 0.5) / nc, (np.arange(nr) + 0.5) / nr)
    uv = np.column_stack([U.ravel(), V.ravel()]).astype("float32")

    idx = np.arange(nr * nc, dtype="int32").reshape(nr, nc)
    a, b, c, d = idx[:-1, :-1], idx[:-1, 1:], idx[1:, :-1], idx[1:, 1:]
    if valid is None:
        ok = np.ones((nr - 1, nc - 1), dtype=bool)
    else:
        ok = valid[:-1, :-1] & valid[:-1, 1:] & valid[1:, :-1] & valid[1:, 1:]
    faces = np.concatenate([
        np.column_stack([a[ok], c[ok], b[ok]]),
        np.column_stack([b[ok], c[ok], d[ok]])]).astype("int32")

    wall_v = wall_f = None
    if base is not None:
        # quad cells on the boundary: an edge is open if the neighbour quad is missing
        pad = np.pad(ok, 1, constant_values=False)
        edges = []
        for (dr, dc), (p, q) in (((-1, 0), (a, b)), ((1, 0), (d, c)),
                                 ((0, -1), (c, a)), ((0, 1), (b, d))):
            open_ = ok & ~pad[1 + dr:1 + dr + nr - 1, 1 + dc:1 + dc + nc - 1]
            edges.append(np.column_stack([p[open_], q[open_]]))
        e = np.concatenate(edges)
        top0, top1 = verts[e[:, 0]], verts[e[:, 1]]
        bot0, bot1 = top0.copy(), top1.copy()
        bot0[:, 2] = base
        bot1[:, 2] = base
        n = len(e)
        wall_v = np.concatenate([top0, top1, bot0, bot1]).astype("float32")
        i = np.arange(n, dtype="int32")
        wall_f = np.concatenate([
            np.column_stack([i, i + 2 * n, i + n]),
            np.column_stack([i + n, i + 2 * n, i + 3 * n])]).astype("int32")
    return verts, faces, uv, wall_v, wall_f


def prisms(polys_xy, heights, uv=None):
    """Extrude convex polygons (e.g. hexagons) into columns standing on z = 0.

    polys_xy  (n, k, 2) polygon vertices, counter-clockwise
    heights   (n,)
    uv        (n, 2) texture coordinate shared by every vertex of a column
    """
    n, k, _ = polys_xy.shape
    h = np.asarray(heights, dtype="float32")
    top = np.concatenate([polys_xy, np.repeat(h[:, None, None], k, 1)], 2)
    bot = np.concatenate([polys_xy, np.zeros((n, k, 1), "float32")], 2)
    verts = np.concatenate([top, bot], 1).reshape(-1, 3).astype("float32")
    base = (np.arange(n, dtype="int32") * 2 * k)[:, None]
    fan = np.array([[0, i, i + 1] for i in range(1, k - 1)], dtype="int32")
    side = []
    for i in range(k):
        j = (i + 1) % k
        side += [[i, k + i, j], [j, k + i, k + j]]
    local = np.concatenate([fan, np.array(side, dtype="int32")])
    faces = (base[:, :, None] + local[None]).reshape(-1, 3)
    tex = None
    if uv is not None:
        tex = np.repeat(np.asarray(uv, dtype="float32"), 2 * k, 0)
    return verts, faces, tex


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------
def _dir(az_deg, el_deg):
    """Unit vector pointing from the scene toward a sky position.
    Azimuth clockwise from north, elevation above the horizon."""
    az, el = math.radians(az_deg), math.radians(el_deg)
    return np.array([math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)])


def render(shapes, width, height, view_width, tilt=60.0, heading=0.0, centre=(0, 0, 0),
           sun_az=315.0, sun_el=42.0, sun_size=9.0, sun_share=0.68,
           sun_tint=(1.0, 0.965, 0.91), sky_tint=(0.93, 0.965, 1.0),
           floor=(0.94, 0.935, 0.915), floor_z=0.0, spp=48, max_depth=5, seed=0,
           denoise=True, tile=1024, progress=None, edge_height=1.0):
    """Render a list of shapes to a linear-light float image.

    shapes      list of dicts: {"verts", "faces", "uv"?, "texture"? (H,W,3 sRGB
                0..1 array) or "color" (sRGB 0..1), "flat": bool}
    view_width  ground distance spanned by the image width
    tilt        camera elevation above the horizon, 90 = straight down
    heading     direction the camera looks toward, clockwise from north
    floor       sRGB colour of the floor, or None for no floor
    denoise     run Intel Open Image Denoise, guided by albedo and normals
    edge_height height of the model's rim above the floor, for the mask
    Returns (rgb float32 (H, W, 3) linear, object_mask float32 (H, W)).
    """
    from common import srgb_to_linear
    mi = mitsuba()
    T = mi.ScalarTransform4f
    tmp = Path(tempfile.mkdtemp(prefix="zp_mi_"))
    width, height = int(width), int(height)

    scene = {"type": "scene"}
    scene["integrator"] = {
        "type": "aov", "aovs": "alb:albedo,nn:sh_normal,pos:position",
        "img": {"type": "path", "max_depth": max_depth}}

    # camera placement (the sensor itself is built per tile, below)
    view_dir = -_dir(heading + 180.0, tilt)          # from camera toward the scene
    c = np.asarray(centre, dtype="float64")
    dist = view_width * 6.0
    origin = c - view_dir * dist
    up = [0, 0, 1] if tilt < 89.5 else list(_dir(heading, 0.0))
    half_w = view_width / 2
    to_world = (T().look_at(origin=list(origin), target=list(c), up=up)
                @ T().scale([half_w, half_w, 1.0]))

    # Light, normalised so a white horizontal diffuse surface renders at 1.0
    # and neutral: the warm sun and the cool sky add up to white.
    sun_dir = _dir(sun_az, sun_el)
    sky_share = 1.0 - sun_share
    mix = np.array(sun_tint) * sun_share + np.array(sky_tint) * sky_share
    sun_rgb = np.array(sun_tint) / mix
    sky_rgb = np.array(sky_tint) / mix
    scene["sky"] = {"type": "constant", "radiance": {
        "type": "rgb", "value": [float(sky_share * t) for t in sky_rgb]}}
    R = dist * 3.0
    ang = math.radians(sun_size) / 2
    radius = R * math.tan(ang)
    omega = math.pi * math.tan(ang) ** 2
    L = sun_share * math.pi / (omega * math.sin(math.radians(sun_el)))
    pos = c + sun_dir * R
    scene["sun"] = {
        "type": "disk",
        "to_world": T().look_at(origin=list(pos), target=list(c), up=[0, 0, 1]) @ T().scale(radius),
        "emitter": {"type": "area", "radiance": {
            "type": "rgb", "value": [float(L * t) for t in sun_rgb]}},
    }

    if floor is not None:
        fl = [float(v) for v in srgb_to_linear(np.array(floor))]
        scene["floor"] = {
            "type": "rectangle",
            "to_world": T().translate([float(c[0]), float(c[1]), float(floor_z)])
                        @ T().scale(view_width * 40),
            "bsdf": {"type": "diffuse", "reflectance": {"type": "rgb", "value": fl}},
        }

    for i, s in enumerate(shapes):
        ply = tmp / f"shape{i}.ply"
        write_ply(ply, s["verts"], s["faces"], s.get("uv"))
        if s.get("texture") is not None:
            tex = (np.clip(s["texture"], 0, 1) * 255).astype("uint8")
            refl = {"type": "bitmap", "bitmap": mi.Bitmap(np.ascontiguousarray(tex)),
                    "filter_type": s.get("filter", "bilinear"), "wrap_mode": "clamp"}
        else:
            refl = {"type": "rgb",
                    "value": [float(v) for v in srgb_to_linear(np.array(s["color"]))]}
        scene[f"shape{i}"] = {
            "type": "ply", "filename": str(ply),
            "face_normals": bool(s.get("flat", False)),
            "bsdf": {"type": "twosided",
                     "material": {"type": "diffuse", "reflectance": refl}},
        }

    sc = mi.load_dict(scene)
    for f in tmp.iterdir():
        f.unlink()
    tmp.rmdir()

    # Render in tiles so the wavefront stays within memory at print sizes.
    img = np.zeros((height, width, 12), dtype="float32")
    tiles = [(x, y) for y in range(0, height, tile) for x in range(0, width, tile)]
    for n, (x, y) in enumerate(tiles):
        tw, th = min(tile, width - x), min(tile, height - y)
        sensor = mi.load_dict({
            "type": "orthographic", "near_clip": dist * 0.05, "far_clip": dist * 4,
            "to_world": to_world,
            "film": {"type": "hdrfilm", "width": width, "height": height,
                     "crop_offset_x": x, "crop_offset_y": y,
                     "crop_width": tw, "crop_height": th,
                     "pixel_format": "rgb", "component_format": "float32",
                     "rfilter": {"type": "box"}},
            "sampler": {"type": "independent", "sample_count": int(spp)},
        })
        img[y:y + th, x:x + tw] = np.array(
            mi.render(sc, sensor=sensor, spp=int(spp), seed=seed + n))
        if progress:
            progress(n + 1, len(tiles))

    rgb = np.clip(np.nan_to_num(img[..., :3]), 0, 64)
    albedo, normal, pos_z = img[..., 3:6], img[..., 6:9], img[..., 11]
    if denoise:
        import pyoidn
        # Denoise in overlapping tiles so a print-size image stays within
        # memory; the overlaps are feathered so tile joins cannot show.
        out = np.zeros_like(rgb)
        wsum = np.zeros(rgb.shape[:2], dtype="float32")
        size, pad = 2048, 96
        for y in range(0, height, size):
            for x in range(0, width, size):
                ya, yb = max(y - pad, 0), min(y + size + pad, height)
                xa, xb = max(x - pad, 0), min(x + size + pad, width)
                piece = pyoidn.denoise(
                    np.ascontiguousarray(rgb[ya:yb, xa:xb]),
                    albedo=np.ascontiguousarray(np.clip(albedo[ya:yb, xa:xb], 0, 1)),
                    normal=np.ascontiguousarray(np.clip(normal[ya:yb, xa:xb], -1, 1)),
                    hdr=True, quality="high")
                wy = np.minimum(np.arange(yb - ya) + 1, np.arange(yb - ya)[::-1] + 1)
                wx = np.minimum(np.arange(xb - xa) + 1, np.arange(xb - xa)[::-1] + 1)
                wgt = np.minimum.outer(np.minimum(wy, pad), np.minimum(wx, pad)).astype("float32")
                out[ya:yb, xa:xb] += piece * wgt[..., None]
                wsum[ya:yb, xa:xb] += wgt
        rgb = out / wsum[..., None]
    # Coverage of the model over the floor. Position is averaged per pixel, so
    # a pixel half on the model's rim (which stands `edge_height` above the
    # floor) comes out near 0.5: an anti-aliased edge.
    mask = np.clip((pos_z - floor_z) / max(edge_height, 1e-6), 0, 1)
    return rgb.astype("float32"), mask.astype("float32")


def tonemap(rgb, exposure=1.0, shoulder=0.82):
    """Linear -> display sRGB (0..1) with a soft highlight roll-off."""
    from common import linear_to_srgb
    x = np.clip(rgb * exposure, 0, None)
    over = x > shoulder
    room = 1.0 - shoulder
    x = np.where(over, shoulder + room * (1 - np.exp(-(x - shoulder) / room)), x)
    return linear_to_srgb(x)
