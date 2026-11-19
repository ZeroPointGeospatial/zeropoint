"""Drainage analysis on a DEM grid: Priority-Flood depression handling
(Barnes, Lehman & Mulla 2014), D8 flow routing, flow accumulation, outlet
labelling and stream tracing.

Written for the Kenya rivers plate, where no ready-made river network could
be downloaded: the stream lines on that plate are computed here from the
Copernicus GLO-90 surface.
"""
import numpy as np
from numba import njit

# D8 neighbour offsets (row, col) and their distances in cell units
DR = np.array([-1, -1, 0, 1, 1, 1, 0, -1], dtype=np.int64)
DC = np.array([0, 1, 1, 1, 0, -1, -1, -1], dtype=np.int64)
DD = np.array([1.0, 1.41421356, 1.0, 1.41421356, 1.0, 1.41421356, 1.0, 1.41421356])


@njit(cache=True)
def _heap_push(he, hi, n, e, i):
    k = n
    he[k], hi[k] = e, i
    while k > 0:
        p = (k - 1) >> 1
        if he[p] <= he[k]:
            break
        he[p], he[k] = he[k], he[p]
        hi[p], hi[k] = hi[k], hi[p]
        k = p
    return n + 1


@njit(cache=True)
def _heap_pop(he, hi, n):
    top = hi[0]
    n -= 1
    he[0], hi[0] = he[n], hi[n]
    k = 0
    while True:
        a, b, s = 2 * k + 1, 2 * k + 2, k
        if a < n and he[a] < he[s]:
            s = a
        if b < n and he[b] < he[s]:
            s = b
        if s == k:
            break
        he[s], he[k] = he[k], he[s]
        hi[s], hi[k] = hi[k], hi[s]
        k = s
    return top, n


@njit(cache=True)
def priority_flood(dem, seeds):
    """Flood the DEM upward from every seed cell (sea, sheet edge, terminal
    lakes).

    Returns
      order  flat cell indices in the order they were drained (outlets first)
      recv   for each cell, the flat index of the cell it drains to (-1 = outlet)
      filled the depression-filled surface
    """
    nr, nc = dem.shape
    n = nr * nc
    filled = dem.copy().ravel()
    flat_dem = dem.ravel()
    recv = np.full(n, -1, dtype=np.int32)
    order = np.empty(n, dtype=np.int32)
    closed = np.zeros(n, dtype=np.bool_)
    he = np.empty(n, dtype=np.float32)
    hi = np.empty(n, dtype=np.int32)
    pit = np.empty(n, dtype=np.int32)
    hn = 0
    ph = pt = 0
    k = 0

    for r in range(nr):
        for c in range(nc):
            if seeds[r, c]:
                i = r * nc + c
                closed[i] = True
                hn = _heap_push(he, hi, hn, filled[i], i)

    while hn > 0 or ph < pt:
        if ph < pt:
            i = pit[ph]
            ph += 1
        else:
            i, hn = _heap_pop(he, hi, hn)
        order[k] = i
        k += 1
        r, c = i // nc, i % nc
        for d in range(8):
            rr, cc = r + DR[d], c + DC[d]
            if rr < 0 or rr >= nr or cc < 0 or cc >= nc:
                continue
            j = rr * nc + cc
            if closed[j]:
                continue
            closed[j] = True
            recv[j] = i
            if flat_dem[j] <= filled[i]:
                filled[j] = filled[i]
                pit[pt] = j
                pt += 1
            else:
                hn = _heap_push(he, hi, hn, flat_dem[j], j)
    return order[:k], recv, filled.reshape(nr, nc)


@njit(cache=True)
def steepest_receivers(filled, recv, seeds):
    """Outside flats, send each cell to its steepest strictly-lower neighbour.

    The Priority-Flood receivers stay in place wherever a cell has no lower
    neighbour (lakes, filled pits), so the network stays connected and acyclic.
    """
    nr, nc = filled.shape
    for r in range(nr):
        for c in range(nc):
            if seeds[r, c]:
                continue
            z = filled[r, c]
            best, bj = 0.0, -1
            for d in range(8):
                rr, cc = r + DR[d], c + DC[d]
                if rr < 0 or rr >= nr or cc < 0 or cc >= nc:
                    continue
                s = (z - filled[rr, cc]) / DD[d]
                if s > best:
                    best, bj = s, rr * nc + cc
            if bj >= 0:
                recv[r * nc + c] = bj
    return recv


@njit(cache=True)
def flow_accumulation(filled, recv, weight):
    """Upstream contributing area, by a topological pass over the drainage
    tree: a cell is added to its receiver only once everything above it has
    been added to it."""
    acc = weight.copy().ravel()
    n = acc.size
    indeg = np.zeros(n, dtype=np.int32)
    for i in range(n):
        j = recv[i]
        if j >= 0:
            indeg[j] += 1
    stack = np.empty(n, dtype=np.int32)
    top = 0
    for i in range(n):
        if indeg[i] == 0:
            stack[top] = i
            top += 1
    while top > 0:
        top -= 1
        i = stack[top]
        j = recv[i]
        if j >= 0:
            acc[j] += acc[i]
            indeg[j] -= 1
            if indeg[j] == 0:
                stack[top] = j
                top += 1
    return acc.reshape(filled.shape)


@njit(cache=True)
def outlet_of(recv, n_iter=64):
    """Flat index of the outlet each cell ultimately drains to (pointer
    jumping, so it needs only log2(longest path) sweeps)."""
    n = recv.size
    root = np.empty(n, dtype=np.int32)
    for i in range(n):
        root[i] = recv[i] if recv[i] >= 0 else i
    for _ in range(n_iter):
        changed = False
        for i in range(n):
            r = root[i]
            rr = root[r]
            if rr != r:
                root[i] = rr
                changed = True
        if not changed:
            break
    return root


@njit(cache=True)
def trace_streams(recv, acc, stream, shape):
    """Turn the stream cells into polylines.

    Each line starts at a channel head or just below a confluence and runs
    downstream to (and including) the next confluence, so lines join up.
    Returns (rows, cols, offsets, area): vertex arrays, the start offset of
    each line, and the mean upstream area along each line.
    """
    nr, nc = shape
    n = recv.size
    s = stream.ravel()
    a = acc.ravel()
    nin = np.zeros(n, dtype=np.int32)
    for i in range(n):
        if s[i]:
            j = recv[i]
            if j >= 0 and s[j]:
                nin[j] += 1
    total = 0
    for i in range(n):
        if s[i]:
            total += 1
    rows = np.empty(total * 2 + 16, dtype=np.int32)
    cols = np.empty(total * 2 + 16, dtype=np.int32)
    offs = np.empty(total + 2, dtype=np.int64)
    area = np.empty(total + 2, dtype=np.float32)
    nv = 0
    nl = 0
    for i in range(n):
        if not s[i] or nin[i] == 1:
            continue                      # only heads (0 in) and confluences (>1 in)
        cur = i
        offs[nl] = nv
        asum = 0.0
        cnt = 0
        while True:
            rows[nv], cols[nv] = cur // nc, cur % nc
            nv += 1
            asum += a[cur]
            cnt += 1
            nxt = recv[cur]
            if nxt < 0 or not s[nxt]:
                break
            if nin[nxt] != 1:             # reached the next confluence: include it and stop
                rows[nv], cols[nv] = nxt // nc, nxt % nc
                nv += 1
                break
            cur = nxt
        area[nl] = asum / cnt
        nl += 1
    offs[nl] = nv
    return rows[:nv], cols[:nv], offs[:nl + 1], area[:nl]


@njit(cache=True)
def flood_region(dem, r0, c0, tol, max_cells):
    """Connected cells within `tol` metres of the seed's level (a lake surface
    or the floor of a dry pan). Returns a boolean mask."""
    nr, nc = dem.shape
    mask = np.zeros((nr, nc), dtype=np.bool_)
    z0 = dem[r0, c0]
    qr = np.empty(max_cells, dtype=np.int32)
    qc = np.empty(max_cells, dtype=np.int32)
    qr[0], qc[0] = r0, c0
    mask[r0, c0] = True
    h, t = 0, 1
    while h < t:
        r, c = qr[h], qc[h]
        h += 1
        for d in range(8):
            rr, cc = r + DR[d], c + DC[d]
            if rr < 0 or rr >= nr or cc < 0 or cc >= nc or mask[rr, cc]:
                continue
            if abs(dem[rr, cc] - z0) <= tol and t < max_cells:
                mask[rr, cc] = True
                qr[t], qc[t] = rr, cc
                t += 1
    return mask


def chaikin(x, y, n=2):
    """Corner-cutting smoothing that keeps both end points fixed."""
    for _ in range(n):
        if len(x) < 3:
            break
        qx = 0.75 * x[:-1] + 0.25 * x[1:]
        rx = 0.25 * x[:-1] + 0.75 * x[1:]
        qy = 0.75 * y[:-1] + 0.25 * y[1:]
        ry = 0.25 * y[:-1] + 0.75 * y[1:]
        nx = np.empty(2 * len(qx) + 2)
        ny = np.empty_like(nx)
        nx[0], ny[0], nx[-1], ny[-1] = x[0], y[0], x[-1], y[-1]
        nx[1:-1:2], nx[2:-1:2] = qx, rx
        ny[1:-1:2], ny[2:-1:2] = qy, ry
        x, y = nx, ny
    return x, y
