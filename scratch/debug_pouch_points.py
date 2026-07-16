import math

VALUES = {
    "Overall_Height": 200.0,
    "Overall_Width": 120.0,
    "Overall_Depth": 8.0,
    "Wall_Thickness": 0.5,
    "Shoulder_Height": 40.0,
    "Shoulder_Radius": 15.0,
    "Side_Taper": 2.0,
    "Top_Seal_Width": 15.0,
    "Bottom_Gusset_Height": 25.0,
    "Bottom_Gusset_Depth": 15.0,
    "Corner_Radius": 12.0,
    "Spout_Diameter": 12.0,
    "Spout_Length": 18.0,
    "Cap_Diameter": 16.0,
    "Cap_Height": 15.0,
    "Seal_Band_Width": 8.0,
    "Blend_Radius": 2.0,
}

def v(name):
    return VALUES[name]

def radius_to_rounded_rect(width, depth, corner, angle):
    ux, yx = math.cos(angle), math.sin(angle)
    low, high = 0.0, max(width, depth)
    hw, hd = width * 0.5, depth * 0.5
    rr = min(corner, hw - 0.01, hd - 0.01)
    for _ in range(40):
        mid = (low + high) * 0.5
        x, y = mid * ux, mid * yx
        qx = abs(x) - (hw - rr)
        qy = abs(y) - (hd - rr)
        outside = math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - rr
        if outside <= 0.0:
            low = mid
        else:
            high = mid
    return low

def test_sections():
    taper_rad = math.radians(v("Side_Taper"))
    hw_top = v("Overall_Width") / 2.0
    z_top = v("Overall_Height")

    def hw_at_z(z_val):
        return hw_top - (z_top - z_val) * math.tan(taper_rad)

    def w_inner_at_z(z_val):
        return 2.0 * (hw_at_z(z_val) - v("Seal_Band_Width"))

    z0 = v("Bottom_Gusset_Height")
    z3 = v("Overall_Height") - v("Shoulder_Height")
    z1 = z0 + (z3 - z0) * 0.4
    z2 = z0 + (z3 - z0) * 0.7

    sections_args = [
        (z0, w_inner_at_z(z0), v("Wall_Thickness") * 2.0, v("Blend_Radius")),
        (z1, w_inner_at_z(z1), v("Overall_Depth"), v("Corner_Radius") - v("Seal_Band_Width")),
        (z2, w_inner_at_z(z2), v("Overall_Depth"), v("Corner_Radius") - v("Seal_Band_Width")),
        (z3, w_inner_at_z(z3), v("Wall_Thickness") * 2.0, v("Blend_Radius")),
    ]

    for idx, (z, w, d, c) in enumerate(sections_args):
        print(f"Section {idx}: z={z:.3f}, w={w:.3f}, d={d:.3f}, corner={c:.3f}")
        pts = []
        for i in range(72):
            a = 2.0 * math.pi * float(i) / 72.0
            mag = radius_to_rounded_rect(w, d, c, a)
            pts.append((mag * math.cos(a), mag * math.sin(a), z))
        # Print first few points
        print("  First 5 pts:", [f"({p[0]:.4f},{p[1]:.4f},{p[2]:.4f})" for p in pts[:5]])
        # Check if there are any duplicate points
        uniq = set(pts)
        print(f"  Total points: {len(pts)}, Unique points: {len(uniq)}")
        # Check consecutive distances
        gaps = 0
        for i in range(72):
            p_curr = pts[i]
            p_next = pts[(i + 1) % 72]
            dist = math.hypot(p_curr[0] - p_next[0], p_curr[1] - p_next[1])
            if dist < 1e-5:
                gaps += 1
        print(f"  Consecutive distances < 1e-5: {gaps}")

if __name__ == "__main__":
    test_sections()
