"""
VisionLink MCP Server — entry point alias for course submission.
Run from laptop-server/:
    python server.py
"""
from app.mcp_server import mcp

if __name__ == "__main__":
    mcp.run()
