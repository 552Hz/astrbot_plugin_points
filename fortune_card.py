from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python < 3.9 fallback.
    ZoneInfo = None


FORTUNES = ("大吉", "吉", "中", "凶", "大凶")
ACTIVITIES = ("吃ota饭", "反切", "关门", "看活", "规划远征", "睡觉", "喝酒", "版聊")
CACHE_VERSION = "yahei1"
PLUGIN_DIR = Path(__file__).resolve().parent
BACKGROUND_IMAGE = PLUGIN_DIR / "pcie_background.png"

FONT_CANDIDATES = (
    "msyh.ttc",
    "msyhbd.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/msyh.ttf",
    "C:/Windows/Fonts/msyhbd.ttf",
    "simhei.ttf",
    "simsun.ttc",
    "Deng.ttf",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
    "C:/Windows/Fonts/Deng.ttf",
    "C:/Windows/Fonts/Dengb.ttf",
    "C:/Windows/Fonts/msjh.ttc",
    "C:/Windows/Fonts/msjhbd.ttc",
    "NotoSansSC-Regular.otf",
    "NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
)


@dataclass(frozen=True)
class FortuneResult:
    date_key: str
    user_id: str
    fortune: str
    score: int
    good: tuple[str, ...]
    bad: tuple[str, ...]


def shanghai_today_key() -> str:
    tz = ZoneInfo("Asia/Shanghai") if ZoneInfo else timezone(timedelta(hours=8))
    return datetime.now(tz).strftime("%Y-%m-%d")


def _seed_for(user_id: str, date_key: str) -> int:
    payload = f"{date_key}:{user_id}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def build_fortune(user_id: str, date_key: str | None = None) -> FortuneResult:
    date_key = date_key or shanghai_today_key()
    rng = random.Random(_seed_for(user_id, date_key))

    fortune = rng.choice(FORTUNES)
    base_scores = {"大吉": 96, "吉": 82, "中": 62, "凶": 36, "大凶": 12}
    score = max(1, min(100, base_scores[fortune] + rng.randint(-8, 8)))

    selected = rng.sample(ACTIVITIES, 4)
    good_count = rng.randint(1, 3)
    good = tuple(selected[:good_count])
    bad = tuple(selected[good_count:])

    return FortuneResult(
        date_key=date_key,
        user_id=user_id,
        fortune=fortune,
        score=score,
        good=good,
        bad=bad,
    )


class FortuneCardGenerator:
    def __init__(self, output_dir: Path | str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def get_or_create(self, user_id: str, date_key: str | None = None) -> Path:
        result = build_fortune(user_id, date_key)
        filename = f"{result.date_key}_{_safe_filename(result.user_id)}_{CACHE_VERSION}.png"
        path = self.output_dir / filename
        if not path.exists():
            self.render(result, path)
            self.cleanup(keep_date=result.date_key)
        return path

    def cleanup(self, keep_date: str) -> None:
        for path in self.output_dir.glob("*.png"):
            if not path.name.startswith(f"{keep_date}_") and path.name != "example.png":
                try:
                    path.unlink()
                except OSError:
                    pass

    def render_background(self, path: Path | str, seed_key: str = "pcie-background") -> Path:
        seed = int.from_bytes(hashlib.sha256(seed_key.encode("utf-8")).digest()[:8], "big")
        img = _make_background(540, 960, seed)
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        img.convert("RGB").save(out, "PNG", optimize=True)
        return out

    def render(self, result: FortuneResult, path: Path | str) -> Path:
        img = _make_background(540, 960, _seed_for(result.user_id, result.date_key))
        draw = ImageDraw.Draw(img)

        fonts = _FontSet()
        _draw_main_panel(draw)
        _draw_header(draw, fonts, result)
        _draw_fortune(draw, fonts, result)
        _draw_score_ring(img, draw, fonts, result)
        _draw_good_bad(draw, fonts, result)

        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        img.convert("RGB").save(out, "PNG", optimize=True)
        return out


def _safe_filename(value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]
    return digest


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    selected = _select_font_source()
    if not selected:
        raise RuntimeError(
            "未找到可用中文字体。请确认 NotoSansSC-Regular.otf 与 fortune_card.py 在同一目录。"
        )
    return ImageFont.truetype(selected, size=size)


def get_font_debug_info() -> str:
    selected = _select_font_source()
    if selected:
        return f"selected_font={selected}"
    checked = []
    for candidate in FONT_CANDIDATES:
        font_path = Path(candidate)
        if not font_path.is_absolute():
            font_path = PLUGIN_DIR / font_path
        checked.append(str(font_path))
    return "selected_font=None\nchecked=" + "\n".join(checked)


def _select_font_source() -> str | None:
    for candidate in FONT_CANDIDATES:
        font_path = Path(candidate)
        if not font_path.is_absolute():
            font_path = PLUGIN_DIR / font_path
        if font_path.exists():
            try:
                font = ImageFont.truetype(str(font_path), size=32)
                _ = font.getbbox("今日运势大吉宜忌")
                return str(font_path)
            except OSError:
                continue
    return None


class _FontSet:
    def __init__(self) -> None:
        self.tiny = _font(18)
        self.small = _font(22)
        self.body = _font(26)
        self.body_bold = _font(30)
        self.medium = _font(34)
        self.large = _font(62)
        self.hero = _font(124)


def _make_background(width: int, height: int, seed: int) -> Image.Image:
    asset = _load_background_asset(width, height)
    if asset is not None:
        return asset

    rng = random.Random(seed)
    img = Image.new("RGBA", (width, height), (11, 12, 24, 255))
    pixels = img.load()
    for y in range(height):
        ratio = y / (height - 1)
        for x in range(width):
            drift = abs((x / (width - 1)) - 0.5)
            r = int(10 + ratio * 12 + drift * 12)
            g = int(13 + ratio * 10)
            b = int(28 + ratio * 25 + drift * 18)
            pixels[x, y] = (r, g, b, 255)

    d = ImageDraw.Draw(img)
    for x in range(36, width, 36):
        d.line((x, 0, x, height), fill=(45, 52, 88, 42), width=1)
    for y in range(36, height, 36):
        d.line((0, y, width, y), fill=(45, 52, 88, 35), width=1)

    trace_colors = ((63, 236, 226, 105), (147, 117, 255, 75), (213, 177, 96, 72))
    for _ in range(24):
        x = rng.randrange(36, width - 36, 18)
        y = rng.randrange(48, height - 168, 18)
        segments = rng.randint(2, 5)
        color = rng.choice(trace_colors)
        points = [(x, y)]
        for _ in range(segments):
            if rng.random() < 0.55:
                x = max(24, min(width - 24, x + rng.choice((-72, -54, -36, 36, 54, 72))))
            else:
                y = max(24, min(height - 168, y + rng.choice((-72, -54, -36, 36, 54, 72))))
            points.append((x, y))
        d.line(points, fill=color, width=2)
        for px, py in points:
            d.ellipse((px - 3, py - 3, px + 3, py + 3), fill=color)

    for _ in range(5):
        x = rng.randrange(66, width - 126, 18)
        y = rng.randrange(110, height - 260, 18)
        w = rng.choice((54, 72, 90))
        h = rng.choice((36, 54, 72))
        d.rounded_rectangle((x, y, x + w, y + h), radius=5, outline=(78, 244, 232, 70), width=1)
        for pin_y in range(y + 9, y + h, 12):
            d.line((x - 9, pin_y, x, pin_y), fill=(78, 244, 232, 60), width=1)
            d.line((x + w, pin_y, x + w + 9, pin_y), fill=(78, 244, 232, 60), width=1)

    # PCIe-like gold fingers.
    gold_top = height - 104
    d.rounded_rectangle((58, gold_top - 20, width - 58, gold_top + 70), radius=12, fill=(20, 20, 34, 230), outline=(81, 88, 128, 150), width=1)
    for i in range(18):
        x1 = 74 + i * 22
        d.rounded_rectangle((x1, gold_top, x1 + 14, gold_top + 54), radius=3, fill=(209, 167, 74, 230))
        d.line((x1 + 2, gold_top + 5, x1 + 12, gold_top + 5), fill=(255, 229, 142, 180), width=1)

    return img


def _load_background_asset(width: int, height: int) -> Image.Image | None:
    if not BACKGROUND_IMAGE.exists():
        return None

    with Image.open(BACKGROUND_IMAGE) as source:
        img = source.convert("RGBA")

    scale = max(width / img.width, height / img.height)
    resized = img.resize((round(img.width * scale), round(img.height * scale)), Image.Resampling.LANCZOS)
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def _draw_main_panel(draw: ImageDraw.ImageDraw) -> None:
    draw.rounded_rectangle((54, 82, 486, 760), radius=24, fill=(17, 18, 35, 242), outline=(71, 241, 230, 110), width=2)
    draw.rounded_rectangle((76, 104, 464, 738), radius=12, outline=(85, 93, 142, 116), width=1)
    draw.line((96, 198, 444, 198), fill=(55, 230, 220, 105), width=1)
    draw.line((96, 498, 444, 498), fill=(85, 93, 142, 120), width=1)
    for x in range(112, 444, 22):
        draw.line((x, 104, x + 10, 104), fill=(209, 167, 74, 145), width=2)


def _draw_header(draw: ImageDraw.ImageDraw, fonts: _FontSet, result: FortuneResult) -> None:
    _text(draw, "今日运势", (96, 136), fonts.body_bold, fill=(237, 240, 255, 255))
    _text(draw, result.date_key, (342, 140), fonts.tiny, fill=(151, 159, 205, 255))
    draw.rounded_rectangle((96, 178, 192, 181), radius=2, fill=(209, 167, 74, 210))


def _draw_fortune(draw: ImageDraw.ImageDraw, fonts: _FontSet, result: FortuneResult) -> None:
    hero_font = fonts.hero if len(result.fortune) == 1 else _font(102)
    shadow_color = (68, 241, 231, 80)
    _center(draw, result.fortune, 274, 306, hero_font, fill=shadow_color)
    _center(draw, result.fortune, 270, 300, hero_font, fill=(238, 241, 255, 255))


def _draw_score_ring(img: Image.Image, draw: ImageDraw.ImageDraw, fonts: _FontSet, result: FortuneResult) -> None:
    center = (270, 436)
    draw.ellipse((224, 390, 316, 482), outline=(54, 60, 96, 255), width=8)
    end = -90 + 360 * result.score / 100
    draw.arc((224, 390, 316, 482), -90, end, fill=(67, 242, 231, 255), width=8)
    _center(draw, str(result.score), center[0], center[1] - 5, fonts.medium, fill=(238, 241, 255, 255))
    _center(draw, "人品值", center[0], center[1] + 28, fonts.tiny, fill=(151, 159, 205, 255))


def _draw_good_bad(draw: ImageDraw.ImageDraw, fonts: _FontSet, result: FortuneResult) -> None:
    _draw_column(draw, fonts, (96, 538, 252, 710), "宜", result.good, (67, 242, 231, 255), (67, 242, 231, 255))
    _draw_column(draw, fonts, (288, 538, 444, 710), "忌", result.bad, (246, 76, 137, 255), (246, 76, 137, 255))


def _draw_column(
    draw: ImageDraw.ImageDraw,
    fonts: _FontSet,
    box: tuple[int, int, int, int],
    title: str,
    items: Iterable[str],
    fill: tuple[int, int, int, int],
    accent: tuple[int, int, int, int],
) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=12, fill=(25, 27, 47, 255), outline=(78, 86, 130, 200), width=1)
    draw.line((x1 + 16, y1 + 42, x2 - 16, y1 + 42), fill=accent, width=2)
    _text(draw, title, (x1 + 16, y1 + 10), fonts.body_bold, fill=fill)
    y = y1 + 58
    for item in items:
        draw.ellipse((x1 + 18, y + 8, x1 + 25, y + 15), fill=accent)
        _text(draw, item, (x1 + 36, y), fonts.small, fill=(238, 241, 255, 255))
        y += 34


def _center(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int, int],
    tracking: int = 0,
) -> None:
    if tracking and len(text) > 1:
        widths = [draw.textbbox((0, 0), char, font=font)[2] for char in text]
        total = sum(widths) + tracking * (len(text) - 1)
        cursor = x - total / 2
        for char, width in zip(text, widths):
            bbox = draw.textbbox((0, 0), char, font=font)
            draw.text((cursor, y - (bbox[3] - bbox[1]) / 2 - bbox[1]), char, font=font, fill=fill)
            cursor += width + tracking
        return

    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    draw.text((x - w / 2 - bbox[0], y - h / 2 - bbox[1]), text, font=font, fill=fill)


def _text(draw: ImageDraw.ImageDraw, text: str, xy: tuple[int, int], font: ImageFont.ImageFont, fill: tuple[int, int, int, int]) -> None:
    draw.text(xy, text, font=font, fill=fill)
