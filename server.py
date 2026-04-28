# -*- coding: utf-8 -*-
"""
MCP Server 主入口
"""

import json
from typing import Dict, Any
from fastapi import FastAPI, Request, Response, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .config import mcp_settings
from .auth.api_key import verify_api_key, AgentContext
from .tools import register_all_tools


# 工具注册表
_TOOLS_REGISTRY: Dict[str, Any] = {}


def create_mcp_server() -> FastAPI:
    """创建 MCP HTTP Server"""
    
    app = FastAPI(
        title="正和系统 MCP Server",
        description="""
        正和系统 MCP 接口 - 为 AI Agent 提供积分服务
        
        ## 功能
        - 积分查询：余额、价格、历史
        - 积分操作：转账、铸造、销毁
        - 服务消费：Agent 间交易结算
        - Agent 管理：注册、认证、定价
        
        ## 认证
        所有请求需携带 Authorization Header:
        `Authorization: Bearer sk_live_xxx`
        """,
        version=mcp_settings.MCP_SERVER_VERSION,
    )
    
    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # 注册工具
    register_all_tools(_TOOLS_REGISTRY)
    
    # MCP 协议端点
    @app.post("/mcp")
    async def mcp_endpoint(
        request: Request,
        agent: AgentContext = Depends(verify_api_key)
    ):
        """MCP JSON-RPC 2.0 端点"""
        try:
            body = await request.json()
            
            # 验证 JSON-RPC 格式
            if body.get("jsonrpc") != "2.0":
                return jsonrpc_error(body.get("id"), -32600, "Invalid Request: jsonrpc must be '2.0'")
            
            method = body.get("method", "")
            params = body.get("params", {})
            request_id = body.get("id")
            
            # 路由请求
            if method == "initialize":
                return handle_initialize(request_id, agent)
            elif method == "tools/list":
                return handle_tools_list(request_id, agent)
            elif method == "tools/call":
                return await handle_tools_call(request_id, params, agent)
            elif method == "resources/list":
                return handle_resources_list(request_id)
            else:
                return jsonrpc_error(request_id, -32601, f"Method not found: {method}")
                
        except json.JSONDecodeError:
            return jsonrpc_error(None, -32700, "Parse error: Invalid JSON")
        except Exception as e:
            return jsonrpc_error(
                body.get("id") if 'body' in locals() else None, 
                -32603, 
                f"Internal error: {str(e)}"
            )
    
    def handle_initialize(request_id, agent: AgentContext):
        """处理初始化握手"""
        return JSONResponse(content={
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": mcp_settings.MCP_PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {"listChanged": True},
                    "resources": {"subscribe": False, "listChanged": False},
                },
                "serverInfo": {
                    "name": mcp_settings.MCP_SERVER_NAME,
                    "version": mcp_settings.MCP_SERVER_VERSION,
                },
                "instructions": f"正和系统 MCP 服务。已认证 Agent: {agent.agent_name}"
            }
        })
    
    def handle_tools_list(request_id, agent: AgentContext):
        """返回可用工具列表"""
        tools = []
        for tool in _TOOLS_REGISTRY.values():
            # 根据权限过滤
            if tool.permission in agent.permissions or tool.permission == "read":
                tools.append({
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.input_schema
                })
        
        return JSONResponse(content={
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"tools": tools}
        })
    
    async def handle_tools_call(request_id, params: dict, agent: AgentContext):
        """执行工具调用"""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        # 查找工具
        tool = _TOOLS_REGISTRY.get(tool_name)
        if not tool:
            return jsonrpc_error(request_id, -32602, f"Tool not found: {tool_name}")
        
        # 检查权限
        if tool.permission not in agent.permissions and tool.permission != "read":
            return jsonrpc_error(request_id, -32602, f"Permission denied: {tool.permission}")
        
        try:
            # 执行工具
            result = await tool.execute(arguments, agent)
            
            return JSONResponse(content={
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{
                        "type": "text",
                        "text": json.dumps(result, ensure_ascii=False, indent=2)
                    }]
                }
            })
        except Exception as e:
            return jsonrpc_error(request_id, -32603, str(e))
    
    def handle_resources_list(request_id):
        """返回资源列表"""
        return JSONResponse(content={
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"resources": []}
        })
    
    def jsonrpc_error(request_id, code, message):
        """构造 JSON-RPC 错误响应"""
        return JSONResponse(content={
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message}
        })
    
    # 健康检查
    @app.get("/health")
    async def health_check():
        return {"status": "ok", "service": "zhenghe-mcp"}
    
    # 工具列表（无需认证）
    @app.get("/tools")
    async def list_all_tools():
        """列出所有工具（公开）"""
        return {
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "permission": tool.permission
                }
                for tool in _TOOLS_REGISTRY.values()
            ]
        }
    
    return app


# 创建默认实例
mcp_app = create_mcp_server()
