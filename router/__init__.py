"""Model-Router: tag each task in a plan with the cheapest capable model tier.

The package is intentionally dependency-free (standard library only) so the
core logic can later be wrapped as a Claude skill or an MCP server without
dragging in a heavy install.

Public re-exports are wired up in the pipeline task once all modules exist.
"""

__version__ = "0.1.0"
