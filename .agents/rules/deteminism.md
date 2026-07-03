---
trigger: always_on
---

# Determinism & Consistency Rules

To ensure that the agent returns consistent, reproducible, and identical results for identical prompts, the agent must follow these rules:

1. **Greedy and Deterministic Code Generation**: Always choose the most direct, standard, and logical implementation. Avoid inserting stylistic variations or alternative approaches unless explicitly requested.
2. **Fixed Formatting**: Maintain an identical structure, naming convention, and comment format for all generated files and code blocks.
3. **No Stylistic Variation**: When answering questions or generating code, do not introduce random variations in word choice, logging formats, or variable names.
4. **Follow Prior Patterns Exactly**: Reuse existing coding patterns, file structures, and library imports found in the workspace exactly as they are.
