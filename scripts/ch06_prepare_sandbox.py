from sandbox.manager import get_or_create_sandbox_backend


def main():
    thread_id = "ch06-devmate-team"

    backend, sandbox, client, workdir = get_or_create_sandbox_backend(
        thread_id
    )

    print(f"沙箱工作目录：{workdir}")

    result = sandbox.process.exec(
        f"cd {workdir} && uv sync"
    )

    print(result.result)


if __name__ == "__main__":
    main()