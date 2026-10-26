# OBJ-to-Parametric NX — Agent Rules

## Input Contract
- The ONLY input to this system is a **Wavefront OBJ file path**.
- Do NOT expect text prompts describing what to build. The geometry IS the specification.
- Do NOT expect images, sketches, or any other input format.

## Execution Architecture
- The core relay chain is: **Agent → server.py → runner.py → nx_bridge.py → Siemens NX**
- The agent drives the process by calling MCP tools or executing Python scripts via `run_journal.exe`.
- Tool routing is DISABLED (`NX_MCP_ENABLE_ROUTING=0`) — all tools are always available.
- Do NOT modify `server.py`, `runner.py`, `nx_bridge.py`, or any file under `src/nx_mcp/tools/`.

## Mandatory First Step
Before building anything in NX, ALWAYS run the mesh analyzer first:
```bash
python analyze_obj.py <obj_file> --output <name>_analysis.json
```
Use the structured JSON output to plan the parametric feature tree before issuing any NX tool calls.

## Scale Convention
- OBJ files are unitless. Inspect the bounding box extents from the analyzer output.
- If extents are O(1) (e.g. 0.5–5.0), assume the OBJ is in meters and scale ×1000 for NX (millimeters).
- If extents are O(100) (e.g. 50–500), assume the OBJ is already in millimeters.
- When uncertain, ask the user.

## Part Persistence
- `create_part()` creates an in-memory NX session part ONLY.
- `save_part()` is MANDATORY as the final step of every build — the `.prt` file does not exist on disk until this is called.
- ALWAYS update `open_current_nx_result.cmd` and `latest_nx_result.txt` after saving so the user can inspect the result with a single click.

## MANDATORY: Genuine Feature-Based Parametric CAD Architecture
- **NEVER use a single monolithic `Through Curves` loft as the whole CAD model.**
  - Slicing an entire mesh into 30–50 polygon loops produces thousands of faceted corrugated patches, uneditable geometry, and overlapping selection artifacts in the NX Part Navigator.
  - Slicing an entire body into one command is strictly FORBIDDEN.
- **Decompose the object into real, distinct, individually editable CAD features**:
  1. **Base Stock Body**: Built with native CAD features (`Block`, `Extrude`, or `Revolve`), driven by explicit expressions (`BODY_LENGTH`, `BODY_WIDTH`, `BODY_HEIGHT`).
  2. **Primary Form Cutouts & Recesses**: Built with native boolean operations (`Cylinder` subtracts for concave waists, `Block` subtracts for stepped shelves/pockets), each independently selectable and editable in the Part Navigator.
  3. **Analytical Sub-Features**: Necks, caps, spouts, collars, and bosses must be built with native CAD features (`Cylinder`, `Extrude`, `Revolve`, `Pattern`) with Boolean Unite — NEVER approximated as sliced loft rings.
  4. **Corner & Transition Fillets**: Built with `CreateEdgeBlendBuilder` chained to expressions (`CORNER_BLEND_R`, `PERIMETER_BLEND_R`, `SHELF_BLEND_R`).
  5. **Clean Display**: All construction wireframes/curves must be blanked (`c.Blank()`) so the graphics window displays a clean, smooth, shaded solid body.
- **True Editability**: Every feature in the Part Navigator must be double-clickable to edit its parameters directly in NX, and all dimensions must be tied to associative **User Expressions**.
