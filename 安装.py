# -*- coding: utf-8 -*-
"""张展nb666-Harness 手动安装。装到 ~/.claude/，并把四道闸写进 settings.json。

  python 安装.py          装
  python 安装.py 卸载     卸

只加 hooks 这一个键，不动你别的设置。原文件会先备份。
"""
import json
import os
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

包 = os.path.dirname(os.path.abspath(__file__))
家 = os.path.join(os.path.expanduser("~"), ".claude")
技能 = os.path.join(家, "skills", "harness")
钩子目录 = os.path.join(家, "hooks", "harness")
配置 = os.path.join(家, "settings.json")

入口 = (("UserPromptSubmit", None, "接话"),
        ("SessionStart", "startup|clear|compact|resume", "注入"),
        ("PreToolUse", "Write|Edit|NotebookEdit|MultiEdit|Bash", "战略闸"),
        ("Stop", None, "收尾闸"))


def 命令(动作):
    return f'python "{os.path.join(钩子目录, "闸门.py")}" {动作}'


def 读配置():
    if not os.path.isfile(配置):
        return {}
    try:
        with open(配置, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"× {配置} 读不出来（{e}）。先修好它再装，我不敢覆盖。")
        sys.exit(1)


def 写配置(数据):
    if os.path.isfile(配置):
        shutil.copy2(配置, 配置 + ".harness备份")
    with open(配置, "w", encoding="utf-8") as f:
        json.dump(数据, f, ensure_ascii=False, indent=2)


def 是我的(条目):
    for h in 条目.get("hooks", []):
        if "闸门.py" in str(h.get("command", "")):
            return True
    return False


def 装():
    # 技能（含模板）
    os.makedirs(技能, exist_ok=True)
    shutil.copy2(os.path.join(包, "skills", "harness", "SKILL.md"),
                 os.path.join(技能, "SKILL.md"))
    模板目标 = os.path.join(技能, "模板")
    shutil.rmtree(模板目标, ignore_errors=True)
    shutil.copytree(os.path.join(包, "skills", "harness", "模板"), 模板目标)

    # 硬闸
    os.makedirs(钩子目录, exist_ok=True)
    shutil.copy2(os.path.join(包, "hooks-classic", "闸门.py"),
                 os.path.join(钩子目录, "闸门.py"))
    模板邻居 = os.path.join(钩子目录, "模板")
    shutil.rmtree(模板邻居, ignore_errors=True)
    shutil.copytree(os.path.join(包, "skills", "harness", "模板"), 模板邻居)

    # 审查员
    os.makedirs(os.path.join(家, "agents"), exist_ok=True)
    shutil.copy2(os.path.join(包, "agents", "harness-审查员.md"),
                 os.path.join(家, "agents", "harness-审查员.md"))

    # 四道闸写进配置
    数据 = 读配置()
    hooks = 数据.setdefault("hooks", {})
    for 事件, 匹配, 动作 in 入口:
        表 = hooks.setdefault(事件, [])
        表[:] = [c for c in 表 if not 是我的(c)]  # 先撤旧的，避免装两遍
        条目 = {"hooks": [{"type": "command", "command": 命令(动作)}]}
        if 匹配:
            条目["matcher"] = 匹配
        表.append(条目)
    写配置(数据)

    print("装好了。")
    print(f"  技能   {技能}")
    print(f"  硬闸   {钩子目录}")
    print(f"  审查员 {os.path.join(家, 'agents', 'harness-审查员.md')}")
    print(f"  四道闸 已写进 {配置}（原文件备份成 settings.json.harness备份）")
    print()
    print("在任何项目里说「用我的harness」，或者打 /harness。")
    print("没铺 harness 目录的项目完全不生效，一点不打扰。")


def 卸():
    shutil.rmtree(技能, ignore_errors=True)
    shutil.rmtree(钩子目录, ignore_errors=True)
    try:
        os.remove(os.path.join(家, "agents", "harness-审查员.md"))
    except Exception:
        pass

    数据 = 读配置()
    hooks = 数据.get("hooks", {})
    for 事件 in list(hooks):
        hooks[事件] = [c for c in hooks[事件] if not 是我的(c)]
        if not hooks[事件]:
            del hooks[事件]
    if not hooks:
        数据.pop("hooks", None)
    写配置(数据)
    print("卸干净了。各项目里已有的 harness 目录留着没动，那是你的项目记录。")


if __name__ == "__main__":
    卸() if len(sys.argv) > 1 and sys.argv[1] in ("卸载", "卸", "uninstall") else 装()
