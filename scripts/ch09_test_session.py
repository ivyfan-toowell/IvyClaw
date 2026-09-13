"""
scripts/ch09_test_session.py —— 第 9 章：会话归属 thread_id_for 单元测试
纯函数测试，不依赖服务/网络/飞书。直接运行：

uv run python -m scripts.ch09_test_session
"""

from channels.base import InboundMessage
from channels.session import thread_id_for


def _msg(channel, conv, user="u1"):
    return InboundMessage(channel=channel, user_id=user, text="x", conversation_id=conv)


def test_same_conversation_stable():
    """同 (渠道,会话) → 同 thread_id（这样才能续聊）。"""
    a = thread_id_for(_msg("feishu", "chatA"))
    b = thread_id_for(_msg("feishu", "chatA"))
    assert a == b, "同会话必须得到相同 thread_id（否则续不上）"


def test_different_conversation_isolated():
    """不同会话 → 不同 thread_id（否则不同群会串）。"""
    a = thread_id_for(_msg("feishu", "chatA"))
    b = thread_id_for(_msg("feishu", "chatB"))
    assert a != b, "不同会话必须隔离"


def test_different_channel_isolated():
    """同会话 id 但不同渠道 → 不同 thread_id（飞书的 chatA 和 web 的 chatA 不是一回事）。"""
    a = thread_id_for(_msg("feishu", "X"))
    b = thread_id_for(_msg("web", "X"))
    assert a != b, "不同渠道必须隔离"


def test_tenant_isolated():
    """同渠道同会话但不同租户 → 不同 thread_id（多租户硬隔离）。"""
    m = _msg("feishu", "shared")
    a = thread_id_for(m, tenant_id="tenant-1")
    b = thread_id_for(m, tenant_id="tenant-2")
    assert a != b, "不同租户必须隔离"


def test_format():
    """thread_id 是定长十六进制（适合做 checkpointer 的 key）。"""
    t = thread_id_for(_msg("cli", "s1"))
    assert len(t) == 32 and all(c in "0123456789abcdef" for c in t)


def main():
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  ✅ {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {t.__name__}: {e}")
    print(f"\n会话归属测试：{passed}/{len(tests)} 通过")


if __name__ == "__main__":
    main()