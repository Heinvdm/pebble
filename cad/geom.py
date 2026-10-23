import math
import numpy as np
from manifold3d import Manifold, CrossSection, OpType, JoinType, set_min_circular_angle, set_min_circular_edge_length

set_min_circular_angle(6.0)
set_min_circular_edge_length(0.5)


def empty():
    return Manifold()


def union(items):
    items = [m for m in items if m is not None and not m.is_empty()]
    if not items:
        return Manifold()
    if len(items) == 1:
        return items[0]
    return Manifold.batch_boolean(items, OpType.Add)


def cut(base, items):
    tool = union(items)
    if tool.is_empty():
        return base
    return base - tool


def box(x0, x1, y0, y1, z0, z1):
    return Manifold.cube((x1 - x0, y1 - y0, z1 - z0)).translate((x0, y0, z0))


def boxc(cx, cy, cz, lx, ly, lz):
    return box(cx - lx / 2.0, cx + lx / 2.0, cy - ly / 2.0, cy + ly / 2.0, cz - lz / 2.0, cz + lz / 2.0)


def cyl_z(cx, cy, r, z0, z1, r1=None, seg=0):
    return Manifold.cylinder(z1 - z0, r, r if r1 is None else r1, seg).translate((cx, cy, z0))


def cyl_y(cx, cz, r, y0, y1, r1=None, seg=0):
    return Manifold.cylinder(y1 - y0, r, r if r1 is None else r1, seg).rotate((-90.0, 0.0, 0.0)).translate((cx, y0, cz))


def cyl_x(cy, cz, r, x0, x1, r1=None, seg=0):
    return Manifold.cylinder(x1 - x0, r, r if r1 is None else r1, seg).rotate((0.0, 90.0, 0.0)).translate((x0, cy, cz))


def sphere(cx, cy, cz, r, seg=0):
    return Manifold.sphere(r, seg).translate((cx, cy, cz))


def poly(points):
    return CrossSection([np.asarray(points, dtype=np.float64)])


def circle2(cx, cy, r, seg=0):
    return CrossSection.circle(r, seg).translate((cx, cy))


def rect2(x0, x1, y0, y1):
    return CrossSection.square((x1 - x0, y1 - y0)).translate((x0, y0))


def rrect2(x0, x1, y0, y1, r):
    r = min(r, (x1 - x0) / 2.0 - 1e-6, (y1 - y0) / 2.0 - 1e-6)
    if r <= 0:
        return rect2(x0, x1, y0, y1)
    return rect2(x0 + r, x1 - r, y0 + r, y1 - r).offset(r, JoinType.Round)


def hull2(items):
    return CrossSection.batch_hull(list(items))


def extrude_z(cs, z0, z1):
    return Manifold.extrude(cs, z1 - z0).translate((0.0, 0.0, z0))


def extrude_y(cs_xz, y0, y1):
    return Manifold.extrude(cs_xz, y1 - y0).rotate((90.0, 0.0, 0.0)).translate((0.0, y1, 0.0))


def extrude_x(cs_yz, x0, x1):
    return Manifold.extrude(cs_yz, x1 - x0).rotate((90.0, 0.0, 90.0)).translate((x0, 0.0, 0.0))


def hull(items):
    return Manifold.batch_hull(list(items))


def slot_z(x0, y0, x1, y1, w, z0, z1):
    return extrude_z(hull2([circle2(x0, y0, w / 2.0), circle2(x1, y1, w / 2.0)]), z0, z1)


def mirror_y(m):
    return m.mirror((0.0, 1.0, 0.0))


def sym_y(m):
    return union([m, mirror_y(m)])


def body_outline(offset=0.0):
    from params import Body
    r = Body.corner_r + offset
    return rrect2(Body.rear_x - offset, Body.front_x + offset, -Body.half_y - offset, Body.half_y + offset, r)


def outline_halfwidth(x, offset=0.0):
    from params import Body
    r = Body.corner_r + offset
    hy = Body.half_y + offset
    flat = hy - r
    if x > Body.corner_cx_front:
        dx = x - Body.corner_cx_front
    elif x < Body.corner_cx_rear:
        dx = Body.corner_cx_rear - x
    else:
        return hy
    if dx >= r:
        return 0.0
    return flat + math.sqrt(r * r - dx * dx)


def outline_x_at(y, offset=0.0, front=True):
    from params import Body
    r = Body.corner_r + offset
    hy = Body.half_y + offset
    flat = hy - r
    ay = abs(y)
    if ay <= flat:
        dx = r
    else:
        d = ay - flat
        dx = math.sqrt(max(r * r - d * d, 0.0))
    return Body.corner_cx_front + dx if front else Body.corner_cx_rear - dx


def tilt_place(m, theta):
    from params import Tilt
    return m.rotate((0.0, -theta, 0.0)).translate((Tilt.axis_x, 0.0, Tilt.axis_z))


def tilt_unplace(m, theta):
    from params import Tilt
    return m.translate((-Tilt.axis_x, 0.0, -Tilt.axis_z)).rotate((0.0, theta, 0.0))


def sweep_angles(margin=None, step=None):
    from params import Tilt
    margin = Tilt.sweep_margin if margin is None else margin
    step = Tilt.sweep_step if step is None else step
    a0 = Tilt.t_min - margin
    a1 = Tilt.t_max + margin
    n = int(math.ceil((a1 - a0) / step))
    return [a0 + (a1 - a0) * i / n for i in range(n + 1)]


def sweep(m_local, angles=None):
    angles = sweep_angles() if angles is None else angles
    return union([tilt_place(m_local, a) for a in angles])


def inverse_sweep(m_robot, angles=None):
    angles = sweep_angles() if angles is None else angles
    return union([tilt_unplace(m_robot, a) for a in angles])


def mesh_arrays(m):
    mesh = m.to_mesh()
    v = np.asarray(mesh.vert_properties, dtype=np.float64)[:, :3]
    f = np.asarray(mesh.tri_verts, dtype=np.int64)
    return v, f


def write_stl(m, path):
    v, f = mesh_arrays(m)
    tri = v[f].astype(np.float32)
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    ln = np.linalg.norm(n, axis=1)
    ln[ln == 0] = 1.0
    n = (n / ln[:, None]).astype(np.float32)
    rec = np.zeros(len(f), dtype=[("n", "<f4", (3,)), ("v", "<f4", (3, 3)), ("a", "<u2")])
    rec["n"] = n
    rec["v"] = tri
    with open(path, "wb") as fh:
        fh.write(b"Pebble CAD".ljust(80, b" "))
        fh.write(np.uint32(len(f)).tobytes())
        fh.write(rec.tobytes())


def drop_to_bed(m):
    b = m.bounding_box()
    cx = (b[0] + b[3]) / 2.0
    cy = (b[1] + b[4]) / 2.0
    return m.translate((-cx, -cy, -b[2]))


def bbox_size(m):
    b = m.bounding_box()
    return (b[3] - b[0], b[4] - b[1], b[5] - b[2])
