# -*- coding: utf-8 -*-
"""张展nb666-Harness 自测。

拿真实输入跑四个入口，看：
  · 该拦的拦不拦
  · 该记的记不记
  · 不误伤正常对话
  · 不把自己锁死

  python 自测.py
"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

这里 = os.path.dirname(os.path.abspath(__file__))
闸门路径 = os.path.join(这里, "hooks-classic", "闸门.py")
模板目录 = os.path.join(这里, "skills", "harness", "模板")

spec = importlib.util.spec_from_file_location("闸门", 闸门路径)
闸门 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(闸门)

通过, 失败 = [], []


def 跑(函数, 数据):
    sys.stdin = io.StringIO(json.dumps(数据, ensure_ascii=False))
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            函数()
    except SystemExit:
        pass
    finally:
        sys.stdin = sys.__stdin__
    return buf.getvalue().strip()


def 断(名, 条件, 细节=""):
    (通过 if 条件 else 失败).append(名)
    print(f"  {'✓' if 条件 else '✗'} {名}")
    if not 条件 and 细节:
        print(f"      {细节}")


def 造项目(状态="待确认"):
    目录 = tempfile.mkdtemp(prefix="harness自测_")
    shutil.copytree(模板目录, os.path.join(目录, "harness"))
    if 状态 == "已确认":
        文件 = os.path.join(目录, "harness", "战略步骤.md")
        with open(文件, encoding="utf-8") as f:
            文 = f.read()
        with open(文件, "w", encoding="utf-8") as f:
            f.write(文.replace("状态：**待确认**", "状态：**已确认**"))
    return 目录


def 主():
    print("=== 战略闸：该拦的拦住 ===")
    for 状态, 工具, 载荷, 想拦 in (
        ("待确认", "Write", {"file_path": "{根}/a.py"}, True),
        ("待确认", "Edit", {"file_path": "{根}/b.txt"}, True),
        ("待确认", "Bash", {"command": "cat > x.py <<EOF"}, True),
        ("待确认", "Write", {"file_path": "{根}/harness/经验日记.md"}, False),
        ("待确认", "Write", {"file_path": "/别的地方/a.py"}, False),
        ("待确认", "Bash", {"command": "ls -la"}, False),
        ("待确认", "Write", {"file_path": "{根}/harness/战略步骤.md"}, False),
        ("已确认", "Write", {"file_path": "{根}/a.py"}, False),
    ):
        根 = 造项目(状态)
        输入 = {k: (v.format(根=根.replace("\\", "/")) if isinstance(v, str) else v)
                for k, v in 载荷.items()}
        出 = 跑(闸门.战略闸, {"cwd": 根, "tool_name": 工具, "tool_input": 输入})
        拦了 = bool(出)
        断(f"{状态} + {工具} + {list(输入.values())[0][-28:]}",
           拦了 == 想拦, f"期望{'拦' if 想拦 else '放行'}，实际{'拦' if 拦了 else '放行'}")
        shutil.rmtree(根, ignore_errors=True)

    print("\n=== 接话：该记的记，不折腾闲聊 ===")
    根 = 造项目()
    出 = 跑(闸门.接话, {"cwd": 根, "prompt": "以后你要说人话，别啰嗦"})
    断("带偏好/纠正的话 → 发出归档指令", "实时归档" in 出)
    出 = 跑(闸门.接话, {"cwd": 根, "prompt": "嗯嗯，继续"})
    断("闲聊 → 一声不吭", not 出)
    流水 = os.path.join(根, "harness", "动作与交互.md")
    with open(流水, encoding="utf-8") as f:
        文 = f.read()
    断("原话落进流水（两句都在）", "说人话" in 文 and "嗯嗯" in 文)
    shutil.rmtree(根, ignore_errors=True)

    print("\n=== 注入：只塞该塞的 ===")
    根 = 造项目()
    出 = 跑(闸门.注入, {"cwd": 根})
    断("塞了总纲索引", "总纲.md" in 出)
    断("塞了战略状态", "战略步骤状态" in 出)
    断("塞了偏好", "用户偏好.md" in 出)
    断("没塞整份战略步骤（太长）", "复现步骤" not in 出)
    根2 = tempfile.mkdtemp(prefix="harness空_")
    断("没 harness 目录 → 一声不吭", not 跑(闸门.注入, {"cwd": 根2}))
    shutil.rmtree(根, ignore_errors=True)
    shutil.rmtree(根2, ignore_errors=True)

    print("\n=== 收尾闸：该拦的拦，不误伤 ===")
    根 = 造项目()
    待办 = os.path.join(根, "harness", ".待归档")

    with open(待办, "w", encoding="utf-8") as f:
        f.write(f"{time.time()}|偏好|说人话\n")
    日记 = os.path.join(根, "harness", "经验日记.md")
    os.utime(日记, (time.time() - 9999, time.time() - 9999))
    断("提了该归档的没记 → 拦住", bool(跑(闸门.收尾闸, {"cwd": 根})))

    with open(待办, "w", encoding="utf-8") as f:
        f.write(f"{time.time()}|偏好|说人话\n")
    with open(日记, "a", encoding="utf-8") as f:
        f.write("\n- 记了一笔\n")
    断("记过了 → 放行", not 跑(闸门.收尾闸, {"cwd": 根}))

    def 写对话(文本):
        甲 = os.path.join(根, "t.jsonl")
        with open(甲, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "assistant", "message": {"content":
                    [{"type": "text", "text": 文本}]}}, ensure_ascii=False) + "\n")
        return 甲

    断("用形式指标汇报 → 拦住",
       bool(跑(闸门.收尾闸, {"cwd": 根, "transcript_path": 写对话("12 项全部通过，哈希校验一致。")})))
    断("在讨论这些词 → 不误伤",
       not 跑(闸门.收尾闸, {"cwd": 根, "transcript_path": 写对话("我把全绿和验收通过这些指标砍掉了。")}))
    断("说完成没给结论 → 拦住",
       bool(跑(闸门.收尾闸, {"cwd": 根, "transcript_path": 写对话("已完成全部开发工作。")})))
    断("给了结论 → 放行",
       not 跑(闸门.收尾闸, {"cwd": 根, "transcript_path": 写对话("我打开跑了一遍，做到了。")}))

    print("\n=== 不把自己锁死 ===")
    根3 = tempfile.mkdtemp(prefix="harness没铺_")  # 故意不铺 harness
    断("没 harness 目录的项目，四个入口全都不动",
       not any(跑(f, {"cwd": 根3}) for f in (闸门.接话, 闸门.注入, 闸门.战略闸, 闸门.收尾闸)))
    断("收尾闸认「已经拦过一次」的标记",
       not 跑(闸门.收尾闸, {"cwd": 根, "stop_hook_active": True}))
    shutil.rmtree(根, ignore_errors=True)
    shutil.rmtree(根3, ignore_errors=True)

    print()
    if 失败:
        print(f"❌ {len(失败)} 项没过：{'、'.join(失败)}")
        sys.exit(1)
    print(f"✅ 全过（{len(通过)} 项）")


if __name__ == "__main__":
    主()
