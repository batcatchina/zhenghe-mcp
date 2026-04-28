# -*- coding: utf-8 -*-
"""
MCP 配置
"""

from pydantic_settings import BaseSettings
from typing import List


class MCPSettings(BaseSettings):
    """MCP 服务配置"""
    
    # 服务配置
    MCP_SERVER_NAME: str = "zhenghe-points"
    MCP_SERVER_VERSION: str = "1.0.0"
    MCP_PROTOCOL_VERSION: str = "2024-11-05"
    
    # HTTP 配置
    MCP_HTTP_HOST: str = "0.0.0.0"
    MCP_HTTP_PORT: int = 8081
    
    # 认证配置
    MCP_API_KEY_PREFIX_LIVE: str = "sk_live_"
    MCP_API_KEY_PREFIX_TEST: str = "sk_test_"
    MCP_API_KEY_LENGTH: int = 32
    
    # 频率限制
    MCP_RATE_LIMIT_REQUESTS: int = 100  # 每分钟请求数
    MCP_RATE_LIMIT_WINDOW: int = 60  # 秒
    
    # 权限配置
    MCP_DEFAULT_PERMISSIONS: List[str] = ["read"]
    MCP_ADMIN_PERMISSIONS: List[str] = ["read", "write", "admin"]
    
    class Config:
        env_file = ".env"
        env_prefix = "ZHENGHE_"


# 全局配置实例
mcp_settings = MCPSettings()
