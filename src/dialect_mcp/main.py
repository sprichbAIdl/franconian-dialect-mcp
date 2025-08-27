#!/usr/bin/env python3
"""
Franconian Dialect MCP Server - Entry Point
Clean modular architecture following LangSec principles.
"""

import sys
from pathlib import Path

# Add the src directory to Python path for proper module resolution
if __name__ == "__main__":
    # Get the src directory (parent of dialect_mcp)
    src_dir = Path(__file__).parent.parent
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    
    # Now we can import from the package
    from dialect_mcp.server import run_server
    run_server()
else:
    # When imported as a module, use relative imports
    from .server import run_server