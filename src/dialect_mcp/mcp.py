#!/usr/bin/env python3
"""
Franconian Dialect MCP Server - Entry Point
Clean modular architecture following LangSec principles.
"""

from .server import run_server

if __name__ == "__main__":
    run_server()