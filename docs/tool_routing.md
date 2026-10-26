# Tool Routing & Discovery

## Overview

The NX-MCP server exposes **154 registered tools** across the entire parametric CAD modeling workflow. Exposing all 154 tool schemas on every turn would consume upwards of 30,000 prompt tokens.

To optimize context window efficiency without limiting agent capability, NX-MCP provides three complementary mechanisms:
1. **Dynamic Tool Router (`src/nx_mcp/router.py`)**: A fast, deterministic keyword-scoring layer that filters `tools/list` responses down to relevant CAD categories.
2. **Discovery Tool (`get_relevant_nx_tools` in `discovery.py`)**: An explicit tool that an AI agent can call with its task prompt to obtain a focused subset of tool schemas and optional CAD Spec vocabulary.
3. **Spec Vocabulary Router (`get_spec_vocabulary` in `router.py`)**: Filters relevant CAD Spec `op` values and `$fn:` geometry math functions for authoring structured `run_spec` graphs.

---

## Routing Architecture

```
User / Agent Prompt
         │
         ▼
┌──────────────────┐
│  src/nx_mcp/     │
│  router.py       │ ── Tokenize ──▶ Keyword Match ──▶ Score Categories
└────────┬─────────┘
         │ Matched category tool names (e.g. 30-45 tools)
         ▼
┌──────────────────┐
│  src/nx_mcp/     │
│  server.py       │ ── Filters ToolRegistry.list_tools()
└────────┬─────────┘
         │
         ├─ Normal Flow: Returns filtered tool schemas
         │
         └─ Escape Hatch Flow: If client calls an unexposed tool,
            _session_state["escape_hatch_active"] is set to True,
            re-exposing all 154 tools immediately.
```

---

## Scoring Algorithm

### Step 1: Tokenization
The input prompt is converted to lowercase and cleaned of punctuation.

### Step 2: Weighted Keyword Matching
Keywords are categorized as single words or multi-word phrases:
- **Single-word keyword**: Weight = `1.0` (e.g. `"extrude"`, `"fillet"`, `"sketch"`, `"cylinder"`).
- **Multi-word phrase**: Weight = `2.0` (e.g. `"edge blend"`, `"through curves"`, `"bolt circle"`, `"create part"`).

Multi-word phrases are matched first (sorted longest-first) to prevent constituent single words from being double-counted.

### Step 3: Raw Category Scoring
For each category:
$$\text{raw\_score} = \sum_{\text{matched keywords}} \text{weight}$$

### Step 4: Inclusion Gating
A category is included if:
$$\text{raw\_score} \ge \text{MIN\_RAW\_WEIGHT} \quad (\text{default } 1.0)$$
Any single keyword match qualifies the category.

### Step 5: Safety Fallback
If no category meets the threshold (e.g., completely unrecognized or abstract prompt), the router falls back to returning **all 154 tools**, ensuring no valid operations are blocked.

---

## The 8 Functional Categories (154 Tools Total)

| Category | Tools Count | Scope / Key Tools |
|---|:---:|---|
| **Modeling** | 34 | Primitives (`create_cuboid`, `create_cylinder`, `create_cube`, `create_tube`), booleans (`unite`, `subtract`, `combine`), `loft`, `shell`, `extrude`, `revolve`, `add_fillet`, `add_chamfer`, `add_hole`, `add_hole_nx`, `pattern_circular`, `pattern`, `create_rib`, `create_expression`, `edit_expression`, `list_expressions` |
| **Sketch** | 16 | 2D sketch plane, lines, rectangles, rounded rectangles, circles, splines (`draw_spline`), curve offset (`offset_curve`), closed regions (`close_curve_region`), `create_profile`, `polar_to_cartesian_points`, sketch constraints (`fixed`, `horizontal`, `vertical`) |
| **Surface Modeling** | 52 | Studio surface, sweeps, through-curves, ruled, n-sided, fill, bounded plane, trims, sheets, thicken, extensions, face blends, sew/unsew |
| **Edit Operations** | 17 | Freeform editing: X-Form, I-Form, match edge, heal surface, normal reversal, enlarge face, deformation, shaping, smoothing, variable offset |
| **File Operations** | 6 | `create_part`, `open_part`, `save_part`, `save_part_as`, `export_step`, `export_stl` |
| **Measurement** | 5 | `measure_distance`, `measure_angle`, `measure_volume`, `measure_body_volume`, `get_bounding_box` |
| **Assembly** | 4 | `add_component`, `list_components`, `mate_components`, `reposition_component` |
| **Utility & State** | 20 | Viewport (`set_view`, `fit_view`), screenshot (`take_screenshot`), inspection (`list_features`, `list_feature_edges`, `inspect_part`, `inspect_api`, `get_active_part`), bridge control (`reset_nx_bridge`), journal execution (`run_nx_journal_code`), recipes & specs (`run_recipe`, `run_spec`, `resume_spec`, `rerun_spec_node`), dependency graph (`get_dependency_graph`, `get_downstream`, `get_upstream`, `validate_dependency_graph`), discovery (`get_relevant_nx_tools`) |

---

## Spec Vocabulary Routing (`get_spec_vocabulary`)

When drafting a structured `CADSpec` graph (executed via `run_spec`), local models benefit from seeing only relevant operation names and deterministic geometry-math `$fn:` helpers rather than all 154 tool descriptions.

Calling `get_relevant_nx_tools(request_text, include_spec_vocabulary=True)` returns:
- `relevant_ops`: Filtered list of operation names legal in spec nodes (reusing the category mappings, avoiding schema forks).
- `relevant_fn_functions`: Filtered list of `$fn:` helpers (`bolt_circle`, `polar_to_cartesian`, `linear_spacing`, `lerp`, `deg_to_rad`, `rad_to_deg`) mapped from task intent.

---

## The Server Escape Hatch

If an AI agent decides to call a tool that was omitted from the routed list (e.g. calling `measure_distance` during a modeling task where measurement wasn't in the initial prompt):
1. `server.py` checks `_session_state["active_routed_tool_names"]`.
2. Detects the tool call outside the active subset.
3. Sets `_session_state["escape_hatch_active"] = True`.
4. Successfully executes the requested tool.
5. Emits an info log and expands the tool list to all 154 tools for subsequent interactions.

---

## Performance & Token Impact

- **Routing Latency**: `< 0.05 ms` per invocation.
- **Average Tool Count**: Reduced from 154 down to ~35–45 tools per turn.
- **Token Efficiency**: Saves approximately 20,000 to 24,000 prompt tokens per interaction.

---

## Related Documentation

- [tool_registry.md](tool_registry.md) — Tool registration and reflection schemas.
- [cad_spec_system.md](cad_spec_system.md) — Declarative CAD Spec DAG engine.
- [architecture.md](architecture.md) — System architecture overview.
- [workflow.md](workflow.md) — Request and execution workflow.
