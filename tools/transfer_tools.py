# -*- coding: utf-8 -*-
"""
转账类 MCP 工具
"""

from decimal import Decimal
from typing import Dict, Any
import uuid

from ...services.mint_service import MintService
from ...services.burn_service import BurnService
from ...utils.db import get_db
from ...utils.exceptions import InsufficientBalanceError


class TransferTool:
    """积分转账工具"""
    
    name = "transfer"
    description = "在账户之间转移积分"
    permission = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "from_account_id": {
                "type": "string",
                "description": "转出账户ID"
            },
            "to_account_id": {
                "type": "string",
                "description": "接收账户ID"
            },
            "amount": {
                "type": "string",
                "description": "转账积分数量"
            },
            "reference_id": {
                "type": "string",
                "description": "幂等参考号，防止重复执行"
            },
            "memo": {
                "type": "string",
                "description": "转账备注（可选）"
            }
        },
        "required": ["from_account_id", "to_account_id", "amount", "reference_id"]
    }
    
    async def execute(self, arguments: dict, agent_context) -> dict:
        """执行转账"""
        from_account_id = arguments.get("from_account_id")
        to_account_id = arguments.get("to_account_id")
        amount = Decimal(arguments.get("amount"))
        reference_id = arguments.get("reference_id")
        memo = arguments.get("memo", "")
        
        async with get_db() as db:
            # 检查幂等
            existing = await db.execute(
                "SELECT tx_id FROM transactions WHERE reference_id = %s",
                (reference_id,)
            )
            if await existing.fetchone():
                raise ValueError(f"重复的reference_id: {reference_id}")
            
            # 检查余额
            balance_result = await db.execute(
                "SELECT balance FROM accounts WHERE account_id = %s FOR UPDATE",
                (from_account_id,)
            )
            balance_row = await balance_result.fetchone()
            
            if not balance_row:
                raise ValueError(f"转出账户不存在: {from_account_id}")
            
            current_balance = Decimal(str(balance_row[0]))
            if current_balance < amount:
                raise InsufficientBalanceError(
                    f"余额不足: 需要 {amount}, 可用 {current_balance}"
                )
            
            # 检查接收账户
            to_result = await db.execute(
                "SELECT account_id FROM accounts WHERE account_id = %s",
                (to_account_id,)
            )
            if not await to_result.fetchone():
                raise ValueError(f"接收账户不存在: {to_account_id}")
            
            # 执行转账
            tx_id = f"tx_{uuid.uuid4().hex[:24]}"
            
            # 扣款
            await db.execute(
                "UPDATE accounts SET balance = balance - %s WHERE account_id = %s",
                (amount, from_account_id)
            )
            
            # 入账
            await db.execute(
                "UPDATE accounts SET balance = balance + %s WHERE account_id = %s",
                (amount, to_account_id)
            )
            
            # 记录交易
            await db.execute(
                """
                INSERT INTO transactions 
                (tx_id, tx_type, account_id, token_amount, reference_id, description)
                VALUES (%s, 'transfer', %s, -%s, %s, %s)
                """,
                (tx_id, from_account_id, amount, reference_id, f"转账到 {to_account_id}: {memo}")
            )
            
            await db.execute(
                """
                INSERT INTO transactions 
                (tx_id, tx_type, account_id, token_amount, reference_id, description)
                VALUES (%s, 'transfer', %s, %s, %s, %s)
                """,
                (tx_id, to_account_id, amount, reference_id, f"来自 {from_account_id}: {memo}")
            )
            
            await db.commit()
            
            # 查询新余额
            new_balance_result = await db.execute(
                "SELECT balance FROM accounts WHERE account_id = %s",
                (from_account_id,)
            )
            new_balance_row = await new_balance_result.fetchone()
            
            return {
                "tx_id": tx_id,
                "from_account_id": from_account_id,
                "to_account_id": to_account_id,
                "amount": str(amount),
                "from_new_balance": str(new_balance_row[0]),
                "status": "completed"
            }


# 工具注册函数
def register(registry: dict):
    """注册转账工具"""
    registry["transfer"] = TransferTool()
