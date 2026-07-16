import math

def get_rounded_rect_point(w, d, r, s):
    # Clamp r to prevent negative values
    hw, hd = w * 0.5, d * 0.5
    r = min(r, hw - 0.01, hd - 0.01)
    r = max(r, 0.001)

    L1 = hd - r
    L2 = math.pi * 0.5 * r
    L3 = w - 2.0 * r
    L4 = math.pi * 0.5 * r
    L5 = d - 2.0 * r
    L6 = math.pi * 0.5 * r
    L7 = w - 2.0 * r
    L8 = math.pi * 0.5 * r
    L9 = hd - r

    if s < L1:
        return hw, s
    s -= L1

    if s < L2:
        theta = s / r
        return (hw - r) + r * math.cos(theta), (hd - r) + r * math.sin(theta)
    s -= L2

    if s < L3:
        return (hw - r) - s, hd
    s -= L3

    if s < L4:
        theta = math.pi * 0.5 + s / r
        return (-hw + r) + r * math.cos(theta), (hd - r) + r * math.sin(theta)
    s -= L4

    if s < L5:
        return -hw, (hd - r) - s
    s -= L5

    if s < L6:
        theta = math.pi + s / r
        return (-hw + r) + r * math.cos(theta), (-hd + r) + r * math.sin(theta)
    s -= L6

    if s < L7:
        return (-hw + r) + s, -hd
    s -= L7

    if s < L8:
        theta = math.pi * 1.5 + s / r
        return (hw - r) + r * math.cos(theta), (-hd + r) + r * math.sin(theta)
    s -= L8

    # Must be in L9
    return hw, -hd + r + s

def test_uniform():
    w, d, c = 91.778, 1.0, 2.0
    hw, hd = w * 0.5, d * 0.5
    r = min(c, hw - 0.01, hd - 0.01)
    r = max(r, 0.001)

    L1 = hd - r
    L2 = math.pi * 0.5 * r
    L3 = w - 2.0 * r
    L4 = math.pi * 0.5 * r
    L5 = d - 2.0 * r
    L6 = math.pi * 0.5 * r
    L7 = w - 2.0 * r
    L8 = math.pi * 0.5 * r
    L9 = hd - r

    p_tot = L1 + L2 + L3 + L4 + L5 + L6 + L7 + L8 + L9
    print(f"Perimeter: {p_tot:.4f}")

    pts = []
    for i in range(72):
        s = p_tot * float(i) / 72.0
        pt = get_rounded_rect_point(w, d, c, s)
        pts.append(pt)

    print("  First 5 pts:", [f"({p[0]:.4f},{p[1]:.4f})" for p in pts[:5]])
    uniq = set(pts)
    print(f"  Total points: {len(pts)}, Unique points: {len(uniq)}")

    max_dist = 0.0
    min_dist = 999999.0
    for i in range(72):
        p_curr = pts[i]
        p_next = pts[(i + 1) % 72]
        dist = math.hypot(p_curr[0] - p_next[0], p_curr[1] - p_next[1])
        max_dist = max(max_dist, dist)
        min_dist = min(min_dist, dist)
    print(f"  Min consecutive distance: {min_dist:.6f}")
    print(f"  Max consecutive distance: {max_dist:.6f}")

if __name__ == "__main__":
    test_uniform()
