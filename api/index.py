# -*- coding: utf-8 -*-
"""
正和系统 MCP Server（链上版 v2.0）

架构原则：
  - 无数据库、无 API Key、无私钥——合约即状态，链上即可信
  - 读操作：直接 eth_call Base 主网合约
  - 写操作：返回"签名就绪"的 calldata，由调用方（Agent/钱包）本地签名上链，
    私钥永不离开调用方环境

三大链上可核验特性：
  ① 存款安全：LoveVault 无 owner、无管理函数，NAV 单调增长
  ② 引路人激励：一次绑定永久分账（6bps USDC 立即到账 + 商户捐赠 LOVE 的 20%）
  ③ 消费即升值：每笔路由支付自动注入手续费与捐赠进金库，抬升全体持有者 NAV

全部代码内联于此文件，避免 Vercel Python 的依赖打包问题。
"""
import os
import time
from typing import Any, Dict, List, Optional

import httpx
from Crypto.Hash import keccak
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ==================== 链上常量（与 zhenghe-system api/a2a.mjs 单一事实来源对齐） ====================
CHAIN_ID = 8453  # Base 主网
RPC_URL = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")

ROUTER = "0x2348ec656e395edAbcE2e198DC44647456d81867"  # ZhengHeRouter：pay/payWithLove/bindReferrer
VAULT = "0x16A7F8CfAD687A87183fCbd1dF7aF09dce05D357"  # LoveVault（ERC-4626，无 owner）
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # Base 原生 USDC（Circle）

ASSET_DECIMALS = 6   # USDC
LOVE_DECIMALS = 18   # LOVE share
NAV_DECIMALS = 6     # nav() 返回 1e6 精度

# 费用结构（链上常量）：消费者手续费 30bps，其中 20%（=6bps）分给引路人；商户捐赠地板 10bps
FEE_RATE = 0.0006          # 付款方额外负担（6bps）
DONATION_FLOOR = 0.001     # 商户捐赠 10bps

SELECTOR = {
    "nav": "0xc1590cd7",
    "totalAssets": "0x01e1d114",
    "totalSupply": "0x18160ddd",
    "balanceOf": "0x70a08231",
    "approve": "0x095ea7b3",
    "pay": "0x7a17ac71",           # pay(uint256,bytes32,address,address)
    "payWithLove": "0xcfcf752c",   # payWithLove(uint256,bytes32,address,address)
    "deposit": "0x6e553f65",       # deposit(uint256,address) ERC-4626
    "redeem": "0xba087652",        # redeem(uint256,address,address) ERC-4626
    "bindReferrer": "0x04f618cb",  # bindReferrer(address)
    "previewDeposit": "0xef8b30f7",
    "maxRedeem": "0xd905777e",
}

ZERO_ADDR = "0x0000000000000000000000000000000000000000"

# RPC 失败时的兜底快照（标明是快照，不冒充实时）
FALLBACK = {"nav": 1.118038, "totalAssets": 5789.278371, "totalSupply": 5178.068752, "stale": True}

# ==================== ABI 编码工具（纯 Python，无 web3 依赖） ====================

def uint256_hex(n: int) -> str:
    return format(n, "064x")


def address_hex(addr: str) -> str:
    return addr.lower().replace("0x", "").rjust(64, "0")


def keccak256(data: bytes) -> bytes:
    h = keccak.new(digest_bits=256)
    h.update(data)
    return h.digest()


def ref_to_bytes32_hex(ref: Optional[str]) -> str:
    """ref → bytes32：已是 0x+64hex 直接透传；否则 keccak256(utf8(ref))。
    与 zhenghe-system 前端及 /api/orders 的链上验付口径一致。"""
    s = str(ref or "")
    if s.startswith("0x") and len(s) == 66:
        try:
            int(s[2:], 16)
            return s[2:].lower()
        except ValueError:
            pass
    return keccak256(s.encode("utf-8")).hex()


def is_address(s: Any) -> bool:
    if not isinstance(s, str) or not s.startswith("0x") or len(s) != 42:
        return False
    try:
        int(s[2:], 16)
        return True
    except ValueError:
        return False


# ==================== Base RPC（只读 eth_call） ====================

async def eth_call(to: str, data: str) -> Optional[str]:
    """单次 eth_call，失败返回 None"""
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "eth_call",
        "params": [{"to": to, "data": data}, "latest"],
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(RPC_URL, json=payload)
            res = r.json()
            if "result" in res and res["result"] and res["result"] != "0x":
                return res["result"]
    except Exception:
        pass
    return None


async def get_chain_state() -> Dict[str, Any]:
    """读取 NAV / 金库总资产 / LOVE 总份额（1e6 精度换算）"""
    nav_hex, assets_hex, supply_hex = (
        await eth_call(VAULT, SELECTOR["nav"]),
        await eth_call(VAULT, SELECTOR["totalAssets"]),
        await eth_call(VAULT, SELECTOR["totalSupply"]),
    )
    if nav_hex and assets_hex and supply_hex:
        return {
            "nav": int(nav_hex, 16) / 10 ** NAV_DECIMALS,
            "totalAssets": int(assets_hex, 16) / 10 ** ASSET_DECIMALS,
            "totalSupply": int(supply_hex, 16) / 10 ** LOVE_DECIMALS,
            "stale": False,
        }
    return dict(FALLBACK)


async def get_love_balance(addr: str) -> float:
    h = await eth_call(VAULT, SELECTOR["balanceOf"] + address_hex(addr))
    return int(h, 16) / 10 ** LOVE_DECIMALS if h else 0.0


async def get_usdc_balance(addr: str) -> float:
    h = await eth_call(USDC, SELECTOR["balanceOf"] + address_hex(addr))
    return int(h, 16) / 10 ** ASSET_DECIMALS if h else 0.0


# ==================== 路由支付决策（与 a2a.mjs / 前端 smartRoute 三通道对齐） ====================

def fee_of(amount: float) -> float:
    return amount * FEE_RATE


def decide_pay(amount: float, love_balance: float, wallet_usdc: float, nav: float) -> Dict[str, Any]:
    needed = amount + fee_of(amount)
    love_value = love_balance * nav
    if wallet_usdc >= needed:
        return {"kind": "PURE_PAY", "canPay": True, "needed": needed}
    if love_value >= needed:
        return {"kind": "PAY_WITH_LOVE", "canPay": True, "needed": needed}
    return {
        "kind": "INSUFFICIENT", "canPay": False, "needed": needed,
        "shortfall": round(max(0.0, needed - wallet_usdc - love_value), 6),
        "reason": "user_balance",
    }


def build_pay_steps(decision: Dict[str, Any], merchant: str, amount: float,
                    ref: Optional[str], leader: Optional[str], nav: float) -> List[Dict[str, Any]]:
    assets_wei = int(round(amount * 10 ** ASSET_DECIMALS))
    needed_wei = int(round(decision["needed"] * 10 ** ASSET_DECIMALS))
    ref_b32 = ref_to_bytes32_hex(ref)
    leader_hex = address_hex(leader if leader and is_address(leader) else ZERO_ADDR)
    pay_args = uint256_hex(assets_wei) + ref_b32 + address_hex(merchant) + leader_hex

    if decision["kind"] == "PURE_PAY":
        return [
            {"step": 1, "name": "approve", "to": USDC, "chainId": CHAIN_ID,
             "data": SELECTOR["approve"] + address_hex(ROUTER) + uint256_hex(needed_wei),
             "value": "0x0",
             "note": f"授权 Router 从你的 USDC 扣款 {decision['needed']:.6f}（金额 {amount} + 手续费 6bps）"},
            {"step": 2, "name": "pay", "to": ROUTER, "chainId": CHAIN_ID,
             "data": SELECTOR["pay"] + pay_args, "value": "0x0",
             "note": f"原子分账：商户收 {amount * 0.999:.6f} USDC，1‰ 捐赠注入金库，引路人分账，NAV 抬升"},
        ]
    # PAY_WITH_LOVE
    love_needed = round(decision["needed"] * 1.01 / nav, 6)  # 1% NAV 波动缓冲
    love_wei = int(round(love_needed * 10 ** LOVE_DECIMALS))
    return [
        {"step": 1, "name": "approve", "to": VAULT, "chainId": CHAIN_ID,
         "data": SELECTOR["approve"] + address_hex(ROUTER) + uint256_hex(love_wei),
         "value": "0x0",
         "note": f"授权 Router 使用你的 LOVE 份额（约 {love_needed} LOVE，含 1% 缓冲）"},
        {"step": 2, "name": "payWithLove", "to": ROUTER, "chainId": CHAIN_ID,
         "data": SELECTOR["payWithLove"] + pay_args, "value": "0x0",
         "note": "赎回 LOVE 按 NAV 换 USDC 完成支付：商户收 USDC，捐赠注入金库，NAV 抬升"},
    ]


# ==================== MCP 工具定义 ====================

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "nav_query",
        "description": "查询正和金库实时状态：NAV（净值）、金库 USDC 总资产、LOVE 总份额、累计溢价。"
                       "只读，无需任何授权。传入 address 可同时查该地址的 LOVE/USDC 余额与浮盈。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "address": {"type": "string", "description": "（可选）要查余额的钱包地址 0x…"},
            },
        },
    },
    {
        "name": "zhenghe_route",
        "description": "构造一笔正和路由支付（消费入口）。返回签名就绪的 approve+pay calldata，"
                       "调用方本地签名上链即完成原子正和支付：商户收 USDC + 捐赠注入金库 + 引路人分账 + NAV 抬升。"
                       "路由决策：USDC 够→直接付；USDC 不足但 LOVE×NAV 够→赎回 LOVE 付；都不够→返回缺口。"
                       "私钥永不经过服务器。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "merchant": {"type": "string", "description": "收款商户地址 0x…（必填）"},
                "amount": {"type": "number", "description": "支付金额（USDC，必填）"},
                "ref": {"type": "string", "description": "订单引用（可选，将 keccak 为 bytes32）"},
                "leader": {"type": "string", "description": "引路人地址（可选，未绑定时可自引自收）"},
                "payer": {"type": "string", "description": "付款方地址（可选，传入则按真实余额做路由决策）"},
            },
            "required": ["merchant", "amount"],
        },
    },
    {
        "name": "vault_action",
        "description": "正和金库操作。action=deposit：USDC→LOVE（返回 approve+deposit calldata）；"
                       "action=withdraw：LOVE→USDC（返回 redeem calldata）；action=balance：查 LOVE 余额+NAV+浮盈（只读）。"
                       "金库无 owner、无管理函数，NAV 单调增长——存款安全由合约字节码保证，可自验。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["deposit", "withdraw", "balance"]},
                "amount": {"type": "number", "description": "deposit=USDC 数量；withdraw=LOVE 数量"},
                "address": {"type": "string", "description": "操作地址 0x…（deposit/withdraw 的接收方，balance 的查询方）"},
            },
            "required": ["action", "address"],
        },
    },
    {
        "name": "affiliate_bind",
        "description": "绑定引路人（一次性、永久、链上不可改）。返回 bindReferrer calldata，签名上链即完成绑定。"
                       "此后该地址每笔路由消费的 6bps USDC 立即分给引路人，商户捐赠 LOVE 的 20% 同样分账，原子结算。"
                       "任何 Agent 都可以成为引路人推广正和并永久获取分成。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "leader": {"type": "string", "description": "引路人地址 0x…（必填）"},
                "binder": {"type": "string", "description": "被绑定地址 0x…（calldata 的 from，仅用于展示）"},
            },
            "required": ["leader"],
        },
    },
]


# ==================== 工具执行 ====================

async def tool_nav_query(args: Dict[str, Any]) -> Dict[str, Any]:
    chain = await get_chain_state()
    result: Dict[str, Any] = {
        "nav": chain["nav"],
        "totalAssetsUsdc": chain["totalAssets"],
        "totalSupplyLove": chain["totalSupply"],
        "premiumPct": round((chain["nav"] - 1) * 100, 4),
        "chainId": CHAIN_ID,
        "vault": VAULT,
        "verified": not chain["stale"],
        "note": "实时链上数据" if not chain["stale"] else "RPC 暂不可用，此为最近快照",
        "verifyYourself": f"eth_call {VAULT} nav() selector 0xc1590cd7 on Base (chainId 8453)",
    }
    addr = args.get("address")
    if addr and is_address(addr):
        love = await get_love_balance(addr)
        usdc = await get_usdc_balance(addr)
        result["account"] = {
            "address": addr,
            "loveBalance": round(love, 6),
            "usdcBalance": round(usdc, 6),
            "loveValueUsdc": round(love * chain["nav"], 6),
            "profitPct": round((chain["nav"] - 1) * 100, 4) if love > 0 else 0,
        }
    return result


async def tool_zhenghe_route(args: Dict[str, Any]) -> Dict[str, Any]:
    merchant = args.get("merchant", "")
    if not is_address(merchant):
        return {"error": "merchant 必须是合法的 0x 地址"}
    try:
        amount = float(args.get("amount", 0))
    except (TypeError, ValueError):
        return {"error": "amount 必须是数字"}
    if amount <= 0:
        return {"error": "amount 必须大于 0"}

    chain = await get_chain_state()
    payer = args.get("payer")
    wallet_usdc, love_balance = 0.0, 0.0
    balance_known = False
    if payer and is_address(payer):
        wallet_usdc = await get_usdc_balance(payer)
        love_balance = await get_love_balance(payer)
        balance_known = True
    else:
        # 未提供付款方：假设纯 USDC 支付通道，仅构造 calldata
        wallet_usdc = amount + fee_of(amount)

    decision = decide_pay(amount, love_balance, wallet_usdc, chain["nav"])
    if not decision["canPay"]:
        return {
            "kind": "INSUFFICIENT", "canPay": False,
            "needed": round(decision["needed"], 6),
            "walletUsdc": round(wallet_usdc, 6),
            "loveValueUsdc": round(love_balance * chain["nav"], 6),
            "shortfall": decision["shortfall"],
            "suggestion": "可先用 vault_action 存入 USDC 换 LOVE，或补足 USDC 后重试",
        }

    steps = build_pay_steps(decision, merchant, amount, args.get("ref"),
                            args.get("leader"), chain["nav"])
    inj = (amount * DONATION_FLOOR + fee_of(amount)) * 0.8
    uplift = (inj / chain["totalAssets"] * 100) if chain["totalAssets"] > 0 else 0
    result: Dict[str, Any] = {
        "kind": decision["kind"],
        "canPay": True,
        "amount": amount,
        "merchant": merchant,
        "feeUsdc": round(fee_of(amount), 6),
        "payerTotalDebit": round(decision["needed"], 6),
        "merchantReceives": round(amount * 0.999, 6),
        "donationToVault": round(amount * DONATION_FLOOR, 6),
        "navUpliftPctEst": round(uplift, 8),
        "nav": chain["nav"],
        "steps": steps,
        "signAndSend": "按 steps 顺序由付款方钱包签名发送（先 approve 后 pay），两步原子完成",
        "balanceSource": "链上实查" if balance_known else "未提供 payer，按纯 USDC 通道构造",
    }
    leader = args.get("leader")
    if leader and is_address(leader):
        result["affiliate"] = {
            "leader": leader,
            "leaderFeeUsdc": round(amount * FEE_RATE, 6),
            "leaderLoveSharePct": 20,
            "binding": "permanent, on-chain, 原子结算",
        }
    else:
        result["leaderHint"] = "未指定引路人：付款方可先用 affiliate_bind 自引自收，此后自己消费的 6bps+20%LOVE 分账归自己"
    return result


async def tool_vault_action(args: Dict[str, Any]) -> Dict[str, Any]:
    action = args.get("action", "")
    addr = args.get("address", "")
    if not is_address(addr):
        return {"error": "address 必须是合法的 0x 地址"}
    chain = await get_chain_state()

    if action == "balance":
        love = await get_love_balance(addr)
        usdc = await get_usdc_balance(addr)
        return {
            "address": addr,
            "loveBalance": round(love, 6),
            "usdcBalance": round(usdc, 6),
            "nav": chain["nav"],
            "loveValueUsdc": round(love * chain["nav"], 6),
            "profitPct": round((chain["nav"] - 1) * 100, 4) if love > 0 else 0,
            "verified": not chain["stale"],
        }

    try:
        amount = float(args.get("amount", 0))
    except (TypeError, ValueError):
        return {"error": "amount 必须是数字"}
    if amount <= 0:
        return {"error": "amount 必须大于 0"}

    if action == "deposit":
        amount_wei = int(round(amount * 10 ** ASSET_DECIMALS))
        love_est = round(amount / chain["nav"], 6)
        return {
            "action": "deposit",
            "amountUsdc": amount,
            "estLoveReceived": love_est,
            "nav": chain["nav"],
            "steps": [
                {"step": 1, "name": "approve", "to": USDC, "chainId": CHAIN_ID,
                 "data": SELECTOR["approve"] + address_hex(VAULT) + uint256_hex(amount_wei),
                 "value": "0x0", "note": f"授权金库划扣 {amount} USDC"},
                {"step": 2, "name": "deposit", "to": VAULT, "chainId": CHAIN_ID,
                 "data": SELECTOR["deposit"] + uint256_hex(amount_wei) + address_hex(addr),
                 "value": "0x0", "note": f"存入 {amount} USDC，按 NAV={chain['nav']} 铸造约 {love_est} LOVE"},
            ],
            "signAndSend": "按 steps 顺序签名发送，LOVE 立即到账，此后 NAV 增长即浮盈",
            "safety": "LoveVault 无 owner、无管理函数，仅可注入与按净值赎回——basescan.org 可验源码",
        }

    if action == "withdraw":
        love_wei = int(round(amount * 10 ** LOVE_DECIMALS))
        usdc_est = round(amount * chain["nav"], 6)
        return {
            "action": "withdraw",
            "amountLove": amount,
            "estUsdcReceived": usdc_est,
            "nav": chain["nav"],
            "steps": [
                {"step": 1, "name": "redeem", "to": VAULT, "chainId": CHAIN_ID,
                 "data": SELECTOR["redeem"] + uint256_hex(love_wei) + address_hex(addr) + address_hex(addr),
                 "value": "0x0", "note": f"赎回 {amount} LOVE，按 NAV={chain['nav']} 得约 {usdc_est} USDC"},
            ],
            "signAndSend": "签名发送即完成赎回，USDC 立即到账",
        }

    return {"error": "action 必须是 deposit / withdraw / balance 之一"}


async def tool_affiliate_bind(args: Dict[str, Any]) -> Dict[str, Any]:
    leader = args.get("leader", "")
    if not is_address(leader):
        return {"error": "leader 必须是合法的 0x 地址"}
    return {
        "action": "bindReferrer",
        "leader": leader,
        "steps": [
            {"step": 1, "name": "bindReferrer", "to": ROUTER, "chainId": CHAIN_ID,
             "data": SELECTOR["bindReferrer"] + address_hex(leader),
             "value": "0x0", "note": f"永久绑定引路人 {leader}（一次性、链上不可改）"},
        ],
        "signAndSend": "由被绑定地址的钱包签名发送即生效",
        "feeTable": {
            "consumerFeeBps": 30,
            "leaderFeeShare": "手续费的 20%（=6bps USDC，每笔立即到账）",
            "merchantDonationFloorBps": 10,
            "leaderDonationShare": "商户捐赠 LOVE 的 20%",
            "settlement": "atomic on-chain，随每笔路由支付实时结算",
        },
        "note": "绑定后不可更改。任何 Agent 都可成为引路人：让他人绑定你的地址，其每笔消费你都有分成。",
    }


TOOL_HANDLERS = {
    "nav_query": tool_nav_query,
    "zhenghe_route": tool_zhenghe_route,
    "vault_action": tool_vault_action,
    "affiliate_bind": tool_affiliate_bind,
}

# ==================== FastAPI App ====================

app = FastAPI(
    title="正和系统 MCP Server",
    description="Base 主网去中心化支付路由 + 资本保全金库。三大链上可核验特性："
                "①存款安全（无 owner、NAV 单调）②引路人激励（6bps+20% LOVE 永久分账）③消费即升值（每笔注入抬升 NAV）。"
                "无数据库、无 API Key、无私钥——读走 eth_call，写返回签名就绪 calldata。",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


def jsonrpc_result(req_id: Any, result: Any) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "result": result, "id": req_id}


def jsonrpc_error(req_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "error": {"code": code, "message": message}, "id": req_id}


@app.get("/")
async def root():
    return {
        "name": "zhenghe-mcp",
        "version": "2.0.0",
        "protocol": "MCP (JSON-RPC 2.0 over HTTP)",
        "endpoint": "POST /mcp",
        "chain": {"chainId": CHAIN_ID, "router": ROUTER, "vault": VAULT, "usdc": USDC},
        "tools": [t["name"] for t in TOOLS],
        "sellingPoints": [
            "存款安全：金库无 owner、无管理函数，NAV 单调增长，字节码可验",
            "引路人激励：一次绑定永久分账，6bps USDC 立即到账 + 捐赠 LOVE 的 20%",
            "消费即升值：每笔路由支付注入手续费与捐赠，抬升全体持有者 NAV",
        ],
    }


@app.get("/health")
async def health():
    chain = await get_chain_state()
    return {"ok": True, "nav": chain["nav"], "stale": chain["stale"], "ts": int(time.time())}


@app.post("/mcp")
async def mcp_endpoint(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(jsonrpc_error(None, -32700, "Parse error: invalid JSON"))

    if body.get("jsonrpc") != "2.0":
        return JSONResponse(jsonrpc_error(body.get("id"), -32600, "jsonrpc must be '2.0'"))

    method = body.get("method", "")
    params = body.get("params") or {}
    req_id = body.get("id")

    if method == "initialize":
        # 回显客户端请求的协议版本（兼容各版本 Registry/目录的健康扫描）
        client_ver = params.get("protocolVersion") or "2024-11-05"
        return JSONResponse(jsonrpc_result(req_id, {
            "protocolVersion": client_ver,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "zhenghe-mcp", "version": "2.0.1"},
        }))

    if method in ("notifications/initialized", "initialized"):
        return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": {}})

    if method == "ping":
        return JSONResponse(jsonrpc_result(req_id, {}))

    if method == "tools/list":
        return JSONResponse(jsonrpc_result(req_id, {"tools": TOOLS}))

    if method == "tools/call":
        name = params.get("name", "")
        arguments = params.get("arguments") or {}
        handler = TOOL_HANDLERS.get(name)
        if not handler:
            return JSONResponse(jsonrpc_error(req_id, -32602, f"未知工具: {name}"))
        try:
            result = await handler(arguments)
            import json as _json
            return JSONResponse(jsonrpc_result(req_id, {
                "content": [{"type": "text", "text": _json.dumps(result, ensure_ascii=False, indent=2)}],
                "isError": "error" in result,
            }))
        except Exception as e:
            return JSONResponse(jsonrpc_result(req_id, {
                "content": [{"type": "text", "text": f'{{"error": "工具执行异常: {e}"}}'}],
                "isError": True,
            }))

    return JSONResponse(jsonrpc_error(req_id, -32601, f"Method not found: {method}"))


# Vercel 入口
handler = app
