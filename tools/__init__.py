# -*- coding: utf-8 -*-
"""
MCP 工具模块
"""

from .account_tools import register as register_account_tools
from .transfer_tools import register as register_transfer_tools
from .mint_burn_tools import register as register_mint_burn_tools
from .agent_tools import register as register_agent_tools


def register_all_tools(registry: dict):
    """注册所有工具到注册表"""
    register_account_tools(registry)
    register_transfer_tools(registry)
    register_mint_burn_tools(registry)
    register_agent_tools(registry)
