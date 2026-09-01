# Workflow & Request Lifecycle

## Overview

This document traces the complete execution lifecycle of CAD operations in NX-MCP across the network, server, process runner, socket bridge, and native Siemens NX CAD engine.

---

## Complete End-to-End Flow Diagram

```
┌─────────────────┐
│    AI Client    │
└────────┬────────┘
         │ 1. JSON-RPC 2.0 stdio: {"method":"tools/call", "params":{"name":"create_cuboid", "arguments":{...}}}
         ▼
┌─────────────────┐
│    server.py    │ ── 2. Parses line, validates method, checks escape hatch, resolves ToolRegistry
└────────┬────────┘
         │ 3. modeling.py: create_cuboid(**args)
         ▼
┌─────────────────┐
│   _common.py    │ ── 4. _bridge_result() -> runner.call_nx("create_cuboid", args)
└────────┬────────┘
         │ 5. Acquires _lock, verifies NX environment, verifies socket 43210
         ▼
┌─────────────────┐
│    runner.py    │ ── 6. Transmits JSON line over TCP: {"tool":"create_cuboid", "args":{...}}\n
└────────┬────────┘
         │ 7. TCP Loopback Socket (127.0.0.1:43210)
         ▼
┌─────────────────┐
│  nx_bridge.py   │ ── 8. select.select() event loop inside ugraf.exe receives stream
└────────┬────────┘
         │ 9. handle_line(): Captures state backup snapshot -> dispatch() -> parameter normalization
         ▼
┌─────────────────┐
│  NXOpen Handler │ ── 10. _ensure_work_part() -> Create Expressions -> BlockFeatureBuilder -> Commit -> Destroy -> Save
└────────┬────────┘
         │ 11. Returns {"ok": true, "message": "Cuboid created", "filepath": "..."}\n over socket
         ▼
┌─────────────────┐
│    runner.py    │ ── 12. Receives result, writes latest_nx_result.txt, generates open_current_nx_result.cmd
└────────┬────────┘
         │ 13. Returns result dict to tool wrapper -> wrapped as ToolResult
         ▼
┌─────────────────┐
│    server.py    │ ── 14. Serializes JSON-RPC response: {"jsonrpc":"2.0", "result":{"content":[{"type":"text","text":"OK: ..."}]}}
└────────┬────────┘
         │ 15. stdio stdout flush
         ▼
┌─────────────────┐
│    AI Client    │
└─────────────────┘
```

---

## Detailed Execution Phases

### Phase 1: AI Client to Server Transport

1. **Protocol Handshake**:
   - Client sends: `{"jsonrpc":"2.0", "id":0, "method":"initialize", "params":{...}}`.
   - Server returns: protocol version `2024-11-05` and capabilities `{"tools":{}}`.
   - Client sends notification: `{"method":"notifications/initialized"}`.

2. **Tool Discovery (`tools/list`)**:
   - If routing is enabled (`NX_MCP_ENABLE_ROUTING=1`), `router.py` filters tool schemas based on the client's prompt context.
   - Client receives a focused JSON Schema list (typically 30-45 tools instead of 141).

3. **Tool Invocation (`tools/call`)**:
   - Client transmits JSON-RPC request over `stdin`:
     ```json
     {
       "jsonrpc": "2.0",
       "id": 1,
       "method": "tools/call",
       "params": {
         "name": "create_cylinder",
         "arguments": {"diameter": 50.0, "height": 100.0, "axis": "Z"}
       }
     }
     ```

---

## Specialized Execution Workflows

### 1. The Multi-Step Recipe Workflow (`run_recipe`)

When a complex CAD model requires multiple sequential features (e.g. Base Block → Extrude Cut → Fillet → Hole Pattern), using `run_recipe` executes all steps server-side in a single round-trip:

```json
{
  "name": "run_recipe",
  "arguments": {
    "steps": [
      {"tool": "create_part", "args": {"filename": "mounting_bracket.prt"}},
      {"tool": "create_cuboid", "args": {"length": 100, "width": 60, "height": 20, "centered": true}},
      {"tool": "add_hole", "args": {"x": 35, "y": 20, "z": 10, "diameter": 8, "depth": 20}},
      {"tool": "add_hole", "args": {"x": -35, "y": 20, "z": 10, "diameter": 8, "depth": 20}},
      {"tool": "add_fillet", "args": {"radius": 3.0, "edge_reference": "vertical_edges"}}
    ],
    "stop_on_error": true
  }
}
```

**Benefits**:
- Eliminates client-server network roundtrips for each individual feature.
- Deterministic sequential execution.
- Returns detailed step-by-step completion logs with precise failure step index if any error occurs.

---

### 2. The Custom Mathematical Journaling Workflow (`run_nx_journal_code`)

For advanced mathematically defined geometry (involute gear teeth, aerodynamic airfoils, cam profiles):
1. The AI agent generates pure Python NXOpen code.
2. Injects variables automatically: `SESSION`, `UF_SESSION`, `work_part`, `NXOpen`, `Point3d`, `Vector3d`, `Null`, `math`.
3. Calls `run_nx_journal_code(code=...)`.
4. Executed inside the live socket bridge with standard output captured and returned.

---

## Error Handling and Recovery Flow

```
Tool Execution Failure (e.g. Invalid Geometry or Constraint Failure)
  │
  ├─ 1. In-NX Bridge Catches Exception in handle_line()
  ├─ 2. Automatically rolls back _state to pre-call snapshot
  ├─ 3. Returns {"ok": false, "error": "Unable to create blend on target edge"}
  ├─ 4. runner.py returns result dict to tool wrapper
  ├─ 5. Tool wrapper returns ToolError / error message
  ├─ 6. server.py sends {"content": [{"type": "text", "text": "ERROR: Unable to create blend..."}]}
  └─ 7. AI agent reads error and chooses alternative parameter or edge reference
```

---

## Related Documentation

- [architecture.md](architecture.md) — 3-layer architecture map.
- [bridge.md](bridge.md) — Socket bridge implementation and dispatch.
- [state.md](state.md) — State dictionary and rollback mechanics.
- [parametric.md](parametric.md) — Parametric feature generation and expression editing.
