from __future__ import annotations

from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

from .fortune_card import FortuneCardGenerator


class IdolFortunePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.generator = FortuneCardGenerator(Path(__file__).parent / "cache")

    @filter.command("抽签")
    async def draw_fortune(self, event: AstrMessageEvent):
        """发送 /抽签，返回当天固定的地下偶像运势图。"""
        user_id = str(event.get_sender_id())
        try:
            image_path = self.generator.get_or_create(user_id)
        except Exception as exc:  # pragma: no cover - runtime guard for bot stability.
            logger.exception("生成抽签图片失败: %s", exc)
            yield event.plain_result("抽签图片生成失败了，请稍后再试。")
            return

        yield event.image_result(str(image_path))
        event.stop_event()

    async def terminate(self):
        """插件卸载/停用时调用。"""
