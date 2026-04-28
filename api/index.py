# -*- coding: utf-8 -*-
"""
Vercel Serverless Function 入口
"""
import sys
import os

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from standalone_server import app

# Vercel需要的handler
handler = app
