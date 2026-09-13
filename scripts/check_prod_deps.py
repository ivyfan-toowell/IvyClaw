import ast
import importlib.metadata
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 生产代码目录：不扫 tests / eval / loadtest 等
PROD_DIRS = {
    "agent", "api", "app", "channels", "concurrency", "gateway",
    "infra", "middleware", "obs", "profiles", "resilience",
    "sandbox", "skills", "subagents", "tasks", "tools", "web",
}

# 项目自己的模块，不能当第三方依赖
local_modules = {
    p.name for p in ROOT.iterdir() if p.is_dir()
}
local_modules.add("main")

imports = set()

for dirname in PROD_DIRS:
    base = ROOT / dirname
    if not base.exists():
        continue

    for py in base.rglob("*.py"):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except Exception:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    imports.add(n.name.split(".")[0])

            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])

# requirements.txt 中真正包含的发行包
req_text = (ROOT / "requirements.txt").read_text(
    encoding="utf-8", errors="ignore"
)

required_packages = set()

for line in req_text.splitlines():
    line = line.strip()
    if not line or line.startswith("#") or line.startswith("--"):
        continue

    m = re.match(r"([A-Za-z0-9_.-]+)", line)
    if m:
        required_packages.add(m.group(1).lower().replace("_", "-"))

mapping = importlib.metadata.packages_distributions()

print("=== 生产代码依赖审计 ===")

missing = []

for mod in sorted(imports - sys.stdlib_module_names - local_modules):
    distributions = mapping.get(mod)

    if not distributions:
        print(f"{mod:30} -> ⚠️ 无法确定对应安装包")
        continue

    present = any(
        d.lower().replace("_", "-") in required_packages
        for d in distributions
    )

    names = ", ".join(distributions)

    if present:
        print(f"{mod:30} -> ✅ {names}")
    else:
        print(f"{mod:30} -> ❌ requirements 缺少：{names}")
        missing.extend(distributions)

print("\n=== 真正需要补的依赖 ===")

if missing:
    for name in sorted(set(missing)):
        print(name)
else:
    print("没有发现缺失依赖")