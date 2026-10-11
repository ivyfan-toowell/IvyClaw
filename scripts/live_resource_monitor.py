"""采集本次真实联调容器的内存峰值与 OOM 事件，不读取凭据或任务内容。"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def docker(*args: str) -> str:
    """执行只读 Docker 查询，失败保留错误而不停止采样。"""
    result = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=20)
    return result.stdout.strip() if result.returncode == 0 else ""


def monitor(seconds: int, output: Path) -> None:
    """监测 IvyClaw 服务和新沙箱；保留容器销毁前的 cgroup 峰值。"""
    started = datetime.now(timezone.utc).isoformat()
    report: dict[str, Any] = {"startedAt": started, "containers": {}, "oomEvents": [], "samples": 0}
    deadline = time.monotonic() + seconds
    output.parent.mkdir(parents=True, exist_ok=True)
    while time.monotonic() < deadline:
        names = docker("ps", "--format", "{{.Names}}").splitlines()
        for name in names:
            if not name.startswith(("ivyclaw-", "ivc-sbx-", "ivc-ro-")):
                continue
            raw = docker("inspect", name, "--format", '{{json .State}}')
            if not raw:
                continue
            entry = report["containers"].setdefault(name, {"maxMemoryPeakBytes": 0, "maxOomKills": 0})
            entry["lastState"] = json.loads(raw)
            memory = docker("exec", name, "sh", "-c", "cat /sys/fs/cgroup/memory.peak; cat /sys/fs/cgroup/memory.events")
            lines = memory.splitlines()
            if lines and lines[0].isdigit():
                entry["maxMemoryPeakBytes"] = max(entry["maxMemoryPeakBytes"], int(lines[0]))
                for line in lines[1:]:
                    key, _, value = line.partition(" ")
                    if key == "oom_kill" and value.isdigit():
                        entry["maxOomKills"] = max(entry["maxOomKills"], int(value))
            entry["lastSeenAt"] = datetime.now(timezone.utc).isoformat()
        until = datetime.now(timezone.utc).isoformat()
        events = docker("events", "--since", started, "--until", until, "--filter", "event=oom", "--format", "{{json .}}")
        # Docker 事件缓冲会轮转；已观察到的 OOM 不能被后续空查询覆盖。
        known = {(event.get("id"), event.get("timeNano")) for event in report["oomEvents"]}
        for line in events.splitlines():
            if not line:
                continue
            event = json.loads(line)
            key = (event.get("id"), event.get("timeNano"))
            if key not in known:
                report["oomEvents"].append(event)
                known.add(key)
        report["samples"] += 1
        report["updatedAt"] = until
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if report["samples"] % 6 == 0:
            print(f"samples={report['samples']} containers={len(report['containers'])} oom_events={len(report['oomEvents'])}", flush=True)
        time.sleep(5)
    print(str(output.resolve()), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=900)
    parser.add_argument("--output", type=Path, default=Path("logs/live_resources.json"))
    args = parser.parse_args()
    monitor(args.seconds, args.output)
