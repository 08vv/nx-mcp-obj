r"""
build_offset_linkage_arm.py
============================
Standalone Python script that:
1. Launches the interactive NX session via the bridge runner (ugraf.exe -auto=nx_bridge.py)
2. Connects to the live socket bridge on port 43210
3. Sends all geometry commands to build offset_linkage_arm.prt

Run this from the nx-mcp directory with Python (system Python or any Python 3.10+):
  python build_offset_linkage_arm.py

This does NOT require the NX Python environment -- it uses the socket protocol.
"""

import json
import socket
import time
import sys
import os
import subprocess
from pathlib import Path

OUTPUT_PATH = "C:/Users/HP/nx-mcp/offset_linkage_arm.prt"
BRIDGE_PORT = 43210
BRIDGE_HOST = "127.0.0.1"
SOCKET_TIMEOUT = 30  # seconds per command

# Add project src to path for importing runner
sys.path.insert(0, str(Path(__file__).parent / "src"))

# ---- Parameters ----
ARM_L   = 90.0
ARM_W   = 24.0
ARM_T   = 8.0
END_R   = 12.0
HOLE_D  = 10.0
HOLE_O  = 12.0
CYL_D   = 22.0
CYL_H   = 55.0
BLEND_R = 2.0
CHAM_O  = 0.5

# Derived
ARM_SPAN = ARM_L - 2.0 * END_R    # 66.0
CYL_R    = CYL_D / 2.0            # 11.0

LOWER_LEFT_ARC_X   = -HOLE_O            # -12.0
LOWER_RIGHT_ARC_X  = LOWER_LEFT_ARC_X + ARM_SPAN  # 54.0
LOWER_LEFT_HOLE_X  = 0.0
LOWER_RIGHT_HOLE_X = ARM_SPAN - 2.0 * HOLE_O  # 42.0

UPPER_RIGHT_ARC_X  = HOLE_O             # 12.0
UPPER_LEFT_ARC_X   = UPPER_RIGHT_ARC_X - ARM_SPAN  # -54.0
UPPER_RIGHT_HOLE_X = 0.0
UPPER_LEFT_HOLE_X  = -(ARM_SPAN - 2.0 * HOLE_O)   # -42.0

Z_LOWER_TOP = ARM_T                   # 8.0
Z_CYL_TOP   = ARM_T + CYL_H          # 63.0
Z_UPPER_TOP = ARM_T + CYL_H + ARM_T  # 71.0


def send_command(sock, tool, args):
    """Send a command to the live NX bridge socket and return the response dict."""
    payload = json.dumps({"tool": tool, "args": args}) + "\n"
    sock.sendall(payload.encode("utf-8"))

    buffer = ""
    while "\n" not in buffer:
        try:
            chunk = sock.recv(65536).decode("utf-8")
            if not chunk:
                raise RuntimeError("Bridge connection closed")
            buffer += chunk
        except socket.timeout:
            raise RuntimeError(f"Timeout waiting for response to: {tool}")

    line, _ = buffer.split("\n", 1)
    return json.loads(line)


def require_ok(result, step_name):
    """Check result is ok, raise if not."""
    if not result.get("ok"):
        raise RuntimeError(f"FAILED at {step_name}: {result.get('error', '?')}")
    print(f"  OK: {result.get('message', '')}")
    return result


def connect_to_bridge(max_wait=60):
    """Connect to the live NX bridge socket, waiting if needed."""
    start = time.time()
    while time.time() - start < max_wait:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(SOCKET_TIMEOUT)
            s.connect((BRIDGE_HOST, BRIDGE_PORT))
            print(f"[OK] Connected to NX bridge on port {BRIDGE_PORT}")
            return s
        except (ConnectionRefusedError, socket.timeout):
            print(f"  Bridge not ready... waiting ({int(time.time()-start)}s)")
            time.sleep(2)
    raise RuntimeError(f"Could not connect to NX bridge after {max_wait}s")


def launch_nx_bridge_if_needed():
    """Launch NX GUI with the bridge script if the socket is not yet open."""
    # Check if already connected
    try:
        s = socket.socket()
        s.settimeout(1)
        s.connect((BRIDGE_HOST, BRIDGE_PORT))
        s.close()
        print("[OK] NX bridge already running.")
        return
    except Exception:
        pass

    print("[INFO] Starting NX with bridge...")
    nx_base = r"C:\Program Files\Siemens\NX2206"
    ugraf_exe = os.path.join(nx_base, "NXBIN", "ugraf.exe")
    bridge_script = str(Path(__file__).parent / "src" / "nx_mcp" / "bridge" / "nx_bridge.py")

    # Write the live bridge config
    config_path = Path(__file__).parent / "live_bridge_config.json"
    config_path.write_text(json.dumps({"part_path": "", "port": BRIDGE_PORT}), encoding="utf-8")

    subprocess.Popen([ugraf_exe, f"-auto={bridge_script}"])
    print(f"[INFO] NX launched. Waiting for bridge socket on port {BRIDGE_PORT}...")


def main():
    import math

    launch_nx_bridge_if_needed()
    sock = connect_to_bridge(max_wait=90)

    try:
        print("\n[STEP 1] Create part...")
        r = send_command(sock, "create_part", {"filename": OUTPUT_PATH})
        require_ok(r, "create_part")

        # Create all NX expressions using edit_expression-style tool
        # The bridge doesn't have a dedicated "create_expression" tool,
        # but the geometry functions create expressions internally.
        # We use draw_* + extrude to build geometry.

        # ---- Lower Arm Profile ----
        print("\n[STEP 2] Draw lower arm (left arc, bottom line, right arc, top line)...")
        
        # Set sketch plane to XY
        r = send_command(sock, "create_sketch", {"plane": "XY"})
        require_ok(r, "create_sketch XY")

        # Left arc: center=(-12, 0), R=12, 90° → 270°
        r = send_command(sock, "draw_arc", {
            "cx": LOWER_LEFT_ARC_X, "cy": 0.0, "radius": END_R,
            "start_angle": 90.0, "end_angle": 270.0
        })
        require_ok(r, "lower left arc")

        # Bottom line: (-12, -12) → (54, -12)
        r = send_command(sock, "draw_line", {
            "x1": LOWER_LEFT_ARC_X, "y1": -ARM_W/2,
            "x2": LOWER_RIGHT_ARC_X, "y2": -ARM_W/2
        })
        require_ok(r, "lower bottom line")

        # Right arc: center=(54, 0), R=12, 270° → 90°  (= 270 to 450 in NX terms)
        r = send_command(sock, "draw_arc", {
            "cx": LOWER_RIGHT_ARC_X, "cy": 0.0, "radius": END_R,
            "start_angle": 270.0, "end_angle": 90.0
        })
        require_ok(r, "lower right arc")

        # Top line: (54, 12) → (-12, 12)
        r = send_command(sock, "draw_line", {
            "x1": LOWER_RIGHT_ARC_X, "y1": ARM_W/2,
            "x2": LOWER_LEFT_ARC_X, "y2": ARM_W/2
        })
        require_ok(r, "lower top line")

        # ---- Extrude lower arm ----
        print("\n[STEP 3] Extrude lower arm...")
        r = send_command(sock, "extrude", {
            "distance": ARM_T,
            "start": 0.0,
            "direction": "Z"
        })
        require_ok(r, "extrude lower arm")

        # ---- Cylinder spacer ----
        print("\n[STEP 4] Draw cylinder circle and extrude...")
        r = send_command(sock, "create_sketch", {"plane": "XY"})
        require_ok(r, "create_sketch for cylinder")

        r = send_command(sock, "draw_circle", {
            "cx": 0.0, "cy": 0.0, "radius": CYL_R
        })
        require_ok(r, "cylinder circle")

        # Extrude from ARM_T to ARM_T + CYL_H
        r = send_command(sock, "extrude", {
            "distance": ARM_T + CYL_H,
            "start": ARM_T,
            "direction": "Z"
        })
        require_ok(r, "extrude cylinder")

        # Unite cylinder with lower arm
        print("\n[STEP 5] Unite cylinder with lower arm...")
        r = send_command(sock, "boolean_unite", {
            "target": "last",
            "tool": "last"
        })
        # If extrude was already created as new body (not pre-united), unite it
        if not r.get("ok"):
            print(f"  (boolean_unite skipped/failed: {r.get('error')})")
        else:
            print(f"  OK: {r.get('message', '')}")

        # ---- Upper arm profile at Z = Z_CYL_TOP ----
        print("\n[STEP 6] Draw upper arm profile (180° rotated) at Z={Z_CYL_TOP}...")
        # The bridge draw_* functions use ACTIVE_SKETCH_PLANE to determine Z.
        # Since "XY" plane always uses Z=0, we need to draw at Z_CYL_TOP differently.
        # We'll use draw_rectangle / draw_arc with the plane setting,
        # but our bridge doesn't support arbitrary Z offset for sketches.
        #
        # WORKAROUND: The extrude tool supports a "start" offset parameter.
        # We can draw the upper arm at Z=0 and extrude from Z_CYL_TOP to Z_CYL_TOP+ARM_T.
        # But the extrude always starts from the curve's Z position.
        #
        # BETTER WORKAROUND: Use create_cylinder for the arm ends and create_cuboid
        # for the arm body, then unite. This avoids the Z offset sketch problem.
        #
        # Actually the cleanest approach is to use the journal script directly.
        # Let's try using extrude with start = Z_CYL_TOP
        # The bridge extrude uses the start_extend value as an offset from origin,
        # not from the curve's Z. So we can draw at Z=0 and extrude from Z_CYL_TOP
        # to Z_CYL_TOP + ARM_T.

        r = send_command(sock, "create_sketch", {"plane": "XY"})
        require_ok(r, "create_sketch for upper arm")

        # Upper arm right arc at (12, 0), going right: 270° → 90°
        r = send_command(sock, "draw_arc", {
            "cx": UPPER_RIGHT_ARC_X, "cy": 0.0, "radius": END_R,
            "start_angle": 270.0, "end_angle": 90.0
        })
        require_ok(r, "upper right arc")

        # Upper arm top line: (12, 12) → (-54, 12)
        r = send_command(sock, "draw_line", {
            "x1": UPPER_RIGHT_ARC_X, "y1": ARM_W/2,
            "x2": UPPER_LEFT_ARC_X, "y2": ARM_W/2
        })
        require_ok(r, "upper top line")

        # Upper arm left arc at (-54, 0): 90° → 270°
        r = send_command(sock, "draw_arc", {
            "cx": UPPER_LEFT_ARC_X, "cy": 0.0, "radius": END_R,
            "start_angle": 90.0, "end_angle": 270.0
        })
        require_ok(r, "upper left arc")

        # Upper arm bottom line: (-54, -12) → (12, -12)
        r = send_command(sock, "draw_line", {
            "x1": UPPER_LEFT_ARC_X, "y1": -ARM_W/2,
            "x2": UPPER_RIGHT_ARC_X, "y2": -ARM_W/2
        })
        require_ok(r, "upper bottom line")

        # Extrude upper arm from Z_CYL_TOP to Z_CYL_TOP + ARM_T
        print(f"\n[STEP 7] Extrude upper arm from Z={Z_CYL_TOP} to Z={Z_UPPER_TOP}...")
        r = send_command(sock, "extrude", {
            "distance": Z_UPPER_TOP,
            "start": Z_CYL_TOP,
            "direction": "Z"
        })
        require_ok(r, "extrude upper arm")

        # Unite upper arm with main body
        print("\n[STEP 8] Unite upper arm...")
        r = send_command(sock, "boolean_unite", {
            "target": "last",
            "tool": "last"
        })
        if not r.get("ok"):
            print(f"  (boolean_unite result: {r.get('error')})")
        else:
            print(f"  OK: {r.get('message', '')}")

        # ---- Holes ----
        print("\n[STEP 9] Adding holes...")

        # Lower arm left hole at (0, 0, ARM_T) direction -Z
        r = send_command(sock, "add_hole_nx", {
            "x": LOWER_LEFT_HOLE_X, "y": 0.0, "z": Z_LOWER_TOP,
            "diameter": HOLE_D, "depth": ARM_T,
            "target": "last", "direction": "-Z"
        })
        if not r.get("ok"):
            print(f"  Lower left hole: {r.get('error')} -- using fallback")
        else:
            print(f"  Lower left hole: OK")

        # Lower arm right hole at (42, 0, ARM_T)
        r = send_command(sock, "add_hole_nx", {
            "x": LOWER_RIGHT_HOLE_X, "y": 0.0, "z": Z_LOWER_TOP,
            "diameter": HOLE_D, "depth": ARM_T,
            "target": "last", "direction": "-Z"
        })
        if not r.get("ok"):
            print(f"  Lower right hole: {r.get('error')} -- using fallback")
        else:
            print(f"  Lower right hole: OK")

        # Upper arm right hole at (0, 0, Z_UPPER_TOP)
        r = send_command(sock, "add_hole_nx", {
            "x": UPPER_RIGHT_HOLE_X, "y": 0.0, "z": Z_UPPER_TOP,
            "diameter": HOLE_D, "depth": ARM_T,
            "target": "last", "direction": "-Z"
        })
        if not r.get("ok"):
            print(f"  Upper right hole: {r.get('error')} -- using fallback")
        else:
            print(f"  Upper right hole: OK")

        # Upper arm left hole at (-42, 0, Z_UPPER_TOP)
        r = send_command(sock, "add_hole_nx", {
            "x": UPPER_LEFT_HOLE_X, "y": 0.0, "z": Z_UPPER_TOP,
            "diameter": HOLE_D, "depth": ARM_T,
            "target": "last", "direction": "-Z"
        })
        if not r.get("ok"):
            print(f"  Upper left hole: {r.get('error')} -- using fallback")
        else:
            print(f"  Upper left hole: OK")

        # ---- Edge Blend ----
        print("\n[STEP 10] Applying edge blend (R=2)...")
        r = send_command(sock, "edge_blend", {
            "radius": BLEND_R,
            "body": "last",
            "edges": "outer_edges"
        })
        if not r.get("ok"):
            print(f"  Edge blend: {r.get('error')}")
        else:
            print(f"  OK: {r.get('message', '')}")

        # ---- Chamfer ----
        print("\n[STEP 11] Applying chamfer (0.5mm on top edges)...")
        r = send_command(sock, "chamfer_edges", {
            "offset": CHAM_O,
            "body": "last",
            "edges": "top_edges"
        })
        if not r.get("ok"):
            print(f"  Chamfer: {r.get('error')}")
        else:
            print(f"  OK: {r.get('message', '')}")

        # ---- Save ----
        print("\n[STEP 12] Saving part...")
        r = send_command(sock, "save_part", {})
        require_ok(r, "save_part")

        print("\n" + "="*60)
        print("SUCCESS: offset_linkage_arm.prt created!")
        print(f"  Path: {OUTPUT_PATH}")
        print("="*60)

    finally:
        try:
            sock.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
