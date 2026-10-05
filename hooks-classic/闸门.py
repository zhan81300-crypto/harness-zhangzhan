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

try:
    from 循环 import 读状态 as 读循环状态, 拼注入 as 拼循环注入
except ImportError:
    读循环状态 = lambda 目录: None
    拼循环注入 = lambda 状态: ""

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


# ---------- 经验的四栏解析与检索 ----------
四栏 = ("现象", "根因", "原则", "什么时候该想起来")


def 拆经验(文本):
    """把 经验日记.md 拆成一条条经验，每条取四个栏。

    结构长这样：
        ### 标题
        - **现象**：...
        - **根因**：...
        - **原则**：...
        - **什么时候该想起来**：...
    返回 [{标题, 现象, 根因, 原则, 触发}, ...]，只留四栏齐全的。
    """
    条 = []
    现在 = None
    for 行 in 文本.splitlines():
        m = re.match(r"^#{2,4}\s+(.*)", 行)
        if m:
            标题 = m.group(1).strip()
            # 「一条经验长这样」那段是示范，不算
            if "长这样" in 标题 or "每轮记录" in 标题:
                现在 = None
                continue
            现在 = {"标题": 标题, "现象": "", "根因": "", "原则": "", "触发": ""}
            条.append(现在)
            continue
        if not 现在:
            continue
        m = re.match(r"^\s*[-*]\s*\*\*(现象|根因|原则|什么时候该想起来)\*\*[：:]\s*(.*)", 行)
        if m:
            键 = {"现象": "现象", "根因": "根因", "原则": "原则",
                  "什么时候该想起来": "触发"}[m.group(1)]
            现在[键] = m.group(2).strip()
    return [x for x in 条 if all(x[k] for k in ("现象", "根因", "原则", "触发"))]


# 极其常见的词不能当触发词，否则条条都命中。
常用词 = set("""
的 了 是 在 和 就 都 而 及 与 着 或 一个 没有 我们 你们 他们 这个 那个
什么 怎么 因为 所以 但是 如果 可以 需要 应该 时候 问题 东西 地方 现在
然后 还是 就是 不是 一样 这样 那样 知道 觉得 正在 一旦 凡是 比如
例如 遇到 涉及 出现 发现 想起 记得 之前 之后 以后 当下 当前 开始 继续
任何 所有 每一 每次 某个 某些 有关 关于 进行 使用 采用 通过 根据 按照
""".split())

# 单个常用字。切片时只要沾上这些字，那个切片就不算信号。
常用字 = set("的一了是在和就都而及与着或个我你他这那什么怎因所为但如果可要应该"
            "时问西地现然还很也才把被让给对从到向于并且以及把被没不有会能")


def 切信号(场景):
    """从一个触发场景里切出能当信号找的片段。

    中文没有空格，不能按"整串汉字"当一个词——那样整句话会变成一块，
    永远匹配不上。改成按字滑窗，切 2 字和 3 字的片段。

    切片里只要沾了常用字就丢掉（"正在""时候"这种当不了信号）。
    """
    信号 = set()
    for 串 in re.findall(r"[一-龥]+", 场景):
        for 长 in (2, 3):
            for i in range(len(串) - 长 + 1):
                片 = 串[i:i + 长]
                if 片 in 常用词:
                    continue
                if any(字 in 常用字 for 字 in 片):
                    continue
                信号.add(片)
    # 英文标识符整词算一个
    for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", 场景):
        if w not in 常用词:
            信号.add(w)
    return 信号


def 找触发(话, 经验条):
    """拿这句话去比对每条经验的「什么时候该想起来」，命中的返回。

    命中规则：一个 3 字片段对上就算，或者两个不同的 2 字片段对上。
    单靠一个 2 字片段太容易误伤，所以不算。
    这样既容得下说法不完全一样，又不会见词就召回。
    """
    命中 = []
    for 条 in 经验条:
        信号 = 切信号(条["触发"])
        if not 信号:
            continue
        对上的 = [片 for 片 in 信号 if 片 in 话]
        if not 对上的:
            continue
        三字 = [片 for 片 in 对上的 if len(片) >= 3]
        两字 = {片 for 片 in 对上的 if len(片) == 2}
        if 三字 or len(两字) >= 2:
            命中.append((条, sorted(set(三字) | 两字)))
    return 命中


def 拼召回(召回):
    """把命中的经验拼成一段话，塞到 AI 眼前。"""
    行 = ["[harness 经验召回] 这件事你以前踩过，现在就该想起来："]
    for 条, 词 in 召回[:3]:          # 最多三条，多了成噪音
        行.append(f"\n▸ {条['标题']}")
        行.append(f"  · 原则：{条['原则']}")
        行.append(f"  · 当初为什么错：{条['根因']}")
        行.append(f"  ·（对上了：{'、'.join(词)}）")
    行.append("\n先把上面几条对照当前这一步做一遍，再动手。")
    return "\n".join(行)


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

    循环提示 = 拼循环注入(读循环状态(目录))
    if 循环提示:
        print(循环提示)

    # 1. 先把原话按时间落下来，这一步是死的，漏不掉
    时刻 = datetime.now().strftime("%m-%d %H:%M")
    摘 = 原话 if len(原话) <= 120 else 原话[:120] + "…"
    追加(os.path.join(目录, "动作与交互.md"),
        f"\n- `{时刻}` 用户说：{摘.replace(chr(10), ' ')}\n")

    # 2. 认出这句里有没有该归档的东西
    有偏好 = any(w in 原话 for w in 偏好信号)
    有纠正 = any(w in 原话 for w in 纠正信号)
    有要求 = any(w in 原话 for w in 要求信号)

    # 2.5 经验召回：这句话对上了哪几条旧经验？
    #     对上就当场塞到 AI 眼前——不靠它自己想起来。
    召回 = []
    try:
        经验条 = 拆经验(读(os.path.join(目录, "经验日记.md")))
        if 经验条:
            召回 = 找触发(原话, 经验条)
    except Exception:
        pass

    if not (有偏好 or 有纠正 or 有要求):
        # 没有要归档的，但可能对上了旧经验 —— 那种也要说
        if 召回:
            print(拼召回(召回))
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

    if 召回:
        print(拼召回(召回))
        print()

    指令 = [f"[harness 实时归档] 这句话里有{'和'.join(类型)}，现在就归档，别等：",
            "· 往 `harness/经验日记.md` 加一条，**必须填全四栏**：",
            "  现象（发生了什么，可验证的事实）／根因（根子上为什么，不是「我粗心了」）／",
            "  原则（能搬到别处的一句规矩）／什么时候该想起来（下次遇到什么情况该想起它）。",
            "  最后一栏最要紧——这条经验以后就是靠它，才会在对的时候自己冒出来。"]
    if 有偏好:
        指令.append("· 这条带偏好，同时追加进 `harness/用户偏好.md`，用他自己的说法，别改意思。")
    if 有纠正:
        指令.append("· 这条是在纠我。根因栏写清我错在哪个判断上，别写「不够仔细」这种废话。")
    if 有要求 and not 有纠正:
        指令.append("· 如果这条要求是通用的（换任何项目都成立），除了记进项目经验，"
                    "也回填一份到技能的 `通用经验.md`。")
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
    循环状态 = 读循环状态(目录)
    循环提示 = 拼循环注入(循环状态)
    if 循环提示:
        块.append(循环提示)
    状态 = re.search(r"^状态[:：]\s*\**\s*([^\s（(*]+)", 读(os.path.join(目录, "战略步骤.md")), re.M)
    if 状态:
        块.append(f"战略步骤状态：{状态.group(1)}")
    for 名, 段名, 上限 in (("用户偏好.md", None, 1000),
                          ("目标与原则.md", None, 1100)):
        文本 = 读(os.path.join(目录, 名))
        if not 文本:
            continue
        段 = 取段(文本, 段名, 上限) if 段名 else 文本[:上限].rstrip()
        if 段:
            块.append(f"—— {名} ——\n{段}")

    # 这个项目已经踩出来的坑，塞摘要（完整内容在文件里，需要时自己读）
    项目经验 = 拆经验(读(os.path.join(目录, "经验日记.md")))
    if 项目经验:
        条 = [f"· {x['标题']} → {x['原则']}" for x in 项目经验[:12]]
        块.append("—— 本项目已踩过的坑（详细在 经验日记.md）——\n" + "\n".join(条))

    # 跨项目通用经验，这是跟着人走的，每次都要塞
    通用 = 拆经验(读(os.path.join(os.path.dirname(模板目录), "通用经验.md")))
    if 通用:
        条 = [f"· {x['标题']} → {x['原则']}" for x in 通用[:12]]
        块.append("—— 通用经验（换项目也算数）——\n" + "\n".join(条))

    块.append("规矩：只按 战略步骤.md 走，不即兴发挥；改动前先看影响范围，小改只查受影响部分；"
              "结论只有 做到了 / 没做到，真打开用一遍综合判断，不摆指标不摆过程；"
              "用户每说一句有用的话当场提炼归档（四栏填全）；"
              "要改方向先提到战略口径跟用户确认，再改对应文件。")
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
                     "属于偏好的追加进 用户偏好.md；是纠我的，写清错在哪、根子上为什么错。"
                     "一两句，口语化，不抄原话，别写已经有的。")

    # 4a2 经验写全了没 —— 四栏缺一栏就等于没记
    try:
        日记文本 = 读(os.path.join(目录, "经验日记.md"))
        if 日记文本:
            所有条 = []
            现在 = None
            for 行 in 日记文本.splitlines():
                m = re.match(r"^#{2,4}\s+(.*)", 行)
                if m:
                    标题 = m.group(1).strip()
                    if "长这样" in 标题 or "每轮记录" in 标题:
                        现在 = None
                        continue
                    现在 = {"标题": 标题, "现象": "", "根因": "", "原则": "", "触发": ""}
                    所有条.append(现在)
                    continue
                if not 现在:
                    continue
                m = re.match(r"^\s*[-*]\s*\*\*(现象|根因|原则|什么时候该想起来)\*\*[：:]\s*(.*)", 行)
                if m:
                    键 = {"现象": "现象", "根因": "根因", "原则": "原则",
                          "什么时候该想起来": "触发"}[m.group(1)]
                    现在[键] = m.group(2).strip()
            残缺 = [x for x in 所有条
                    if not all(x[k] for k in ("现象", "根因", "原则", "触发"))]
            if 残缺:
                缺的 = []
                for x in 残缺[:3]:
                    少 = [k for k in ("现象", "根因", "原则", "触发") if not x[k]]
                    缺的.append(f"「{x['标题']}」缺：{'、'.join(少)}")
                阻断(
                    "经验日记里有几条没按四栏写全，等于没记：\n" + "\n".join(缺的) + "\n\n"
                    "四栏是：现象（发生了什么，可验证）／根因（根子上为什么，"
                    "不是「我粗心了」）／原则（能搬到别处的一句规矩）／"
                    "什么时候该想起来（下次遇到什么情况该想起它）。\n"
                    "最后一栏最要紧——写不出触发场景，说明这条还没抽象到位，"
                    "下次它就永远不会在需要的时候冒出来。补全它。")
    except Exception:
        pass

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
