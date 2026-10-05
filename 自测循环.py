# -*- coding: utf-8 -*-
"""循环控制器自测：状态、恢复、去重和阻塞。"""
import os
import shutil
import tempfile
import importlib.util

这里 = os.path.dirname(os.path.abspath(__file__))
规格 = importlib.util.spec_from_file_location("循环", os.path.join(这里, "hooks-classic", "循环.py"))
循环 = importlib.util.module_from_spec(规格)
规格.loader.exec_module(循环)
开始 = 循环.开始
进入验证 = 循环.进入验证
记录验证 = 循环.记录验证
下一轮 = 循环.下一轮
拼注入 = 循环.拼注入
读状态 = 循环.读状态


def 主():
    根 = tempfile.mkdtemp(prefix="harness循环自测_")
    try:
        状态 = 开始(根, "让用户能完成核心操作", 最大轮次=3)
        assert 状态["state"] == "EXECUTING"
        assert 状态["attempt"] == 1

        进入验证(根)
        状态 = 记录验证(
            根,
            {"verdict": "not_done", "evidence": ["按钮点击后没有结果"], "gap": "核心操作无法完成"},
            {"root_cause": "入口没有连接到实际动作", "principle": "每个入口都要能完成对应动作"},
            "把按钮接到真实动作并重新操作",
        )
        assert 状态["state"] == "NEEDS_REWORK"
        assert "把按钮接到真实动作" in 拼注入(状态)

        状态 = 下一轮(根)
        assert 状态["state"] == "EXECUTING" and 状态["attempt"] == 2
        进入验证(根)
        状态 = 记录验证(根, {"verdict": "done", "evidence": ["用户完成了核心操作"]})
        assert 状态["state"] == "DONE"

        # 同一失败证据第二次出现时，必须阻塞，不能无限重做。
        根2 = tempfile.mkdtemp(prefix="harness循环去重_")
        try:
            开始(根2, "目标", 最大轮次=3)
            进入验证(根2)
            失败 = {"verdict": "not_done", "evidence": ["同一个缺口"], "gap": "缺口"}
            assert 记录验证(根2, 失败)["state"] == "NEEDS_REWORK"
            下一轮(根2)
            进入验证(根2)
            assert 记录验证(根2, 失败)["state"] == "BLOCKED"
        finally:
            shutil.rmtree(根2, ignore_errors=True)

        # 不可信验证结果必须阻塞，不得伪装完成。
        根3 = tempfile.mkdtemp(prefix="harness循环验证_")
        try:
            开始(根3, "目标")
            进入验证(根3)
            assert 记录验证(根3, {"verdict": "done", "evidence": []})["state"] == "BLOCKED"
        finally:
            shutil.rmtree(根3, ignore_errors=True)
        print("loop self-test passed")
    finally:
        shutil.rmtree(根, ignore_errors=True)


if __name__ == "__main__":
    主()
