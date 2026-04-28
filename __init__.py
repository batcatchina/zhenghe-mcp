# -*- coding: utf-8 -*-
"""
正和系统 MCP 层
将正和系统开放为 MCP 服务，供 AI Agent 调用
"""

from .server import create_mcp_server, mcp_app
from .config import mcp_settings

__all__ = ["create_mcp_server", "mcp_app", "mcp_settings"]
