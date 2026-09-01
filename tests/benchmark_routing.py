"""
Benchmark: measure routing effectiveness across 10 representative prompts.

Reports: average tools before vs after, routing latency, prompt-size reduction.
"""
import json
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nx_mcp.router import route, get_all_tool_names

TOTAL_TOOLS = len(get_all_tool_names())

# 10 representative test prompts: mix of single-category, multi-category, ambiguous
TEST_PROMPTS = [
    # 1. Single-category: Sketch
    "Draw a rectangle 100x50mm and add a circle at the center",
    # 2. Single-category: Modeling
    "Create a cuboid 40x25x20mm and add a 5mm fillet to all edges",
    # 3. Single-category: File Operations
    "Save the current part and export it as a STEP file",
    # 4. Single-category: Measurement
    "Measure the distance between point A and point B",
    # 5. Single-category: Surface Modeling
    "Create a swept surface along the guide curve and thicken it to 2mm",
    # 6. Multi-category: Sketch + Modeling
    "Sketch a rectangle, extrude it 30mm, then add fillets",
    # 7. Multi-category: Modeling + File Operations
    "Create a cylinder, subtract a hole from it, then export as STL",
    # 8. Multi-category: Sketch + Modeling + Measurement
    "Draw a circle, extrude it, then measure the volume",
    # 9. Ambiguous / Edit Operations
    "Heal the surface gaps and smooth the poles on the freeform body",
    # 10. Unknown / should trigger fallback
    "What is the meaning of life?",
]


def run_benchmark():
    results = []
    total_before = 0
    total_after = 0
    total_latency = 0.0

    print(f"{'#':>2} {'Prompt':60s} {'Before':>6} {'After':>5} {'Reduction':>9} "
          f"{'Latency':>8} {'Fallback':>8} Categories")
    print("-" * 140)

    for i, prompt in enumerate(TEST_PROMPTS, 1):
        result = route(prompt)

        before = TOTAL_TOOLS
        after = result["total_tools"]
        reduction_pct = ((before - after) / before) * 100 if before > 0 else 0
        latency = result["routing_time_ms"]
        is_fallback = result["is_fallback"]
        cats = [c["name"] for c in result["categories"] if c["score"] > 0]

        total_before += before
        total_after += after
        total_latency += latency

        results.append({
            "prompt": prompt,
            "before": before,
            "after": after,
            "reduction_pct": round(reduction_pct, 1),
            "latency_ms": round(latency, 3),
            "is_fallback": is_fallback,
            "categories": cats,
            "scores": {c["name"]: c["score"] for c in result["categories"]},
        })

        cats_str = ", ".join(cats) if cats else "(all - fallback)"
        print(f"{i:>2} {prompt[:58]:60s} {before:>6} {after:>5} {reduction_pct:>8.1f}% "
              f"{latency:>7.3f}ms {'YES' if is_fallback else 'no':>8} {cats_str}")

    n = len(TEST_PROMPTS)
    avg_before = total_before / n
    avg_after = total_after / n
    avg_latency = total_latency / n
    avg_reduction = ((avg_before - avg_after) / avg_before) * 100

    print("-" * 140)
    print(f"   {'AVERAGE':60s} {avg_before:>6.0f} {avg_after:>5.0f} {avg_reduction:>8.1f}% "
          f"{avg_latency:>7.3f}ms")

    # Approximate prompt-size reduction
    # Each tool schema is roughly 200 tokens (name + description + params)
    tokens_per_tool = 200
    avg_tokens_before = avg_before * tokens_per_tool
    avg_tokens_after = avg_after * tokens_per_tool
    token_savings = avg_tokens_before - avg_tokens_after

    print(f"\n--- Prompt Size Estimation ---")
    print(f"Estimated tokens per tool schema: ~{tokens_per_tool}")
    print(f"Average tokens before routing:    ~{avg_tokens_before:.0f}")
    print(f"Average tokens after routing:     ~{avg_tokens_after:.0f}")
    print(f"Average token savings per call:   ~{token_savings:.0f} ({avg_reduction:.1f}%)")

    # Write JSON results
    out_path = os.path.join(os.path.dirname(__file__), "..", "benchmark_results.json")
    summary = {
        "total_tools": TOTAL_TOOLS,
        "num_prompts": n,
        "avg_before": round(avg_before, 1),
        "avg_after": round(avg_after, 1),
        "avg_reduction_pct": round(avg_reduction, 1),
        "avg_latency_ms": round(avg_latency, 3),
        "tokens_per_tool_estimate": tokens_per_tool,
        "avg_token_savings": round(token_savings),
        "results": results,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"\nFull results written to {out_path}")


if __name__ == "__main__":
    run_benchmark()
