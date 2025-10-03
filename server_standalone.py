#!/usr/bin/env python3
"""
Standalone entry point for MCP dev command.

This exists because `mcp dev` has issues with relative imports when loading modules directly.
Use this with: uv run mcp dev server_standalone.py
"""

from src.dialect_mcp.server import mcp

if __name__ == "__main__":
    mcp.run()
