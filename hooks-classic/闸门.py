# -*- coding: utf-8 -*-
"""张展nb666-Harness · 命令钩子闸门

这是**地基**，不是增强层。mod 只在交互会话里生效，无人值守时全失效；
而"战略没确认不许写产物"必须任何模式下都拦得住。所以硬闸放这里。

四个入口：
  接话   每次用户说完话：原话落进流水，认出要求/偏好/纠正就当场要求归档
  注入   新开会话/清屏/压缩上下文：把偏好、原则、通病清单塞回上下文
  战略闸 写产物前：战略步骤没经用户确认就拦住（含 Bash 绕过口）
  收尾闸 这轮结束前：该记的没记、该判断的没判断，拦住
"""
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime

# Windows 上 stdin/stdout 默认不是 UTF-8，路径里的中文会被搞坏。
# 必须在读输入之前就掰过来。
for _流 in (sys.stdin, sys.stdout, sys.stderr):
    try:
        _流.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _找模板():
    """装好之后在技能目录里，在包里在技能的上一层。两种都得认。"""
    这里 = os.path.dirname(os.path.abspath(__file__))
    上 = os.path.dirname(这里)
    for p in (os.path.join(这里, "模板"),                                   # 同目录
              os.path.join(上, "skills", "harness", "模板"),               # 包里
              os.path.join(上, "模板"),                                    # 装好
              os.path.join(上, "harness模板")):                            # 旧布局
        if os.path.isdir(p):
            return p
    return os.path.join(这里, "模板")


模板目录 = _找模板()

关键词 = ("用我的harness", "开harness", "展的harness", "张展nb666")

偏好信号 = ("偏好", "以后", "永远", "任何时候", "记住", "放进记忆", "跨对话",
            "我不喜欢", "我喜欢", "别再", "不要再", "我讨厌", "我要求")
纠正信号 = ("错了", "不对", "跑偏", "你没", "你怎么", "重做", "推翻", "我说过",
            "不是这个", "又忘", "说人话", "别啰嗦", "我不是这个意思")
要求信号 = ("必须", "禁止", "不许", "不能", "应该", "要做到", "改成", "加上",
            "去掉", "我要", "给我", "希望", "需要")

结论词 = ("做到了", "没做到", "做不到")
完成词 = ("已完成", "全部完成", "已交付", "做完了", "完成了", "已实现", "搞定了")
禁词 = ("全绿", "全部通过", "测试通过", "验收通过", "检查通过", "门禁",
        "冻结", "版本绑定", "覆盖率", "全部检查项", "打勾", "全部达标")
禁模式 = (r"\d+\s*项(?:全部)?(?:通过|一致|达标|无问题)",
          r"(?:哈希|指纹)(?:校验|比对|一致|匹配)",
          r"\d+\s*/\s*\d+\s*(?:项|个)?\s*通过")
# 在"讨论这些词"而不是"用这些词下结论"，别误伤
讨论词 = ("砍掉", "禁用", "禁止", "不许", "不能用", "不再用", "取代", "去掉",
          "删掉", "改掉", "拦住", "拦下", "别用", "而不是", "不是靠")

# Bash 里看起来在写盘的样子。挡得住常见的，挡不住全部——这是知情的取舍。
写盘样 = re.compile(
    r"(^|[;&|]\s*)(cat\s*>|tee\b|sed\s+-i|python[0-9.]*\s+-c|node\s+-e|perl\s+-i|>\s*[^\s|&;]+)")


def 读输入():
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def 找目录(起点):
    """从 cwd 往上找 harness 目录，最多 5 层。"""
    p = os.path.abspath(起点 or os.getcwd())
    for _ in range(5):
        d = os.path.join(p, "harness")
        if os.path.isfile(os.path.join(d, "总纲.md")):
            return d
        上 = os.path.dirname(p)
        if 上 == p:
            break
        p = 上
    return None


def 读(路径):
    try:
        with open(路径, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""


def 追加(路径, 文本):
    try:
        with open(路径, "a", encoding="utf-8") as f:
            f.write(文本)
        return True
    except Exception:
        return False


def 取段(文本, 关键词, 上限=900):
    """抓 markdown 里标题含关键词的那一段。"""
    收, 在段内, 级别 = [], False, 0
    for l in 文本.splitlines():
        m = re.match(r"^(#+)\s*(.*)", l)
        if m:
            if 在段内:
                break
            if 关键词 in m.group(2):
                在段内, 级别 = True, len(m.group(1))
                continue
        if 在段内:
            收.append(l)
    return "\n".join(收).strip()[:上限]


def 待办文件(目录):
    return os.path.join(目录, ".待归档")


def 阻断(消息, 类型=""):
    # PreToolUse 和 Stop 的拦法不一样：
    # Stop 给 decision=block 就够；PreToolUse 还必须给 permissionDecision=deny，
    # 少了这层，工具照跑。
    out = {"decision": "block", "reason": 消息}
    if 类型 == "PreToolUse":
        out["hookSpecificOutput"] = {"hookEventName": "PreToolUse",
                                     "permissionDecision": "deny",
                                     "permissionDecisionReason": 消息}
    print(json.dumps(out, ensure_ascii=False))
    sys.exit(0)


# ---------- 入口1：接话 ----------
def 接话():
    数据 = 读输入()
    原话 = 数据.get("prompt") or 数据.get("user_message") or ""
    if not 原话:
        return

    目录 = 找目录(数据.get("cwd"))

    # 喊了关键词但项目里还没铺：照模板铺好
    if not 目录 and any(k in 原话 for k in 关键词):
        新目录 = os.path.join(数据.get("cwd") or os.getcwd(), "harness")
        try:
            shutil.copytree(模板目录, 新目录)
        except Exception as e:
            print(f"想给本项目铺 harness 目录但失败了（{e}）。"
                  f"手动把 {模板目录} 复制成 {新目录} 再继续。")
            return
        print(f"已按模板在本项目铺好 harness 目录：{新目录}\n"
              "立刻按 harness 的流程走阶段一：穷尽调查现状、列出全部问题、"
              "分主干与配套、抽象宏观战略、用复现思路写战略步骤，"
              "跟用户确认后才把 战略步骤.md 顶部改成「状态：已确认」。\n"
              "同时把用户这句话提炼进 经验日记.md，属于偏好的写进 用户偏好.md。")
        return

    if not 目录:
        return  # 本项目没启用，完全不打扰

    # 1. 先把原话按时间落下来，这一步是死的，漏不掉
    时刻 = datetime.now().strftime("%m-%d %H:%M")
    摘 = 原话 if len(原话) <= 120 else 原话[:120] + "…"
    追加(os.path.join(目录, "动作与交互.md"),
        f"\n- `{时刻}` 用户说：{摘.replace(chr(10), ' ')}\n")

    # 2. 认出这句里有没有该归档的东西
    有偏好 = any(w in 原话 for w in 偏好信号)
    有纠正 = any(w in 原话 for w in 纠正信号)
    有要求 = any(w in 原话 for w in 要求信号)
    if not (有偏好 or 有纠正 or 有要求):
        return  # "继续""嗯嗯"这种，不折腾

    类型 = []
    if 有偏好:
        类型.append("偏好")
    if 有纠正:
        类型.append("纠正")
    if 有要求:
        类型.append("要求")

    # 3. 记一笔待办，收尾闸靠它查到底记了没
    追加(待办文件(目录), f"{time.time()}|{'/'.join(类型)}|{摘[:60]}\n")

    指令 = [f"[harness 实时归档] 这句话里有{'和'.join(类型)}，现在就归档，别等：",
            "· 往 经验日记.md 加一条：用户这轮想干啥、要解决什么问题、我该怎么改。"
            "一两句，口语化，不抄原话。"]
    if 有偏好:
        指令.append("· 这条带偏好，同时追加进 用户偏好.md，用他自己的说法，别改意思。")
    if 有纠正:
        指令.append("· 这条是在纠我。把我错在哪、根子上为什么错，写进 经验日记.md 的通病清单，"
                    "以后别再犯。只记新东西，已经有的别重复写。")
    指令.append("先归档再干活。这轮结束前没归档会被拦下。")
    print("\n".join(指令))


# ---------- 入口2：注入 ----------
def 注入():
    """只塞几乎不动的那几块。步骤和日记太长，不塞。"""
    数据 = 读输入()
    目录 = 找目录(数据.get("cwd"))
    if not 目录:
        return
    块 = [f"[张展nb666-Harness 已在本项目启用] {os.path.join(目录, '总纲.md')}（索引，link 到各分文件）"]
    状态 = re.search(r"^状态[:：]\s*\**\s*([^\s（(*]+)", 读(os.path.join(目录, "战略步骤.md")), re.M)
    if 状态:
        块.append(f"战略步骤状态：{状态.group(1)}")
    for 名, 段名, 上限 in (("用户偏好.md", None, 1000),
                          ("目标与原则.md", None, 1100),
                          ("经验日记.md", "通病清单", 800)):
        文本 = 读(os.path.join(目录, 名))
        if not 文本:
            continue
        段 = 取段(文本, 段名, 上限) if 段名 else 文本[:上限].rstrip()
        if 段:
            块.append(f"—— {名} ——\n{段}")
    块.append("规矩：只按 战略步骤.md 走，不即兴发挥；改动前先看影响范围，小改只查受影响部分；"
              "结论只有 做到了 / 没做到，真打开用一遍综合判断，不摆指标不摆过程；"
              "用户每说一句有用的话当场提炼归档；要改方向先提到战略口径跟用户确认，再改对应文件。")
    print("\n\n".join(块))


# ---------- 入口3：战略闸 ----------
def 战略闸():
    数据 = 读输入()
    目录 = 找目录(数据.get("cwd"))
    if not 目录:
        return

    工具 = 数据.get("tool_name") or ""
    输入 = 数据.get("tool_input") or {}
    项目根 = os.path.dirname(目录)

    def 在里面(子, 父):
        try:
            return os.path.commonpath([子, os.path.abspath(父)]) == os.path.abspath(父)
        except ValueError:
            return False

    def 拦不拦():
        return not re.search(r"^状态[:：]\s*\**\s*已确认", 读(os.path.join(目录, "战略步骤.md")), re.M)

    # --- Bash 是个绕过口：cat > 文件、tee、sed -i、python -c 都能写盘
    if 工具 == "Bash":
        命令 = 输入.get("command") or ""
        if not 写盘样.search(命令):
            return
        # 只写 harness 目录自己的文档，放行
        if re.search(r"harness[/\\]", 命令):
            return
        if not 拦不拦():
            return
        阻断(
            "[harness 战略闸] 战略还没经用户确认，现在不能写产物。\n"
            f"拦下的命令：{命令[:200]}\n\n"
            "先做完阶段一：穷尽调查 → 列出全部问题 → 分主干与配套 → 抽象宏观战略 → "
            "用复现思路写 战略步骤.md → 跟用户确认，然后把顶部改成「状态：已确认」。\n"
            "禁止为了让流程跑通而删变量、换问题、跳过难处理的地方。沉默不等于同意。", "PreToolUse")
        return

    # --- 文件工具
    路径 = ""
    for k in ("file_path", "path", "notebook_path", "filePath"):
        v = 输入.get(k)
        if isinstance(v, str) and v:
            路径 = v
            break
    if not 路径:
        return
    绝对 = os.path.abspath(路径)
    if ".claude" in 绝对.replace("\\", "/").split("/"):
        return  # harness 自己的安装文件，不是本项目产物
    if 在里面(绝对, 目录):
        return  # 写 harness 目录自己的文件，放行
    if not 在里面(绝对, 项目根):
        return  # 不在这个项目里，不管
    if not 拦不拦():
        return
    阻断(
        f"[harness 战略闸] 战略还没经用户确认，现在不能写产物。\n"
        f"拦下的文件：{路径}\n\n"
        "先做完阶段一，再回来：\n"
        "1. 穷尽调查——相关的东西真读一遍，不抽查、不猜\n"
        "2. 列出全部问题——结合实际情况列全，不筛不删\n"
        "3. 分主干与配套——谁依赖谁，先做哪个\n"
        "4. 抽象宏观战略——在什么目标和原则下，为了做什么，用什么方法，做成什么样\n"
        "5. 用复现思路写 战略步骤.md——每步写明影响范围、怎么算做到了\n"
        "6. 拿给用户确认，点头之后把顶部改成「状态：已确认」\n\n"
        "禁止为了让流程跑通而删变量、换问题、跳过难处理的地方。沉默不等于同意。", "PreToolUse")


# ---------- 入口4：收尾闸 ----------
def 收尾闸():
    数据 = 读输入()
    if 数据.get("stop_hook_active"):
        return
    目录 = 找目录(数据.get("cwd"))
    if not 目录:
        return

    # 4a 该归档的归了没
    待办 = 待办文件(目录)
    if os.path.isfile(待办):
        条目 = [l for l in 读(待办).splitlines() if l.strip()]
        if 条目:
            起点 = min(float(l.split("|")[0]) for l in 条目
                      if l.split("|")[0].replace(".", "").isdigit())
            动过 = False
            for 名 in ("经验日记.md", "用户偏好.md"):
                f = os.path.join(目录, 名)
                if os.path.isfile(f) and os.path.getmtime(f) >= 起点 - 1:
                    动过 = True
            欠 = "；".join(l.split("|", 2)[-1] for l in 条目[-3:])
            try:
                os.remove(待办)  # 先清掉，别让它下一轮再拦一次
            except Exception:
                pass
            if not 动过:
                阻断(f"这轮用户提了{len(条目)}处该归档的东西，你一个字没记：{欠}\n"
                     "现在补：往 经验日记.md 写清他想干啥、要解决什么问题、我该怎么改；"
                     "属于偏好的追加进 用户偏好.md；是纠我的，把根子上的原因写进通病清单。"
                     "一两句，口语化，不抄原话，别写已经有的。")

    # 4b 说完成有没有真判断
    路径 = 数据.get("transcript_path")
    if not 路径 or not os.path.isfile(路径):
        return
    末条 = ""
    try:
        with open(路径, "rb") as fb:
            fb.seek(0, os.SEEK_END)
            大小 = fb.tell()
            fb.seek(max(0, 大小 - 400_000))
            行列 = fb.read().decode("utf-8", errors="replace").splitlines()
        if 大小 > 400_000 and 行列:
            行列 = 行列[1:]
        for 行 in 行列:
            行 = 行.strip()
            if not 行:
                continue
            try:
                o = json.loads(行)
            except Exception:
                continue
            if o.get("type") != "assistant":
                continue
            内容 = (o.get("message") or {}).get("content")
            if isinstance(内容, list):
                t = "".join(c.get("text", "") for c in 内容
                            if isinstance(c, dict) and c.get("type") == "text")
                if t.strip():
                    末条 = t
    except Exception:
        return
    if not 末条.strip():
        return

    命中 = []
    for 句 in re.split(r"[。！？\n；;]+", 末条):
        if not 句.strip() or any(d in 句 for d in 讨论词):
            continue
        命中 += [w for w in 禁词 if w in 句]
        命中 += [m.group(0) for p in 禁模式 for m in [re.search(p, 句)] if m]
    if 命中:
        阻断(f"汇报里用了形式化指标：{'、'.join(dict.fromkeys(命中))}。\n"
             "检查项只能用来发现问题，不能定义完成。重写这段：别摆指标别摆判断过程，"
             "真打开或运行一遍，站最终使用者角度综合判断它在实际场景里行不行，"
             "直接给结论——做到了 / 没做到。没做到就说清哪儿不行。")
    if any(w in 末条 for w in 完成词) and not any(w in 末条 for w in 结论词):
        阻断("你说了完成，但没给判断结果。\n"
             "先真打开或运行一遍成品，站最终使用者角度看它在实际场景里到底行不行，"
             "然后直接说 做到了 或 没做到。别摆指标，别摆过程，别留中间档。"
             "没做到就说清哪儿不行，直接改。")


if __name__ == "__main__":
    {"接话": 接话, "注入": 注入, "战略闸": 战略闸, "收尾闸": 收尾闸}.get(
        sys.argv[1] if len(sys.argv) > 1 else "", lambda: None)()
