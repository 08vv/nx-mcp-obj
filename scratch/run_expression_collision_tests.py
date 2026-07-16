import json
import socket
import time
import sys
import os
import subprocess
from pathlib import Path

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
            time.sleep(2)
    raise RuntimeError(f"Could not connect to NX bridge after {max_wait}s")

def launch_nx_bridge_if_needed():
    """Launch NX GUI with the bridge script if the socket is not yet open."""
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
    bridge_script = str(Path(__file__).parent.parent / "src" / "nx_mcp" / "bridge" / "nx_bridge.py")

    # Write the live bridge config
    config_path = Path(__file__).parent.parent / "live_bridge_config.json"
    config_path.write_text(json.dumps({"part_path": "", "port": BRIDGE_PORT}), encoding="utf-8")

    subprocess.Popen([ugraf_exe, f"-auto={bridge_script}"])
    print(f"[INFO] NX launched. Waiting for bridge socket on port {BRIDGE_PORT}...")

def run_tests():
    launch_nx_bridge_if_needed()
    sock = connect_to_bridge(max_wait=90)

    results = {}

    try:
        # ==========================================
        # 1. TEST CASE: Cuboids
        # ==========================================
        print("\n--- Testing create_cuboid ---")
        send_command(sock, "create_part", {"filename": "C:/Users/HP/nx-mcp/test_collision_cuboids.prt"})
        
        print("Creating Cuboid 1 (100x20x5)...")
        r1 = send_command(sock, "create_cuboid", {"length": 100.0, "width": 20.0, "height": 5.0, "x": 0.0, "y": 0.0, "z": 0.0})
        print(f"Response 1: {r1}")
        
        print("Creating Cuboid 2 (40x40x40)...")
        r2 = send_command(sock, "create_cuboid", {"length": 40.0, "width": 40.0, "height": 40.0, "x": 200.0, "y": 0.0, "z": 0.0})
        print(f"Response 2: {r2}")
        
        diagnostics_cuboids = send_command(sock, "get_diagnostics", {})
        results["cuboids"] = diagnostics_cuboids
        print(f"Cuboids diagnostics: {json.dumps(diagnostics_cuboids, indent=2)}")

        # ==========================================
        # 2. TEST CASE: Cylinder
        # ==========================================
        print("\n--- Testing create_cylinder ---")
        send_command(sock, "create_part", {"filename": "C:/Users/HP/nx-mcp/test_collision_cylinders.prt"})
        
        print("Creating Cylinder 1 (radius=10.0, height=30.0)...")
        r1 = send_command(sock, "create_cylinder", {"radius": 10.0, "height": 30.0, "x": 0.0, "y": 0.0, "z": 0.0})
        print(f"Response 1: {r1}")
        
        print("Creating Cylinder 2 (radius=25.0, height=50.0)...")
        r2 = send_command(sock, "create_cylinder", {"radius": 25.0, "height": 50.0, "x": 200.0, "y": 0.0, "z": 0.0})
        print(f"Response 2: {r2}")
        
        diagnostics_cylinders = send_command(sock, "get_diagnostics", {})
        results["cylinders"] = diagnostics_cylinders
        print(f"Cylinders diagnostics: {json.dumps(diagnostics_cylinders, indent=2)}")

        # ==========================================
        # 3. TEST CASE: Cube
        # ==========================================
        print("\n--- Testing create_cube ---")
        send_command(sock, "create_part", {"filename": "C:/Users/HP/nx-mcp/test_collision_cubes.prt"})
        
        print("Creating Cube 1 (size=15.0)...")
        r1 = send_command(sock, "create_cube", {"size": 15.0, "x": 0.0, "y": 0.0, "z": 0.0})
        print(f"Response 1: {r1}")
        
        print("Creating Cube 2 (size=35.0)...")
        r2 = send_command(sock, "create_cube", {"size": 35.0, "x": 200.0, "y": 0.0, "z": 0.0})
        print(f"Response 2: {r2}")
        
        diagnostics_cubes = send_command(sock, "get_diagnostics", {})
        results["cubes"] = diagnostics_cubes
        print(f"Cubes diagnostics: {json.dumps(diagnostics_cubes, indent=2)}")

        # ==========================================
        # 4. TEST CASE: Offset Linkage Arm
        # ==========================================
        print("\n--- Testing create_offset_linkage_arm ---")
        send_command(sock, "create_part", {"filename": "C:/Users/HP/nx-mcp/test_collision_arms.prt"})
        
        print("Creating Offset Linkage Arm 1...")
        r1 = send_command(sock, "create_offset_linkage_arm", {})
        print(f"Response 1: {r1}")
        
        print("Creating Offset Linkage Arm 2...")
        r2 = send_command(sock, "create_offset_linkage_arm", {})
        print(f"Response 2: {r2}")
        
        diagnostics_arms = send_command(sock, "get_diagnostics", {})
        results["arms"] = diagnostics_arms
        print(f"Arms diagnostics: {json.dumps(diagnostics_arms, indent=2)}")

        # Save output to json
        out_path = Path(__file__).parent / "collision_test_raw_results.json"
        out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\nSaved raw results to {out_path}")

    finally:
        sock.close()

if __name__ == "__main__":
    run_tests()
