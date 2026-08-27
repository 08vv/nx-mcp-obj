# Phase 4 Summary: CAD Spec / Operation Graph

## 1. Overview & Architectural Role

Phase 4 introduces an intermediate validation and planning layer between LLM intent and NX tool execution:

$$\text{User / Intent} \longrightarrow \text{LLM} \longrightarrow \mathbf{\text{CAD Spec (Operation Graph)}} \longrightarrow \mathbf{\text{Validator}} \longrightarrow \mathbf{\text{Executor}} \longrightarrow \text{NX Tools (via Bridge)}$$

Rather than emitting ad-hoc tool calls or static step lists where the LLM is forced to guess monotonic object identifiers ahead of time (`body_1`, `feature_3`, etc.), the LLM authors a structured Directed Acyclic Graph (DAG) with **symbolic reference links** (e.g. `"$loft_body.body_id"`). The deterministic executor topologically sorts the graph, executes nodes, and dynamically substitutes real resolved runtime IDs into downstream operations.

---

## 2. Schema Design Decisions

- **Node Structure**:
  - `id` (str): Unique node identifier (e.g. `"n1"`, `"loft_mount"`).
  - `op` (str): Operation name matching any tool in `ToolRegistry.all()`.
  - `params` (dict): Parameter key-value pairs supporting literals, symbolic node references, expression references, and reserved calc references.
  - `depends_on` (list): Explicit and auto-inferred dependency node IDs.
  - `produces` (dict): Output mapping resolved dynamically at execution time.
- **Reference Grammar**:
  1. **Node Output Reference**: `"$<node_id>.<field_name>"` (e.g. `"$sec1.profile_id"`, `"$base.body_id"`, `"$cut.feature_id"`).
  2. **NX Expression Reference**: `"$expr:<EXPRESSION_NAME>"` (e.g. `"$expr:CUBOID_1_L"`).
  3. **Calculation Reference (Reserved for Phase 5)**: `"$calc:<expression>"`.
- **Automatic Dependency Inference**:
  When a node's parameters contain symbolic references like `"$base.body_id"`, `SpecNode.from_dict()` automatically populates `"base"` into `depends_on`, freeing the LLM from manual graph bookkeeping.

---

## 3. Reserved `$calc:...` Syntax Contract for Phase 5

- **Grammar**: Any parameter value prefixed with `"$calc:"` represents a deterministic server-side mathematical expression (e.g. `"$calc:100 * sin(pi/4)"`, `"$calc:$n1.width / 2"`).
- **Phase 4 Handling**:
  - *Validator*: Accepts `"$calc:..."` as structurally valid syntax (non-empty expression required).
  - *Executor*: Rejects `"$calc:..."` at runtime with an explicit error: `"Calculation reference '$calc:...' is reserved for Phase 5 deterministic math layer and cannot be evaluated in Phase 4."`
- **Phase 5 Contract**: Phase 5 will implement the evaluation engine for `$calc:` expressions without requiring any schema version bump or breaking grammar changes.

---

## 4. Execution Granularity: Atomic vs. Interruptible

- **Decision**: Implemented **(a) ATOMIC** execution as the public MCP interface (`run_spec`), with an internally **(b) RESUMABLE / STEPPABLE** engine (`SpecExecutor.execute_next_node()`).
- **Rationale**:
  - Atomic execution matches `run_recipe`'s clean client lifecycle and ensures single-turn transaction boundaries.
  - Structuring `SpecExecutor` as a stateful step machine internally (`has_next()`, `execute_next_node()`, `symbol_table`) ensures zero architectural rework when Phase 9 introduces intermediate geometric inspection and visual verification pauses.

---

## 5. Validation Rules Implemented (Offline / Pre-Flight)

The static validator (`src/nx_mcp/spec/validator.py`) runs 100% offline without requiring NX:
1. **DAG Structure & Cycle Detection**: Kahn's algorithm validates cycle-free dependencies and derives topological execution order.
2. **Reference Resolution**:
   - Checks that referenced parent nodes exist in the spec.
   - Forbids illegal forward references (parent must precede child in topological order).
   - Validates that parent node `op` actually produces the referenced field (`KNOWN_OP_OUTPUTS`).
3. **Tool Existence**: Validates `node.op` dynamically against `ToolRegistry.all()`.
4. **Parameter Completeness & Types**: Validates required parameters (with alias tolerance e.g. `filepath` $\leftrightarrow$ `filename`, `target` $\leftrightarrow$ `body`) and checks literal parameter types against tool JSON schemas.
5. **Reserved Syntax Checks**: Enforces non-empty `$calc:` syntax.
6. **Structured Error Reporting**: Returns structured `ValidationError` records per node.

---

## 6. Relationship Between `run_spec` and `run_recipe`

- **`run_recipe` (Flat Step List)**: Coexists for simple, sequential, linear scripts where all parameters are known constants and no topological branching or reference resolution is needed.
- **`run_spec` (Operation Graph DAG)**: The primary high-level entry point for AI-driven CAD generation, featuring static DAG validation, dependency inference, and dynamic symbolic reference resolution.
- Neither tool replaces the other; `run_recipe` remains lightweight and backward-compatible, while `run_spec` provides robust graph-level orchestration.

---

## 7. Phase 3 Carry-Forward Risk Audit: Loft $\rightarrow$ Shell Lineage

- **Tested Scenario**: `sec1` + `sec2` (Profiles) $\rightarrow$ `loft_mount` (Through Curves) $\rightarrow$ `center_cut` (Hole) $\rightarrow$ `shell_mount` (Shell with top face removed) $\rightarrow$ `hole_pattern` (Circular Pattern).
- **Audit Findings**:
  - `loft` correctly registered `body_1` and `feature_1`.
  - `shell` resolved `"$loft_mount.body_id"` to `body_1` and hollowed the lofted body with `Tolerance=0.01` and top face removal.
  - `pattern` resolved `"$center_cut.feature_id"` and patterned the feature 4x around Z.
  - Proved that persistent object identity across loft, subtract, shell, and pattern seamlessly composes under graph execution.

---

## 8. Verification Results & Test Counts

- **Automated Unit Tests (`pytest`)**: **118 / 118 passed** (`tests/test_spec_validator.py`, `tests/test_spec_executor.py`, `tests/test_tools.py`, `tests/test_router.py`, etc.).
- **Live Integration Verification ([verify_phase4_live.py](file:///c:/Users/HP/nx-mcp/verify_phase4_live.py))**:
  - Executed 7-node CAD Spec against Siemens NX 2206.
  - 100% completed nodes (`status: "completed"`, `skipped_nodes: []`).
  - Successfully resolved all symbolic references into real NX body/feature IDs.
