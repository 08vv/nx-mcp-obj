# PHASE 2: MCP CLIENT-AGNOSTIC COMPLIANCE AUDIT

## 1. MCP SPEC CHECK
* Ran `npx @modelcontextprotocol/inspector` against `nx-mcp.server`.
* No warnings or errors were flagged by the inspector regarding schema violations or payload formatting. (The server implements the standard `ToolRegistry` and exposes valid `inputSchema` dictionaries for all registered tools).

## 2. CLIENT-SPECIFIC LANGUAGE SCAN
* **Result:** No client-specific language found. 
* Scanned all tool docstrings in `src/nx_mcp/tools/*.py` for agent-specific terms (e.g., "Cline", "cursor", "LLM", "agent", "previously", "step", "remember"). 
* All docstrings are written cleanly using neutral, mechanical engineering terminology (e.g., "previously sewn sheet boundaries").

## 3. HIDDEN STATE CHECK
* **Affected Tools:** `create_cuboid`, `create_cylinder`, `extrude`, `revolve`, `add_hole`, `add_fillet`, `chamfer`, `create_rib`, `pattern_circular`.
  * **Hidden Dependency:** These tools generate parametric NX expression names (e.g., `CUBOID_1_L`) based on an internal, auto-incrementing server counter (`_instance_counters`), making it impossible for the client to deterministically know the expression name to edit later without scraping text responses.
* **Affected Tools:** `boolean_unite`, `boolean_subtract`, `add_fillet`, `add_chamfer`, `add_hole`, `mirror_feature`, `pattern_feature`, `extrude_cut`, `revolve_cut`.
  * **Hidden Dependency:** These tools default their `target` or `body` arguments to `"last"`, which implicitly relies on the server's hidden global tracking of the most recently created body/feature (`_state["last_body"]`), a state entirely opaque to a fresh client.

## 4. ERROR FORMAT CHECK
* **Tool:** `create_cuboid` (Bad Input: length=-10)
  * Raw Output: `{"content": [{"type": "text", "text": "ERROR: Cuboid dimensions must be positive"}], "isError": true}`
* **Tool:** `boolean_combine` (Bad Input: fake_body_123)
  * Raw Output: `{"content": [{"type": "text", "text": "ERROR: fatal error\nrun_journal: failed to initialize UFUN 949804\n"}], "isError": true}`
* **Tool:** `open_part` (Bad Input: C:\fake\path.prt)
  * Raw Output: `{"content": [{"type": "text", "text": "ERROR: fatal error\nrun_journal: failed to initialize UFUN 949804\n"}], "isError": true}`
