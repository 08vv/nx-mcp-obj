import math

def solve_cushion(W, L, Rc, Rs):
    B = W/2.0 - Rs
    A = L/2.0 - Rs
    d = Rs - Rc
    k = (A**2 - B**2) / 2.0
    aq = 1.0 + (B / A)**2
    bq = 2.0 * B * (k / (A**2) - 1.0)
    cq = (k / A)**2 + B**2 - d**2
    disc = bq**2 - 4.0 * aq * cq
    yc = (-bq + math.sqrt(disc)) / (2.0 * aq)
    xc = (B * yc + k) / A
    
    v_top_x = xc
    v_top_y = yc - B
    v_top_len = math.hypot(v_top_x, v_top_y)
    t_top_x = xc * (Rs / v_top_len)
    t_top_y = B + (yc - B) * (Rs / v_top_len)
    
    v_right_x = xc - A
    v_right_y = yc
    v_right_len = math.hypot(v_right_x, v_right_y)
    t_right_x = A + (xc - A) * (Rs / v_right_len)
    t_right_y = yc * (Rs / v_right_len)
    
    return xc, yc, t_top_x, t_top_y, t_right_x, t_right_y

def main():
    W, L, Rc = 80.0, 80.0, 15.0
    Rs = 5.0 * W
    xc, yc, tx_top, ty_top, tx_right, ty_right = solve_cushion(W, L, Rc, Rs)
    
    # Let's print the transition points
    print(f"Top transition point: ({tx_top}, {ty_top})")
    print(f"Right transition point: ({tx_right}, {ty_right})")
    
    # Calculate arc endpoints
    # Arc 1: Top side arc (c_top, Rs)
    # Start: (-tx_top, ty_top), End: (tx_top, ty_top)
    
    # Arc 2: Top-Right corner arc (c_tr=(xc, yc), Rc)
    # Start: (tx_top, ty_top), End: (tx_right, ty_right)
    # Check start radius and end radius from center c_tr:
    r_start = math.hypot(tx_top - xc, ty_top - yc)
    r_end = math.hypot(tx_right - xc, ty_right - yc)
    print(f"Corner arc start radius: {r_start}, end radius: {r_end} (should be Rc={Rc})")
    print(f"Difference from Rc: {r_start - Rc}, {r_end - Rc}")

if __name__ == "__main__":
    main()
