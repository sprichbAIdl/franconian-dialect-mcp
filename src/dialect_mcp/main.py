#!/usr/bin/env python3
"""
Franconian Dialect MCP Server - Entry Point
"""

import sys
from pathlib import Path

if __name__ == "__main__":
    src_dir = Path(__file__).parent.parent
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    
    from dialect_mcp.server import run_server
    run_server()
else:
    from .server import run_server