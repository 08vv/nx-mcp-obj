import json
from nx_mcp.tools.registry import mcp_tool, ToolRegistry
from nx_mcp.router import route, get_spec_vocabulary

@mcp_tool(
    name="get_relevant_nx_tools",
    description=(
        "Always call this tool FIRST with a description of what you are trying to do in NX. "
        "It returns a filtered, highly relevant list of NX tool schemas for your specific task. "
        "Because there are over 150 tools available, calling this tool first will save token "
        "space and help you pick the right tools without guessing. Provide your exact task goal "
        "in the 'request_text' parameter to get the best matches. Set include_spec_vocabulary=True "
        "if you plan to author a structured CAD Spec (run_spec) JSON document."
    ),
)
def get_relevant_nx_tools(request_text: str, include_spec_vocabulary: bool = False) -> str:
    """
    Args:
        request_text (str): A natural language description of your current goal or task in NX 
            (e.g., 'draw a rectangle and extrude it', or 'measure the distance').
        include_spec_vocabulary (bool): If True, includes relevant CAD Spec operations and $fn: geometry math functions.

    Returns:
        JSON string of the filtered tool schemas, matched categories, and optional spec vocabulary.
    """
    routed = route(request_text)
    matched_names = set()
    for cat in routed["categories"]:
        matched_names.update(cat["tools"])
        
    all_tools = ToolRegistry.list_tools()
    
    # If it's a fallback (unrelated prompt), return all tools except the discovery tool itself
    if routed["is_fallback"]:
        filtered_tools = [t for t in all_tools if t["name"] != "get_relevant_nx_tools"]
    else:
        filtered_tools = [
            t for t in all_tools 
            if t["name"] in matched_names and t["name"] != "get_relevant_nx_tools"
        ]
    
    result = {
        "matched_categories": [c["name"] for c in routed["categories"]],
        "is_fallback": routed["is_fallback"],
        "total_returned": len(filtered_tools),
        "tools": filtered_tools
    }
    if include_spec_vocabulary:
        result["spec_vocabulary"] = get_spec_vocabulary(request_text)
    return json.dumps(result, indent=2)

