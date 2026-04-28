# -*- coding: utf-8 -*-
"""
Agent管理类 MCP 工具
"""

from typing import Dict, Any
import secrets

from ...services.agent_service import AgentService
from ...services.consume_service import ConsumeService
from ...utils.db import get_db


class ConsumeTool:
    """消费服务工具"""
    
    name = "consume"
    description = "消费Agent服务（核心交易工具）"
    permission = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "consumer_account_id": {
                "type": "string",
                "description": "消费者账户ID"
            },
            "provider_agent_id": {
                "type": "string",
                "description": "服务提供者Agent ID"
            },
            "pricing_usdt": {
                "type": "string",
                "description": "服务定价（USDT）"
            },
            "reference_id": {
                "type": "string",
                "description": "幂等参考号"
            },
            "referrer_account_id": {
                "type": "string",
                "description": "推荐人账户ID（可选）"
            }
        },
        "required": ["consumer_account_id", "provider_agent_id", "pricing_usdt", "reference_id"]
    }
    
    async def execute(self, arguments: dict, agent_context) -> dict:
        """执行消费"""
        consumer_account_id = arguments.get("consumer_account_id")
        provider_agent_id = arguments.get("provider_agent_id")
        pricing_usdt = arguments.get("pricing_usdt")
        reference_id = arguments.get("reference_id")
        referrer_account_id = arguments.get("referrer_account_id")
        
        async with get_db() as db:
            consume_service = ConsumeService(db)
            result = await consume_service.consume(
                consumer_account_id=consumer_account_id,
                provider_account_id=None,  # 会从agent_id查询
                agent_id=provider_agent_id,
                pricing_usdt=pricing_usdt,
                referrer_account_id=referrer_account_id,
                reference_id=reference_id
            )
            
            return {
                "service_id": result.get("service_id"),
                "tx_id": result["tx_id"],
                "consumer_account_id": consumer_account_id,
                "provider_agent_id": provider_agent_id,
                "pricing_usdt": pricing_usdt,
                "burned_tokens": str(result["burned_tokens"]),
                "consumer_reward": str(result.get("consumer_reward", 0)),
                "status": "completed"
            }


class RegisterAgentTool:
    """注册新Agent工具"""
    
    name = "register_agent"
    description = "注册一个新Agent身份"
    permission = "admin"
    input_schema = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Agent名称（2-50字符）"
            },
            "owner_user_id": {
                "type": "string",
                "description": "所有者用户ID"
            },
            "usdt_address": {
                "type": "string",
                "description": "收款USDT地址（TRC20）"
            },
            "description": {
                "type": "string",
                "description": "Agent描述"
            }
        },
        "required": ["name", "owner_user_id", "usdt_address"]
    }
    
    async def execute(self, arguments: dict, agent_context) -> dict:
        """执行注册"""
        name = arguments.get("name")
        owner_user_id = arguments.get("owner_user_id")
        usdt_address = arguments.get("usdt_address")
        description = arguments.get("description", "")
        
        async with get_db() as db:
            agent_service = AgentService(db)
            agent = await agent_service.register_agent(
                name=name,
                owner_user_id=owner_user_id,
                usdt_address=usdt_address,
                metadata={"description": description}
            )
            
            return {
                "agent_id": agent.agent_id,
                "name": agent.name,
                "api_key": agent.api_key,
                "api_key_prefix": agent.api_key[:15] + "...",
                "status": agent.status,
                "created_at": agent.created_at.isoformat() if agent.created_at else None
            }


class ListAgentsTool:
    """搜索Agent工具"""
    
    name = "list_agents"
    description = "搜索可用Agent列表"
    permission = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "服务类别筛选"
            },
            "keyword": {
                "type": "string",
                "description": "关键词搜索"
            },
            "limit": {
                "type": "integer",
                "description": "返回条数",
                "default": 20
            }
        },
        "required": []
    }
    
    async def execute(self, arguments: dict, agent_context) -> dict:
        """执行搜索"""
        category = arguments.get("category")
        keyword = arguments.get("keyword")
        limit = min(arguments.get("limit", 20), 50)
        
        async with get_db() as db:
            agent_service = AgentService(db)
            agents = await agent_service.search_agents(
                keyword=keyword,
                category=category,
                limit=limit
            )
            
            return {
                "count": len(agents),
                "agents": [
                    {
                        "agent_id": a.agent_id,
                        "name": a.name,
                        "status": a.status,
                        "description": a.metadata.get("description", "") if a.metadata else ""
                    }
                    for a in agents
                ]
            }


# 工具注册函数
def register(registry: dict):
    """注册Agent管理工具"""
    registry["consume"] = ConsumeTool()
    registry["register_agent"] = RegisterAgentTool()
    registry["list_agents"] = ListAgentsTool()
