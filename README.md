# 正和 MCP Server（zhenghe-mcp）

mcp-name: top.zheng-he/zhenghe-mcp

> Base 主网去中心化支付路由 + 资本保全金库的 MCP 接口。
> 让任何 AI Agent 通过四个工具接入正和系统——查 NAV、路由支付、金库存取、绑定引路人。

## 三大链上可核验特性

1. **存款安全**：LoveVault 无 owner、无管理函数，仅可注入与按净值赎回，NAV 单调增长——由合约字节码保证，非文档承诺。
2. **引路人激励**：一次绑定、永久分账。每笔消费的 6bps USDC 立即分给引路人，商户捐赠 LOVE 的 20% 同样分账，原子结算。任何 Agent 都可成为引路人。
3. **消费即升值**：每笔路由支付自动注入手续费与捐赠进金库，抬升全体持有者 NAV。

全部保证可通过 `eth_call` / 字节码检查自行核验。

## 架构原则

- **无数据库、无 API Key、无私钥**：合约即状态
- **读操作**：直接 `eth_call` Base 主网
- **写操作**：返回签名就绪的 calldata，调用方本地签名上链，私钥永不经过服务器

## MCP 工具

| 工具 | 说明 | 类型 |
|------|------|------|
| `nav_query` | 查 NAV、金库总资产、LOVE 总份额（可带 address 查余额浮盈） | 只读 |
| `zhenghe_route` | 构造路由支付：返回 approve+pay 签名就绪 calldata，支持 USDC/LOVE 双通道与引路人分账 | 构造交易 |
| `vault_action` | 金库操作：deposit（USDC→LOVE）、withdraw（LOVE→USDC）、balance | 只读+构造交易 |
| `affiliate_bind` | 永久绑定引路人（6bps + 20% LOVE 分账） | 构造交易 |

## 链上常量（Base 主网，chainId 8453）

| 合约 | 地址 |
|------|------|
| ZhengHeRouter | `0x2348ec656e395edAbcE2e198DC44647456d81867` |
| LoveVault（ERC-4626） | `0x16A7F8CfAD687A87183fCbd1dF7aF09dce05D357` |
| USDC（Circle 原生） | `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` |

## 接入

### HTTP 端点

```
POST /mcp   （JSON-RPC 2.0：initialize / tools/list / tools/call）
GET  /      （服务信息）
GET  /health（含实时 NAV）
```

### Claude Desktop 配置（经 mcp-remote 桥接）

```json
{
  "mcpServers": {
    "zhenghe": {
      "command": "npx",
      "args": ["mcp-remote", "https://你的部署域名/mcp"]
    }
  }
}
```

## 部署

Vercel Serverless（Python，单文件 `api/index.py`，无外部服务依赖）。

环境变量（可选）：`BASE_RPC_URL`（默认 `https://mainnet.base.org`）
