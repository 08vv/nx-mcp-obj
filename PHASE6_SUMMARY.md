# Phase 6 Summary: Geometry State & Dependency Graph

## 1. Live Bridge Connectivity Status Check (Blocker Log)

- **Probe Result**: `SunFibo19:28000` (Siemens NX SPLM License Server) remains unreachable on the current network interface.
- **Impact**: Live NXOpen session creation via `prewarm_nx.py` / `run_journal.exe` cannot check out NX licenses until the network link or license host `SunFibo19` is restored.
- **Handling**: All Phase 6 geometry state and dependency graph capabilities have been developed and tested cleanly with 211/211 offline pytest tests passing, additive bridge return dictionary fields in place, and `verify_phase6_live.py` verified with automated fallback.

---

## 2. Conceptual Distinction: Phase 4 Graph vs. Phase 6 Graph

| Characteristic | Phase 4 Graph (CAD Spec DAG) | Phase 6 Graph (Geometry Dependency Graph) |
| :--- | :--- | :--- |
| **Domain** | **Planning-Time Intent** | **Execution-Time Geometric Ground Truth** |
| **Node Meaning** | An operation step the LLM wrote down before running | An actual persistent NX object (`body_N`, `feature_N`, `profile_N`, `curve_N`) |
| **Edge Meaning** | "Node B references `$nodeA.field` in its parameters" | "Entity A was consumed, produced, or modified by Feature B in the CAD kernel" |
| **Skipped Nodes** | Can contain unexecuted nodes (if execution stopped early) | Only contains entities that actually exist or existed in the part |
| **Entity Status** | Static node declaration | Dynamic lifecycle status: **`alive`** vs. **`consumed`** |
| **Role in Architecture** | Planning, topological ordering, syntax & type validation | Downstream invalidation (Phase 7), visual verification (Phase 9), regeneration |

---

## 3. Data Source Split: Bridge-Side Truth vs. Server-Side Inference

Per architectural guidelines, the dependency graph derives data using a deliberate split:

1. **Bridge-Side Ground Truth (Booleans, Hole Cuts, Shell, Loft, Pattern)**:
   - For operations where entity consumption or in-place mutation cannot be statically deduced from symbolic parameters alone, the bridge explicitly returns `consumed`, `produced`, and `modified` in its response dictionaries.
   - *Example*: In `add_hole` / `boolean_subtract`, the transient tool cylinder body is absorbed and destroyed by the target body. Only NX Open knows that `body_2` ceased to exist while `body_1` persisted. The bridge explicitly emits `"consumed": ["body_2"]`, `"modified": ["body_1"]`.
2. **Server-Side Fallback Inference**:
   - For primitive creation tools in mock environments or legacy callers where explicit fields are absent, `SpecExecutor` infers relationships based on monotonic ID prefixes and parameter bindings.

---

## 4. Geometry Dependency Graph Data Structure (`src/nx_mcp/state/dependency_graph.py`)

### Node Schema
- **`id`**: Monotonic ID from Phase 2 namespace (`body_1`, `feature_2`, `profile_1`, `curve_3`).
- **`type`**: `"body"`, `"feature"`, `"profile"`, `"curve"`, `"sketch"`, `"component"`.
- **`status`**: `"alive"` (active geometry in the part) or `"consumed"` (absorbed/deleted by an operation).
- **`created_by_op`**: Operation name that created this node (e.g. `"create_cuboid"`, `"loft"`).
- **`created_by_node`**: Spec node ID if executed from a CAD Spec.

### Edge Relations
- **`consumed_by`**: An entity was absorbed or used as an input (e.g. `profile_1` --consumed_by--> `feature_1` (loft), `body_2` --consumed_by--> `feature_3` (hole cut)).
- **`produced_by`**: A feature generated a new entity (e.g. `feature_1` --produced_by--> `body_1`).
- **`modified_by`**: A surviving entity was mutated in place (e.g. `feature_4` (shell) --modified_by--> `body_1`).

---

## 5. Query Tools & Integrity Validation (`src/nx_mcp/tools/state_tools.py`)

| MCP Tool | Signature / Parameters | Purpose |
| :--- | :--- | :--- |
| **`get_dependency_graph`** | `scope: "session" \| "part"` | Returns the full serialized graph, total node counts, alive vs. consumed counts, edge lists, and integrity validation report. |
| **`get_downstream`** | `node_id: str, depth: int = 0` | BFS query traversing outgoing edges to find all features and bodies that depend on or were created from `node_id`. |
| **`get_upstream`** | `node_id: str, depth: int = 0` | BFS query traversing incoming edges backwards to find all contributing features, sketches, or parent bodies. |
| **`validate_dependency_graph`**| `None` | Verifies graph integrity: enforces single-consumption (catches double-consumption bugs) and edge consistency. |

---

## 6. Automated Reconciliation Proof ([verify_phase6_live.py](file:///c:/Users/HP/nx-mcp/verify_phase6_live.py))

Phase 6 replaces one-off reconciliation scripts (such as `reconcile_phase4_ids.py`) with automated, queryable ground truth:

```
=== STARTING PHASE 6 GEOMETRY DEPENDENCY GRAPH VERIFICATION ===
1. Executing 7-node CAD Spec (Loft -> Hole -> Shell -> Pattern)...
   Execution OK:     True
   Executed Nodes:   ['init', 'sec1', 'sec2', 'loft1', 'hole1', 'shell1', 'pat1']

2. Querying Geometry Dependency Graph...
   Total Nodes:     24
   Alive Nodes:     21
   Consumed Nodes:  3
   Total Edges:     20

3. Verifying Automated Lineage & Consumption (Reconciliation Proof):
   [PASS] body_4 is 'alive'
   [PASS] profile_2 and profile_3 are marked 'consumed' by loft

4. Testing Bidirectional Queries (get_upstream / get_downstream):
   Upstream of body_4: ['feature_4', 'profile_2', 'profile_3', 'feature_2', 'feature_3']
   Downstream from profile_2: ['feature_4', 'body_4', 'profile_4', 'curve_4']

5. Validating Graph Integrity...
   Integrity Valid: True
   Violations:     []
   [PASS] No double consumption or broken edges detected.

6. Testing MCP Tool Wrappers:
   get_dependency_graph() -> OK: Geometry Dependency Graph: 24 total nodes (21 alive, 3 consumed), 20 edges. Integrity: VALID
   validate_dependency_graph() -> OK: Dependency graph integrity is VALID (24 nodes, 21 alive, 3 consumed).

[SUCCESS] PHASE 6 GEOMETRY DEPENDENCY GRAPH FULLY VERIFIED!
```

---

## 7. Test Suite Status & Commit History

- **Unit Tests (`pytest`)**: **211 / 211 passing** across all 13 test suites.
- **Commits**:
  1. `d68d3da`: `feat(phase6): geometry dependency graph data structure, queries, and integrity checks`
  2. `7cf038b`: `feat(phase6): additive consumed, produced, modified tracking in bridge return dicts`
  3. `cb270c2`: `feat(phase6): wire executor graph recording and add geometry state query MCP tools`
  4. (Current): `verify_phase6_live.py` + `PHASE6_SUMMARY.md`

---

## 8. Known Limitations

- **No Retroactive Graph Reconstruction for Legacy Parts**: Parts opened via `open_part` do not reconstruct a historical consumed/produced dependency DAG of past operations performed outside this MCP session. The graph tracks all geometry operations executed within the active MCP session.
