"""scripts/gunicorn_conf.py —— Gunicorn 配置（Prometheus 多进程清理）"""
def child_exit(server, worker):
    # worker 退出时清理它的 Prometheus 指标文件，避免死 worker 指标残留
    from prometheus_client import multiprocess
    multiprocess.mark_process_dead(worker.pid)