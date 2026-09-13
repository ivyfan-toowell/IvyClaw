"""scripts/ch11_check_docker_sandbox.py —— 第 11 章：加固容器沙箱自检

需本机 Docker 在跑、已构建 shanyang-sandbox 镜像（见 3.3）。
运行：uv run python -m scripts.ch11_check_docker_sandbox

验五件事：① 能执行代码；② 断网生效；③ 根只读；④ 工作目录可写；⑤ pytest 真能跑通。
注意：DockerSandbox 的 execute/upload_files 是同步方法,直接调用不加 await;
      容器生命周期函数(create/seed/destroy)是异步的,要 await。
"""
import asyncio

from sandbox.docker_manager import create_one_sandbox, seed_project, destroy_sandbox


async def main():
    sb = await create_one_sandbox()
    try:
        # ① 能执行（execute 是同步方法）
        r = sb.execute("python -c 'import sys; print(\"py\", sys.version.split()[0])'")
        print("① 执行：", r.output.strip(), "exit=", r.exit_code)

        # ② 断网（--network none）：访问外网应失败
        r = sb.execute(
            "python -c \"import urllib.request as u; u.urlopen('http://example.com', timeout=3)\" 2>&1 | tail -1"
        )
        print("② 断网（应报网络错误）：", r.output.strip())

        # ③ 只读根（--read-only）：写系统目录应被拒
        r = sb.execute("echo hack > /etc/hacked 2>&1; echo exit=$?")
        print("③ 写 /etc（应 Read-only file system / 非 0）：", r.output.strip())

        # ④ 工作目录可写
        r = sb.execute("echo ok > /home/agent/t.txt && cat /home/agent/t.txt")
        print("④ 工作目录可写（应 ok）：", r.output.strip())

        # ⑤ 在加固约束下 pytest 真能跑通（关键：验证 read-only + tmpfs 不阻塞测试）
        upload_result = sb.upload_files([(
            "/home/agent/test_demo.py",
            b"def test_add():\n    assert 1 + 1 == 2\n",
        )])
        print("上传结果：", upload_result)
        r = sb.execute(
            "ls -l /home/agent && "
            "cat /home/agent/test_demo.py"
        )
        print("上传后检查：\n", r.output)

        r = sb.execute("cd /home/agent && python -m pytest test_demo.py -q 2>&1 | tail -3")
        print("⑤ pytest（应有 1 passed）：\n", r.output.strip())

    # finally:
    #     print("暂不销毁容器，留作手动测试")
    finally:
        await destroy_sandbox(sb)   # 用完即弃
        print("✅ 容器已销毁")


if __name__ == "__main__":
    asyncio.run(main())