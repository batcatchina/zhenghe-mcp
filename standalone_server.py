# -*- coding: utf-8 -*-
"""
正和系统 - REST API + MCP Server
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional
import os
import json
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from decimal import Decimal
import uuid
import secrets
from datetime import datetime

# 环境变量
DATABASE_URL = os.getenv("DATABASE_URL", "")
SECRET_KEY = os.getenv("SECRET_KEY", "zhenghe_secret")

# 数据库引擎
engine = None

async def get_db_engine():
    global engine
    if engine is None and DATABASE_URL:
        engine = create_async_engine(DATABASE_URL, echo=False, pool_size=1, max_overflow=0)
    return engine


# ===== FastAPI App =====

app = FastAPI(
    title="正和系统 API",
    description="AI Agent经济价值交换协议 - REST API + MCP Server",
    version="1.1.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===== 健康检查 =====

@app.get("/")
async def root():
    return {"name": "正和系统 API", "version": "1.1.0", "status": "running"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


# ===== REST API 端点（前端需要） =====

@app.get("/v1/stats")
async def get_stats():
    """获取系统统计"""
    db = await get_db_engine()
    if not db:
        return {"total_accounts": 0, "total_transactions": 0, "total_agents": 0}
    
    try:
        async with db.connect() as conn:
            result = await conn.execute(text("SELECT COUNT(*) FROM accounts"))
            total_accounts = result.scalar() or 0
            
            result = await conn.execute(text("SELECT COUNT(*) FROM transactions"))
            total_txs = result.scalar() or 0
            
            result = await conn.execute(text("SELECT COUNT(*) FROM agents"))
            total_agents = result.scalar() or 0
            
            return {
                "total_accounts": total_accounts,
                "total_transactions": total_txs,
                "total_agents": total_agents
            }
    except Exception as e:
        return {"total_accounts": 0, "total_transactions": 0, "total_agents": 0, "error": str(e)}


@app.get("/v1/pool/state")
async def get_pool_state():
    """获取资金池状态"""
    db = await get_db_engine()
    if not db:
        return {"price": "1.0", "total_supply": "0", "capital_pool": "0"}
    
    try:
        async with db.connect() as conn:
            result = await conn.execute(
                text("SELECT price, total_supply, capital_pool FROM prices ORDER BY recorded_at DESC LIMIT 1")
            )
            row = result.fetchone()
            
            if row:
                return {
                    "price": str(row[0]),
                    "total_supply": str(row[1]),
                    "capital_pool": str(row[2])
                }
    except:
        pass
    
    return {"price": "1.0", "total_supply": "0", "capital_pool": "0"}


@app.get("/v1/agents")
async def get_agents():
    """获取Agent列表"""
    db = await get_db_engine()
    if not db:
        return {"agents": []}
    
    try:
        async with db.connect() as conn:
            result = await conn.execute(
                text("SELECT id, name, status, created_at FROM agents ORDER BY created_at DESC LIMIT 20")
            )
            rows = result.fetchall()
            
            return {
                "agents": [
                    {"id": row[0], "name": row[1], "status": row[2], "created_at": str(row[3]) if row[3] else ""}
                    for row in rows
                ]
            }
    except:
        return {"agents": []}


@app.get("/v1/transactions")
async def get_transactions(limit: int = 50):
    """获取交易列表"""
    db = await get_db_engine()
    if not db:
        return {"transactions": []}
    
    try:
        async with db.connect() as conn:
            result = await conn.execute(
                text("SELECT id, tx_type, amount, created_at FROM transactions ORDER BY created_at DESC LIMIT :limit"),
                {"limit": limit}
            )
            rows = result.fetchall()
            
            return {
                "transactions": [
                    {"id": row[0], "type": row[1], "amount": str(row[2]), "created_at": str(row[3]) if row[3] else ""}
                    for row in rows
                ]
            }
    except:
        return {"transactions": []}


@app.get("/v1/accounts/{account_id}")
async def get_account(account_id: str):
    """获取账户信息"""
    db = await get_db_engine()
    if not db:
        return {"error": "数据库未配置"}
    
    try:
        async with db.connect() as conn:
            result = await conn.execute(
                text("SELECT id, balance, user_id FROM accounts WHERE id = :id"),
                {"id": account_id}
            )
            row = result.fetchone()
            
            if row:
                return {
                    "id": row[0],
                    "balance": str(row[1]),
                    "user_id": row[2]
                }
    except:
        pass
    
    return {"error": "账户不存在"}


@app.post("/v1/demo/init")
async def demo_init():
    """初始化演示数据"""
    db = await get_db_engine()
    if not db:
        return {"success": False, "error": "数据库未配置"}
    
    try:
        async with db.begin() as conn:
            # 创建演示用户
            demo_users = []
            for i in range(2):
                user_id = f"user_demo_{i+1}"
                username = f"演示用户{i+1}"
                account_id = f"acc_demo_{i+1}"
                balance = 100 if i == 0 else 50
                
                await conn.execute(
                    text("INSERT INTO users (id, username, user_type) VALUES (:id, :name, 'demo') ON CONFLICT (id) DO NOTHING"),
                    {"id": user_id, "name": username}
                )
                
                await conn.execute(
                    text("INSERT INTO accounts (id, user_id, balance, account_type) VALUES (:id, :user_id, :balance, 'primary') ON CONFLICT (id) DO NOTHING"),
                    {"id": account_id, "user_id": user_id, "balance": balance}
                )
                
                demo_users.append({"user_id": user_id, "account_id": account_id, "balance": balance})
            
            # 创建演示Agent
            demo_agents = []
            for i in range(5):
                agent_id = f"agent_demo_{i+1}"
                agent_name = f"演示Agent{i+1}"
                
                await conn.execute(
                    text("INSERT INTO agents (id, name, owner_user_id, status) VALUES (:id, :name, 'system', 'active') ON CONFLICT (id) DO NOTHING"),
                    {"id": agent_id, "name": agent_name}
                )
                
                api_key = f"sk_demo_{secrets.token_hex(24)}"
                await conn.execute(
                    text("INSERT INTO api_keys (id, key_hash, agent_id, permissions) VALUES (:id, :key, :agent, '{\"role\": \"read\"}'::jsonb) ON CONFLICT (id) DO NOTHING"),
                    {"id": f"key_demo_{i+1}", "key": api_key, "agent": agent_id}
                )
                
                demo_agents.append({"agent_id": agent_id, "name": agent_name})
            
            # 初始化价格记录
            await conn.execute(
                text("INSERT INTO prices (price, total_supply, capital_pool, recorded_at) VALUES (1.0, 150, 150, :now) ON CONFLICT DO NOTHING"),
                {"now": datetime.utcnow()}
            )
        
        return {
            "success": True,
            "message": "演示数据初始化成功",
            "demo_users": demo_users,
            "demo_agents": demo_agents
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/v1/users")
async def create_user(request: Request):
    """创建用户"""
    body = await request.json()
    username = body.get("username", "新用户")
    
    db = await get_db_engine()
    if not db:
        return {"error": "数据库未配置"}
    
    try:
        user_id = f"user_{uuid.uuid4().hex[:24]}"
        account_id = f"acc_{uuid.uuid4().hex[:24]}"
        
        async with db.begin() as conn:
            await conn.execute(
                text("INSERT INTO users (id, username, user_type) VALUES (:id, :name, 'user')"),
                {"id": user_id, "name": username}
            )
            
            await conn.execute(
                text("INSERT INTO accounts (id, user_id, balance, account_type) VALUES (:id, :user_id, 0, 'primary')"),
                {"id": account_id, "user_id": user_id}
            )
        
        return {
            "user_id": user_id,
            "account_id": account_id,
            "username": username
        }
    except Exception as e:
        return {"error": str(e)}


@app.post("/v1/mint")
async def mint_tokens(request: Request):
    """铸造积分（充值）"""
    body = await request.json()
    account_id = body.get("account_id")
    amount = Decimal(str(body.get("amount", 0)))
    
    db = await get_db_engine()
    if not db:
        return {"success": False, "error": "数据库未配置"}
    
    try:
        async with db.begin() as conn:
            result = await conn.execute(
                text("UPDATE accounts SET balance = balance + :amount WHERE id = :id RETURNING balance"),
                {"amount": amount, "id": account_id}
            )
            row = result.fetchone()
            
            if row:
                return {
                    "success": True,
                    "new_balance": str(row[0]),
                    "minted": str(amount)
                }
    except Exception as e:
        return {"success": False, "error": str(e)}
    
    return {"success": False, "error": "账户不存在"}


@app.post("/v1/burn")
async def burn_tokens(request: Request):
    """燃烧积分（提现）"""
    body = await request.json()
    account_id = body.get("account_id")
    amount = Decimal(str(body.get("amount", 0)))
    
    db = await get_db_engine()
    if not db:
        return {"success": False, "error": "数据库未配置"}
    
    try:
        async with db.begin() as conn:
            result = await conn.execute(
                text("SELECT balance FROM accounts WHERE id = :id FOR UPDATE"),
                {"id": account_id}
            )
            row = result.fetchone()
            
            if not row or Decimal(str(row[0])) < amount:
                return {"success": False, "error": "余额不足"}
            
            result = await conn.execute(
                text("UPDATE accounts SET balance = balance - :amount WHERE id = :id RETURNING balance"),
                {"amount": amount, "id": account_id}
            )
            new_row = result.fetchone()
            
            return {
                "success": True,
                "new_balance": str(new_row[0]),
                "burned": str(amount)
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/v1/consume")
async def consume_service(request: Request):
    """消费服务"""
    body = await request.json()
    consumer_account_id = body.get("consumer_account_id")
    provider_agent_id = body.get("provider_agent_id")
    pricing_usdt = Decimal(str(body.get("pricing_usdt", 0)))
    
    db = await get_db_engine()
    if not db:
        return {"success": False, "error": "数据库未配置"}
    
    try:
        async with db.begin() as conn:
            result = await conn.execute(
                text("SELECT price FROM prices ORDER BY recorded_at DESC LIMIT 1")
            )
            price_row = result.fetchone()
            price = Decimal(str(price_row[0])) if price_row else Decimal("1.0")
            
            burn_multiplier = Decimal("1.009")
            burned_tokens = (pricing_usdt / price) * burn_multiplier
            
            result = await conn.execute(
                text("SELECT balance FROM accounts WHERE id = :id FOR UPDATE"),
                {"id": consumer_account_id}
            )
            row = result.fetchone()
            
            if not row or Decimal(str(row[0])) < burned_tokens:
                return {"success": False, "error": "余额不足"}
            
            new_balance = Decimal(str(row[0])) - burned_tokens
            await conn.execute(
                text("UPDATE accounts SET balance = :balance WHERE id = :id"),
                {"balance": new_balance, "id": consumer_account_id}
            )
            
            tx_id = f"tx_{uuid.uuid4().hex[:24]}"
            await conn.execute(
                text("INSERT INTO transactions (id, tx_type, amount, from_account_id) VALUES (:id, 'CONSUME', :amount, :from)"),
                {"id": tx_id, "amount": burned_tokens, "from": consumer_account_id}
            )
            
            return {
                "success": True,
                "tx_id": tx_id,
                "burned_tokens": str(burned_tokens),
                "new_balance": str(new_balance)
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ===== MCP 端点 =====

@app.post("/mcp")
async def mcp_endpoint(request: Request):
    """MCP JSON-RPC 2.0 端点"""
    try:
        body = await request.json()
        method = body.get("method", "")
        params = body.get("params", {})
        request_id = body.get("id", 1)
        
        if method == "tools/list":
            tools = [
                {"name": "get_balance", "description": "查询账户积分余额"},
                {"name": "get_price", "description": "查询当前积分价格"},
                {"name": "register_agent", "description": "注册新Agent"},
                {"name": "consume", "description": "消费Agent服务"},
                {"name": "mint", "description": "铸造积分"},
                {"name": "burn", "description": "燃烧积分"},
            ]
            return {
                "jsonrpc": "2.0",
                "result": {"tools": tools},
                "id": request_id
            }
        
        elif method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            
            # 简单转发到REST API
            if tool_name == "get_price":
                result = await get_pool_state()
            elif tool_name == "get_balance":
                result = await get_account(arguments.get("account_id", ""))
            else:
                result = {"error": f"工具不存在: {tool_name}"}
            
            return {
                "jsonrpc": "2.0",
                "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]},
                "id": request_id
            }
        
        else:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32601, "message": f"方法不存在: {method}"},
                "id": request_id
            }
    
    except Exception as e:
        return {
            "jsonrpc": "2.0",
            "error": {"code": -32603, "message": str(e)},
            "id": 1
        }


# Vercel入口
handler = app
