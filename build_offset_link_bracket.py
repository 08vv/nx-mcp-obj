import json
import socket
import time
import sys
import os
import subprocess
from pathlib import Path

OUTPUT_PATH = "C:/Users/HP/nx-mcp/offset_link_bracket.prt"
BRIDGE_PORT = 43210
BRIDGE_HOST = "127.0.0.1"
SOCKET_TIMEOUT = 30  # seconds per command

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
    """Launch NX GUI with the bridge script, always restarting to load latest code."""

    # Clean kill old session if needed
    print("[INFO] Cleaning up existing ugraf.exe...")
    os.system("taskkill /F /IM ugraf.exe 2>nul")
    time.sleep(2)

    print("[INFO] Starting NX with bridge...")
    nx_base = r"C:\Program Files\Siemens\NX2206"
    ugraf_exe = os.path.join(nx_base, "NXBIN", "ugraf.exe")
    bridge_script = r"C:\Users\HP\nx-mcp\src\nx_mcp\bridge\nx_bridge.py"

    # Write the live bridge config
    config_path = Path("C:/Users/HP/nx-mcp/live_bridge_config.json")
    config_path.write_text(json.dumps({"part_path": "", "port": BRIDGE_PORT}), encoding="utf-8")

    subprocess.Popen([ugraf_exe, f"-auto={bridge_script}"])
    print(f"[INFO] NX launched. Waiting for bridge socket on port {BRIDGE_PORT}...")


def main():
    launch_nx_bridge_if_needed()
    sock = connect_to_bridge(max_wait=120)

    try:
        # Step 0: Create part
        print("\n[STEP 0] Create part...")
        part_file = Path(OUTPUT_PATH)
        if part_file.exists():
            try:
                part_file.unlink()
                print(f"[INFO] Deleted existing {OUTPUT_PATH}")
            except Exception as e:
                print(f"[WARNING] Could not delete {OUTPUT_PATH}: {e}")
        r = send_command(sock, "create_part", {"filename": OUTPUT_PATH})
        require_ok(r, "create_part")

        # Step 0.1: Create/Edit Expressions
        print("\n[STEP 0.1] Creating named expressions...")
        expressions = [
            ("ARM_LENGTH", 90.0),
            ("ARM_WIDTH", 24.0),
            ("END_RADIUS", 12.0),
            ("ARM_THICKNESS", 8.0),
            ("HOLE_DIA", 12.0),
            ("BOSS_DIA", 30.0),
            ("BOSS_HEIGHT", 45.0),
            ("ARM_ANGLE", 160.0),
            ("FILLET_R", 2.0)
        ]
        for name, value in expressions:
            r = send_command(sock, "edit_expression", {"name": name, "value": str(value)})
            require_ok(r, f"edit_expression {name}")

        # Step 1: create_real_sketch plane XY
        print("\n[STEP 1] create_real_sketch plane XY...")
        r = send_command(sock, "create_real_sketch", {"plane": "XY"})
        require_ok(r, "create_real_sketch 1")

        # Step 2: draw_rounded_rectangle
        print("\n[STEP 2] draw_rounded_rectangle...")
        r = send_command(sock, "draw_rounded_rectangle", {
            "sketch_name": "last",
            "cx_left": 0.0,
            "cy": 0.0,
            "arm_length": "ARM_LENGTH",
            "arm_width": "ARM_WIDTH",
            "end_radius": "END_RADIUS"
        })
        require_ok(r, "draw_rounded_rectangle 2")

        # Step 3: extrude_from_sketch Z
        print("\n[STEP 3] extrude_from_sketch...")
        r = send_command(sock, "extrude_from_sketch", {
            "sketch_name": "last",
            "direction": "Z",
            "start": 0.0,
            "distance": "ARM_THICKNESS"
        })
        require_ok(r, "extrude_from_sketch 3")

        # Step 4: add_hole_nx
        print("\n[STEP 4] add_hole_nx...")
        r = send_command(sock, "add_hole_nx", {
            "target": "last",
            "x": "END_RADIUS",
            "y": 0.0,
            "z": "ARM_THICKNESS",
            "diameter": "HOLE_DIA",
            "depth": "ARM_THICKNESS",
            "hole_type": "simple"
        })
        require_ok(r, "add_hole_nx 4")

        # Step 5: create_real_sketch plane XY
        print("\n[STEP 5] create_real_sketch plane XY...")
        r = send_command(sock, "create_real_sketch", {"plane": "XY"})
        require_ok(r, "create_real_sketch 5")

        # Step 6: draw_circle
        print("\n[STEP 6] draw_circle...")
        r = send_command(sock, "draw_circle", {
            "sketch_name": "last",
            "cx": "ARM_LENGTH - END_RADIUS",
            "cy": 0.0,
            "radius": "BOSS_DIA / 2"
        })
        require_ok(r, "draw_circle 6")

        # Step 7: extrude_from_sketch Z
        print("\n[STEP 7] extrude_from_sketch...")
        r = send_command(sock, "extrude_from_sketch", {
            "sketch_name": "last",
            "direction": "Z",
            "start": "ARM_THICKNESS",
            "distance": "BOSS_HEIGHT"
        })
        require_ok(r, "extrude_from_sketch 7")

        # Step 8: boolean_unite boss with arm
        print("\n[STEP 8] boolean_unite...")
        r = send_command(sock, "boolean_unite", {
            "target": "body_1",
            "tool": "body_2"
        })
        require_ok(r, "boolean_unite 8")

        # Step 9: create_real_sketch offset XY
        print("\n[STEP 9] create_real_sketch (rotated and offset)...")
        r = send_command(sock, "create_real_sketch", {
            "plane": "XY",
            "z_offset": "ARM_THICKNESS + BOSS_HEIGHT",
            "origin_x": "ARM_LENGTH - END_RADIUS",
            "origin_y": 0.0,
            "rotate_z_deg": "ARM_ANGLE"
        })
        require_ok(r, "create_real_sketch 9")

        # Step 10: draw_rounded_rectangle
        print("\n[STEP 10] draw_rounded_rectangle...")
        r = send_command(sock, "draw_rounded_rectangle", {
            "sketch_name": "last",
            "cx_left": 0.0,
            "cy": 0.0,
            "arm_length": "ARM_LENGTH",
            "arm_width": "ARM_WIDTH",
            "end_radius": "END_RADIUS"
        })
        require_ok(r, "draw_rounded_rectangle 10")

        # Step 11: extrude_from_sketch Z
        print("\n[STEP 11] extrude_from_sketch...")
        r = send_command(sock, "extrude_from_sketch", {
            "sketch_name": "last",
            "direction": "Z",
            "start": 0.0,
            "distance": "ARM_THICKNESS"
        })
        require_ok(r, "extrude_from_sketch 11")

        # Step 12: boolean_unite top arm with boss/bottom-arm
        print("\n[STEP 12] boolean_unite...")
        r = send_command(sock, "boolean_unite", {
            "target": "last",
            "tool": "body_3"
        })
        require_ok(r, "boolean_unite 12")

        # Step 13: add_hole_nx top arm
        print("\n[STEP 13] add_hole_nx...")
        r = send_command(sock, "add_hole_nx", {
            "target": "last",
            "x": "END_RADIUS",
            "y": 0.0,
            "z_offset": "ARM_THICKNESS + BOSS_HEIGHT",
            "diameter": "HOLE_DIA",
            "depth": "ARM_THICKNESS",
            "hole_type": "simple"
        })
        require_ok(r, "add_hole_nx 13")

        # Step 14: edge_blend vertical
        print("\n[STEP 14] edge_blend vertical...")
        r = send_command(sock, "edge_blend", {
            "body": "last",
            "edges": "vertical_edges",
            "radius": "FILLET_R"
        })
        require_ok(r, "edge_blend 14")

        # Step 15: edge_blend top
        print("\n[STEP 15] edge_blend top...")
        r = send_command(sock, "edge_blend", {
            "body": "last",
            "edges": "top_edges",
            "radius": "FILLET_R"
        })
        require_ok(r, "edge_blend 15")

        # Step 16: edge_blend bottom
        print("\n[STEP 16] edge_blend bottom...")
        r = send_command(sock, "edge_blend", {
            "body": "last",
            "edges": "bottom_edges",
            "radius": "FILLET_R"
        })
        require_ok(r, "edge_blend 16")

        # Step 17: Save
        print("\n[STEP 17] save_part...")
        r = send_command(sock, "save_part", {})
        require_ok(r, "save_part")

        print("\n" + "="*60)
        print("SUCCESS: offset_link_bracket.prt created successfully!")
        print(f"Path: {OUTPUT_PATH}")
        print("="*60)

    finally:
        try:
            print("\n[FINALLY] Saving part for debugging...")
            send_command(sock, "save_part", {})
        except Exception:
            pass
        try:
            sock.close()
        except Exception:
            pass

if __name__ == "__main__":
    main()
