"""scripts/ch06_check_sandbox.py —— 第 6 章：沙箱连通自检（不涉及 agent）

运行（项目根目录，先 uv sync --extra sandbox 并在 .env 配好 DAYTONA_API_KEY）：
    uv run python -m scripts.ch06_check_sandbox

作用：开一个沙箱、在里面跑一条命令、再关掉。看到 Python 版本号即说明沙箱可用。
"""
from dotenv import load_dotenv

load_dotenv()  # 让 Daytona() 能从 .env 读到 DAYTONA_API_KEY / DAYTONA_TARGET


def main():
    from daytona import Daytona

    client = Daytona()          # 自动读 DAYTONA_API_KEY / DAYTONA_TARGET
    sandbox = client.create()   # 开一个沙箱
    try:
        # 在沙箱里跑一条命令，验证它真的能执行代码
        result = sandbox.process.code_run('import sys; print("sandbox python:", sys.version)')
        print("✅ 沙箱连通，执行结果：")
        print(result.result if hasattr(result, "result") else result)
    finally:
        sandbox.stop()          # 关键：用完一定关，省额度
        print("✅ 沙箱已关闭")


if __name__ == "__main__":
    main()