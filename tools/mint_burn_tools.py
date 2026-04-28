# -*- coding: utf-8 -*-
"""
铸造/销毁类 MCP 工具
"""

from decimal import Decimal
from typing import Dict, Any
import uuid

from ...services.mint_service import MintService
from ...services.burn_service import BurnService
from ...utils.db import get_db
from ...utils.exceptions import InsufficientBalanceError


class MintTool:
    """铸造积分工具"""
    
    name = "mint"
    description = "充值USDT铸造积分（需要链上交易确认）"
    permission = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "account_id": {
                "type": "string",
                "description": "目标积分账户ID"
            },
            "usdt_amount": {
                "type": "string",
                "description": "充值USDT金额"
            },
            "tx_hash": {
                "type": "string",
                "description": "链上交易哈希"
            },
            "reference_id": {
                "type": "string",
                "description": "幂等参考号"
            }
        },
        "required": ["account_id", "usdt_amount", "tx_hash", "reference_id"]
    }
    
    async def execute(self, arguments: dict, agent_context) -> dict:
        """执行铸造"""
        account_id = arguments.get("account_id")
        usdt_amount = Decimal(arguments.get("usdt_amount"))
        tx_hash = arguments.get("tx_hash")
        reference_id = arguments.get("reference_id")
        
        async with get_db() as db:
            # TODO: 验证链上交易（暂时跳过，模拟确认）
            
            mint_service = MintService(db)
            result = await mint_service.mint(
                user_id=agent_context.user_id,
                account_id=account_id,
                usdt_amount=usdt_amount,
                reference_id=reference_id
            )
            
            return {
                "tx_id": result["tx_id"],
                "account_id": account_id,
                "usdt_amount": str(usdt_amount),
                "minted_tokens": str(result["minted_tokens"]),
                "price_at_mint": str(result["price_at_tx"]),
                "new_balance": str(result["new_balance"]),
                "status": "completed"
            }


class BurnTool:
    """销毁积分工具"""
    
    name = "burn"
    description = "销毁积分兑换USDT"
    permission = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "account_id": {
                "type": "string",
                "description": "积分账户ID"
            },
            "token_amount": {
                "type": "string",
                "description": "要销毁的积分数量"
            },
            "reference_id": {
                "type": "string",
                "description": "幂等参考号"
            }
        },
        "required": ["account_id", "token_amount", "reference_id"]
    }
    
    async def execute(self, arguments: dict, agent_context) -> dict:
        """执行销毁"""
        account_id = arguments.get("account_id")
        token_amount = Decimal(arguments.get("token_amount"))
        reference_id = arguments.get("reference_id")
        
        async with get_db() as db:
            burn_service = BurnService(db)
            result = await burn_service.burn(
                account_id=account_id,
                token_amount=token_amount,
                reference_id=reference_id
            )
            
            return {
                "tx_id": result["tx_id"],
                "account_id": account_id,
                "burned_tokens": str(token_amount),
                "usdt_out": str(result["usdt_out"]),
                "price_at_burn": str(result["price_at_tx"]),
                "new_balance": str(result["new_balance"]),
                "status": "completed"
            }


# 工具注册函数
def register(registry: dict):
    """注册铸造/销毁工具"""
    registry["mint"] = MintTool()
    registry["burn"] = BurnTool()
