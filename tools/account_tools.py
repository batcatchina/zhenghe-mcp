# -*- coding: utf-8 -*-
"""
账户查询类 MCP 工具
"""

import json
from typing import Dict, Any, Optional
from dataclasses import dataclass
from decimal import Decimal

from ...services.agent_service import AgentService
from ...services.price_engine import PriceEngine
from ...utils.db import get_db


@dataclass
class MCPTool:
    """MCP 工具定义"""
    name: str
    description: str
    input_schema: Dict[str, Any]
    permission: str  # read, write, admin
    
    def to_mcp_spec(self) -> Dict[str, Any]:
        """转换为 MCP 协议格式"""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema
        }


class GetBalanceTool:
    """查询积分余额工具"""
    
    name = "get_balance"
    description = "查询指定账户的积分余额、当前价格和USDT价值"
    permission = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "account_id": {
                "type": "string",
                "description": "积分账户ID，格式: acc_xxx"
            }
        },
        "required": ["account_id"]
    }
    
    async def execute(self, arguments: dict, agent_context) -> dict:
        """执行查询"""
        account_id = arguments.get("account_id")
        
        async with get_db() as db:
            # 查询账户
            account = await db.execute(
                "SELECT balance FROM accounts WHERE account_id = %s",
                (account_id,)
            )
            row = await account.fetchone()
            
            if not row:
                raise ValueError(f"账户不存在: {account_id}")
            
            balance = Decimal(str(row[0]))
            
            # 查询当前价格
            price_engine = PriceEngine()
            price = await price_engine.get_current_price(db)
            
            # 计算价值
            value_usdt = balance * price
            
            return {
                "account_id": account_id,
                "balance": str(balance),
                "price": str(price),
                "value_usdt": str(value_usdt.quantize(Decimal("0.01")))
            }


class GetPriceTool:
    """查询当前价格工具"""
    
    name = "get_price"
    description = "查询当前积分价格、总供应量和资金池状态"
    permission = "read"
    input_schema = {
        "type": "object",
        "properties": {},
        "required": []
    }
    
    async def execute(self, arguments: dict, agent_context) -> dict:
        """执行查询"""
        async with get_db() as db:
            price_engine = PriceEngine()
            price = await price_engine.get_current_price(db)
            
            # 查询池子状态
            capital_result = await db.execute(
                "SELECT balance FROM pools WHERE pool_type = 'capital'"
            )
            capital_row = await capital_result.fetchone()
            capital_balance = Decimal(str(capital_row[0])) if capital_row else Decimal("0")
            
            growth_result = await db.execute(
                "SELECT balance FROM pools WHERE pool_type = 'growth'"
            )
            growth_row = await growth_result.fetchone()
            growth_balance = Decimal(str(growth_row[0])) if growth_row else Decimal("0")
            
            # 查询总供应量
            supply_result = await db.execute(
                "SELECT total_supply FROM token_state WHERE id = 1"
            )
            supply_row = await supply_result.fetchone()
            total_supply = Decimal(str(supply_row[0])) if supply_row else Decimal("0")
            
            return {
                "price": str(price),
                "total_supply": str(total_supply),
                "capital_pool": str(capital_balance),
                "growth_pool": str(growth_balance),
                "market_cap": str(capital_balance + growth_balance)
            }


class GetHistoryTool:
    """查询交易历史工具"""
    
    name = "get_history"
    description = "查询指定账户的交易历史记录"
    permission = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "account_id": {
                "type": "string",
                "description": "积分账户ID"
            },
            "limit": {
                "type": "integer",
                "description": "返回条数，默认20，最大100",
                "default": 20
            }
        },
        "required": ["account_id"]
    }
    
    async def execute(self, arguments: dict, agent_context) -> dict:
        """执行查询"""
        account_id = arguments.get("account_id")
        limit = min(arguments.get("limit", 20), 100)
        
        async with get_db() as db:
            result = await db.execute(
                """
                SELECT tx_id, tx_type, token_amount, usdt_amount, price_at_tx, 
                       description, created_at
                FROM transactions
                WHERE account_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (account_id, limit)
            )
            rows = await result.fetchall()
            
            transactions = []
            for row in rows:
                transactions.append({
                    "tx_id": row[0],
                    "tx_type": row[1],
                    "token_amount": str(row[2]),
                    "usdt_amount": str(row[3]),
                    "price_at_tx": str(row[4]),
                    "description": row[5],
                    "created_at": row[6].isoformat() if row[6] else None
                })
            
            return {
                "account_id": account_id,
                "count": len(transactions),
                "transactions": transactions
            }


class GetAgentTool:
    """查询Agent信息工具"""
    
    name = "get_agent"
    description = "查询Agent的详细信息和提供的服务"
    permission = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "agent_id": {
                "type": "string",
                "description": "Agent ID，格式: agent_xxx"
            }
        },
        "required": ["agent_id"]
    }
    
    async def execute(self, arguments: dict, agent_context) -> dict:
        """执行查询"""
        agent_id = arguments.get("agent_id")
        
        async with get_db() as db:
            agent_service = AgentService(db)
            agent = await agent_service.get_agent(agent_id)
            
            if not agent:
                raise ValueError(f"Agent不存在: {agent_id}")
            
            # 查询服务定价
            pricings = await agent_service.get_pricings(agent_id)
            
            return {
                "agent_id": agent.agent_id,
                "name": agent.name,
                "status": agent.status,
                "usdt_address": agent.usdt_address,
                "services": [
                    {
                        "service_type": p.service_type,
                        "pricing_usdt": str(p.pricing_usdt),
                        "description": p.description
                    }
                    for p in pricings
                ],
                "created_at": agent.created_at.isoformat() if agent.created_at else None
            }


# 工具注册函数
def register(registry: dict):
    """注册账户查询工具"""
    registry["get_balance"] = GetBalanceTool()
    registry["get_price"] = GetPriceTool()
    registry["get_history"] = GetHistoryTool()
    registry["get_agent"] = GetAgentTool()
