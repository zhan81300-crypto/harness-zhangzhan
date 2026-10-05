# -*- coding: utf-8 -*-
"""Harness 反馈循环的持久化控制器。

这个文件只负责状态，不负责替模型做决定：
- 失败不会丢；
- 下一次入口一定能读到待修任务；
- 同一失败不重复制造轮次；
- 达到上限或无法验证时停在 BLOCKED。

真正的模型续轮由宿主或外层 runner 调用，不能在 Stop 钩子里递归启动。
"""
import hashlib
import json
import os
import tempfile
import time
import uuid
from contextlib import contextmanager

状态文件名 = ".循环状态.json"
锁文件名 = ".循环状态.lock"
默认最大轮次 = 3
合法状态 = {"IDLE", "EXECUTING", "VERIFYING", "NEEDS_REWORK", "DONE", "BLOCKED"}


@contextmanager
def _锁(路径):
    """用独占创建做轻量跨进程锁，失败时由调用方决定是否阻塞。"""
    锁 = 路径 + ".lock"
    开始 = time.time()
    while True:
        try:
            fd = os.open(锁, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            break
        except FileExistsError:
            if time.time() - 开始 > 5:
                raise TimeoutError("循环状态锁等待超时")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            os.remove(锁)
        except FileNotFoundError:
            pass


def _现在():
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def _状态路径(目录):
    return os.path.join(目录, 状态文件名)


def _读文件(路径):
    try:
        with open(路径, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def 读状态(目录):
    return _读文件(_状态路径(目录))


def _写原子(路径, 数据):
    父 = os.path.dirname(路径)
    fd, 临时 = tempfile.mkstemp(prefix=".循环状态-", suffix=".tmp", dir=父)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(数据, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(临时, 路径)
    finally:
        if os.path.exists(临时):
            os.remove(临时)


def 写状态(目录, 状态):
    os.makedirs(目录, exist_ok=True)
    路径 = _状态路径(目录)
    with _锁(路径):
        当前 = _读文件(路径)
        if 当前 and 当前.get("run_id") != 状态.get("run_id"):
            raise RuntimeError("循环状态已被另一项任务占用")
        # 调用方必须在锁内完成读、改、写；这里保留整份状态的原子落盘。
        状态 = dict(状态)
        状态["updated_at"] = _现在()
        _写原子(路径, 状态)
    return 状态


def _改状态(目录, 修改):
    """在同一把锁里读、改、写，避免两个入口用同一 run_id 互相覆盖。"""
    os.makedirs(目录, exist_ok=True)
    路径 = _状态路径(目录)
    with _锁(路径):
        状态 = _读文件(路径)
        if not 状态:
            raise RuntimeError("没有活动循环")
        新 = 修改(dict(状态))
        新["updated_at"] = _现在()
        _写原子(路径, 新)
        return 新


def _证据指纹(验证):
    原料 = {
        "gap": (验证 or {}).get("gap", ""),
        "evidence": (验证 or {}).get("evidence", []),
        "paths": [x.get("path", "") for x in (验证 or {}).get("artifact_observed", [])],
    }
    return hashlib.sha256(json.dumps(原料, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def 开始(目录, 目标, 最大轮次=默认最大轮次):
    旧 = 读状态(目录)
    if 旧 and 旧.get("state") in {"EXECUTING", "VERIFYING", "NEEDS_REWORK"}:
        return 旧
    状态 = {
        "run_id": "run-" + uuid.uuid4().hex[:12],
        "goal": 目标,
        "state": "EXECUTING",
        "attempt": 1,
        "max_attempts": max(1, int(最大轮次)),
        "history": [],
        "last_failure": None,
        "stop_reason": None,
        "created_at": _现在(),
        "updated_at": _现在(),
    }
    return 写状态(目录, 状态)


def 进入验证(目录):
    def 改(状态):
        if 状态.get("state") != "EXECUTING":
            return 状态
        状态["state"] = "VERIFYING"
        return 状态
    return _改状态(目录, 改)


def 记录验证(目录, 验证, 诊断=None, 修正=None):
    """消费结构化验证结果，决定完成、待修或阻塞。"""
    结论 = (验证 or {}).get("verdict")
    证据 = (验证 or {}).get("evidence") or []
    if 结论 not in {"done", "not_done", "blocked"} or not 证据:
        return _改状态(目录, lambda 状态: {
            **状态,
            "state": "BLOCKED",
            "stop_reason": "验证结果不可信：必须有 done、not_done、blocked 和真实证据",
        })

    def 改(状态):
        if 状态.get("state") not in {"EXECUTING", "VERIFYING"}:
            raise RuntimeError("当前没有可验证的活动循环")
        本轮 = {
            "number": 状态.get("attempt", 1),
            "verification": 验证,
            "diagnosis": 诊断,
            "correction": 修正,
            "finished_at": _现在(),
        }
        状态.setdefault("history", []).append(本轮)
        if 结论 == "done":
            状态["state"] = "DONE"
            状态["last_failure"] = None
            状态["stop_reason"] = None
            return 状态
        if 结论 == "blocked":
            状态["state"] = "BLOCKED"
            状态["stop_reason"] = (验证 or {}).get("gap") or "验证无法执行"
            return 状态

        指纹 = _证据指纹(验证)
        之前 = 状态.get("last_failure") or {}
        if 指纹 == 之前.get("evidence_id"):
            状态["state"] = "BLOCKED"
            状态["stop_reason"] = "同一失败证据再次出现，上一轮修正没有改变结果"
            return 状态
        if 状态.get("attempt", 1) >= 状态.get("max_attempts", 默认最大轮次):
            状态["state"] = "BLOCKED"
            状态["stop_reason"] = f"已达到最大修正轮次（{状态['max_attempts']}）"
            状态["last_failure"] = {"evidence_id": 指纹, "gap": 验证.get("gap", "")}
            return 状态

        状态["state"] = "NEEDS_REWORK"
        状态["last_failure"] = {
            "evidence_id": 指纹,
            "gap": 验证.get("gap", ""),
            "evidence": 证据,
            "diagnosis": 诊断,
            "correction": 修正,
        }
        状态["stop_reason"] = None
        return 状态
    return _改状态(目录, 改)


def 下一轮(目录):
    def 改(状态):
        if 状态.get("state") != "NEEDS_REWORK":
            return 状态
        状态["attempt"] = int(状态.get("attempt", 1)) + 1
        状态["state"] = "EXECUTING"
        return 状态
    return _改状态(目录, 改)


def 阻塞(目录, 原因):
    return _改状态(目录, lambda 状态: {
        **状态,
        "state": "BLOCKED",
        "stop_reason": 原因,
    })


def 拼注入(状态):
    if not 状态 or 状态.get("state") != "NEEDS_REWORK":
        return ""
    失败 = 状态.get("last_failure") or {}
    诊断 = 失败.get("diagnosis") or {}
    return ("[harness 循环] 上一轮真实验证结论：没做到。现在必须进入下一轮修正，不能结束。\n"
            f"目标：{状态.get('goal', '')}\n"
            f"实际缺口：{失败.get('gap', '')}\n"
            f"失败证据：{'；'.join(失败.get('evidence', []))}\n"
            f"根因：{诊断.get('root_cause', '')}\n"
            f"本轮原则：{诊断.get('principle', '')}\n"
            f"下一轮具体修正：{失败.get('correction') or 诊断.get('correction', '')}\n"
            f"这是第 {状态.get('attempt', 1)} 轮，最多 {状态.get('max_attempts', 默认最大轮次)} 轮。"
            "先按上面的修正动作改，再重新真实验证。")
