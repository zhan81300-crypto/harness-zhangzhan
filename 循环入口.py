# -*- coding: utf-8 -*-
"""外层调度器调用入口。

用法：
  python 循环入口.py 状态 --cwd <项目目录>
  python 循环入口.py 开始 --cwd <项目目录> --目标 "..."
  python 循环入口.py 验证 --cwd <项目目录> --结果 <JSON文件>
  python 循环入口.py 下一轮 --cwd <项目目录>

它只推进持久化状态，不负责启动模型。外层 runner 拿到输出后，
自行调用宿主的续轮接口；没有该接口时，把状态交给下一次会话入口。
"""
import argparse
import json
import os
import sys

这里 = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(这里, "hooks-classic"))
from 循环 import 开始, 进入验证, 记录验证, 下一轮, 读状态, 拼注入  # noqa: E402


def 主():
    p = argparse.ArgumentParser()
    p.add_argument("动作", choices=("状态", "开始", "验证", "下一轮"))
    p.add_argument("--cwd", required=True)
    p.add_argument("--目标", default="")
    p.add_argument("--结果", default="")
    a = p.parse_args()
    目录 = os.path.join(os.path.abspath(a.cwd), "harness")
    if a.动作 == "状态":
        结果 = 读状态(目录)
    elif a.动作 == "开始":
        结果 = 开始(目录, a.目标)
    elif a.动作 == "下一轮":
        结果 = 下一轮(目录)
    else:
        if not a.结果:
            p.error("验证动作需要 --结果 JSON文件")
        with open(a.结果, encoding="utf-8") as f:
            结果 = 记录验证(目录, json.load(f))
    print(json.dumps({"state": 结果, "next_prompt": 拼注入(结果)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    主()
