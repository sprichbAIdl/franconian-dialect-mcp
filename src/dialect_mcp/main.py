#!/usr/bin/env python3
"""
Franconian Dialect MCP Server - Entry Point

For MCP CLI: uv run mcp dev src/dialect_mcp/server.py
For direct run: python -m dialect_mcp.main
"""

from __future__ import annotations

if __name__ == "__main__":
    from dialect_mcp.server import mcp
    mcp.run()
