# -*- coding: utf-8 -*-
"""
MCP 认证模块 - API Key 验证
"""

import hashlib
import secrets
from typing import Optional
from dataclasses import dataclass
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from ..config import mcp_settings
from ...utils.db import get_db


security = HTTPBearer()


@dataclass
class AgentContext:
    """Agent 上下文信息"""
    agent_id: str
    agent_name: str
    user_id: str
    permissions: list
    api_key_prefix: str


def generate_api_key(prefix: str = "sk_live") -> tuple:
    """
    生成 API Key
    
    Returns:
        (api_key, api_key_hash, api_key_prefix)
    """
    # 生成随机字符串
    random_part = secrets.token_hex(mcp_settings.MCP_API_KEY_LENGTH // 2)
    api_key = f"{prefix}_{random_part}"
    
    # 计算哈希
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    
    # 前缀（用于显示）
    api_key_prefix = api_key[:15] + "..."
    
    return api_key, api_key_hash, api_key_prefix


def hash_api_key(api_key: str) -> str:
    """计算 API Key 的哈希值"""
    return hashlib.sha256(api_key.encode()).hexdigest()


async def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> AgentContext:
    """
    验证 API Key 并返回 Agent 上下文
    
    Raises:
        HTTPException: 认证失败
    """
    api_key = credentials.credentials
    
    # 检查格式
    if not (api_key.startswith("sk_live_") or api_key.startswith("sk_test_")):
        raise HTTPException(
            status_code=401,
            detail="Invalid API Key format"
        )
    
    # 计算哈希
    api_key_hash = hash_api_key(api_key)
    
    # 查询数据库
    async with get_db() as db:
        result = await db.execute(
            """
            SELECT a.agent_id, a.name, a.owner_user_id, a.status, 
                   a.api_key_prefix, a.permissions
            FROM agents a
            WHERE a.api_key_hash = %s AND a.status = 'active'
            """,
            (api_key_hash,)
        )
        row = await result.fetchone()
        
        if not row:
            raise HTTPException(
                status_code=401,
                detail="Invalid API Key or Agent not active"
            )
        
        return AgentContext(
            agent_id=row[0],
            agent_name=row[1],
            user_id=row[2],
            permissions=row[5] or mcp_settings.MCP_DEFAULT_PERMISSIONS,
            api_key_prefix=row[4]
        )


def require_permission(permission: str):
    """
    权限检查装饰器
    
    Usage:
        @require_permission("write")
        async def some_tool():
            ...
    """
    async def check_permission(
        agent: AgentContext = Depends(verify_api_key)
    ):
        if permission not in agent.permissions and "admin" not in agent.permissions:
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied: requires '{permission}'"
            )
        return agent
    
    return check_permission
