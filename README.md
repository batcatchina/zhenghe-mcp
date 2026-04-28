# 正和MCP Server

> AI Agent积分服务 - 为Agent提供积分查询、消费、注册等能力

## 功能

- 积分查询：余额、价格
- 服务消费：Agent间交易结算
- Agent注册：身份管理和认证

## MCP工具

| 工具 | 说明 |
|------|------|
| get_balance | 查询积分余额 |
| get_price | 查询当前价格 |
| register_agent | 注册新Agent |
| consume | 消费服务（核心交易） |

## 部署

Vercel + Neon PostgreSQL

## 环境变量

| 变量 | 说明 |
|------|------|
| DATABASE_URL | PostgreSQL连接字符串 |
| SECRET_KEY | 安全密钥 |
