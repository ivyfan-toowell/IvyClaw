"""scripts/ch09_feishu_send.py —— 验证飞书「发消息」

依赖：uv add lark-oapi；.env 配好飞书凭证；
chat_id 用上一步"验收收消息"时终端打印出来的真实值（不是占位符）。
运行：uv run python -m scripts.ch09_feishu_send <真实chat_id>
然后去飞书对应会话看是否收到「DevMate 自检消息」。
"""
import asyncio
import sys

from channels.feishu import FeishuChannel


async def main():
    if len(sys.argv) < 2:
        print("用法：uv run python -m scripts.ch09_feishu_send <chat_id>")
        print("（chat_id 从『验收收消息』那步的接收端日志里复制，形如 oc_xxxxx）")
        return
    chat_id = sys.argv[1]
    fs = FeishuChannel()
    # 只验证「发」这一半：调用 send，不报错 + 群里能看到 = 发通了
    await fs.send(chat_id, "（DevMate自检消息）：你若在飞书看到这条，说明『发消息』通了 ✅，你创建了我，你简直太棒啦！！！")
    print(f"已尝试向 {chat_id} 发送 —— 请去飞书对应会话确认是否收到。")


if __name__ == "__main__":
    asyncio.run(main())



