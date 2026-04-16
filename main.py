"""
积分管理系统插件
功能：
1. 用户注册账户
2. 用户查询自己的积分（生成卡片图片）
3. 管理员增减成员的积分
4. 指令查询群积分排行榜
5. 用户之间转账积分
"""

import json
import re
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import AstrBotConfig, logger
from astrbot.api.message_components import At


class AccountData:
    """用户账户数据管理类"""

    def __init__(self, data_file: Path):
        self.data_file = data_file
        self.accounts: dict = {}  # {qq号: {"username": "xxx", "registered": true}}
        self._load_data()

    def _load_data(self):
        """加载账户数据"""
        if self.data_file.exists():
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    self.accounts = json.load(f)
                logger.info(f"账户数据已加载，共 {len(self.accounts)} 条记录")
            except Exception as e:
                logger.error(f"加载账户数据失败: {e}")
                self.accounts = {}
        else:
            logger.info("账户数据文件不存在，将创建新文件")
            self._save_data()

    def _save_data(self):
        """保存账户数据"""
        try:
            self.data_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self.accounts, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存账户数据失败: {e}")

    def is_registered(self, qq_id: str) -> bool:
        """检查用户是否已注册"""
        return qq_id in self.accounts

    def register(self, qq_id: str, username: str) -> bool:
        """注册新账户，用户名不能重复"""
        # 检查用户名是否已被占用
        for acc in self.accounts.values():
            if acc.get("username") == username:
                return False
        self.accounts[qq_id] = {
            "username": username,
            "registered": True
        }
        self._save_data()
        return True

    def get_username(self, qq_id: str) -> Optional[str]:
        """获取用户名"""
        if qq_id in self.accounts:
            return self.accounts[qq_id].get("username")
        return None

    def update_username(self, qq_id: str, new_username: str) -> bool:
        """修改用户名，不能与已有用户名重复"""
        if qq_id not in self.accounts:
            return False
        # 检查新用户名是否已被占用
        for qid, acc in self.accounts.items():
            if qid != qq_id and acc.get("username") == new_username:
                return False
        self.accounts[qq_id]["username"] = new_username
        self._save_data()
        return True


class PointsData:
    """积分数据管理类"""

    def __init__(self, data_file: Path):
        self.data_file = data_file
        self.points_data: dict = {}
        self._load_data()

    def _load_data(self):
        """加载积分数据"""
        if self.data_file.exists():
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    self.points_data = json.load(f)
                logger.info(f"积分数据已加载，共 {len(self.points_data)} 条记录")
            except Exception as e:
                logger.error(f"加载积分数据失败: {e}")
                self.points_data = {}
        else:
            logger.info("积分数据文件不存在，将创建新文件")
            self._save_data()

    def _save_data(self):
        """保存积分数据"""
        try:
            self.data_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self.points_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存积分数据失败: {e}")

    def get_points(self, qq_id: str, group_id: str) -> int:
        """获取用户积分"""
        key = f"{group_id}_{qq_id}"
        return self.points_data.get(key, 0)

    def set_points(self, qq_id: str, group_id: str, points: int) -> int:
        """设置用户积分"""
        key = f"{group_id}_{qq_id}"
        self.points_data[key] = points
        self._save_data()
        return points

    def add_points(self, qq_id: str, group_id: str, amount: int) -> tuple[int, bool]:
        """
        添加积分，返回 (新积分, 是否成功)
        amount 为负数表示扣除积分
        """
        key = f"{group_id}_{qq_id}"
        current = self.points_data.get(key, 0)
        new_points = current + amount

        # 检查最低积分限制
        if new_points < 0:
            return current, False

        self.points_data[key] = new_points
        self._save_data()
        return new_points, True

    def get_group_ranking(self, group_id: str, limit: int = 10) -> list[tuple[str, int]]:
        """
        获取群积分排行榜
        返回 [(qq_id, points), ...]
        """
        prefix = f"{group_id}_"
        group_keys = [k for k in self.points_data.keys() if k.startswith(prefix)]

        rankings = []
        for key in group_keys:
            qq_id = key[len(prefix):]
            points = self.points_data[key]
            rankings.append((qq_id, points))

        # 按积分降序排序
        rankings.sort(key=lambda x: x[1], reverse=True)

        # 返回前N名
        return [(uid, pts) for uid, pts in rankings[:limit]]

    def get_user_info(self, qq_id: str, group_id: str) -> dict:
        """获取用户在群中的信息"""
        key = f"{group_id}_{qq_id}"
        points = self.points_data.get(key, 0)

        # 计算排名（使用已排序的列表）
        rankings = self.get_group_ranking(group_id, limit=999999)
        rank = 1
        for i, uid in enumerate([uid for uid, _ in rankings]):
            if uid == qq_id:
                rank = i + 1
                break

        return {
            "points": points,
            "rank": rank,
            "total_users": len(rankings)
        }


class PointsPlugin(Star):
    """积分管理插件主类"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.name = "积分管理系统"

        # 初始化数据存储路径
        from astrbot.core.utils.astrbot_path import get_astrbot_data_path
        data_dir = Path(get_astrbot_data_path()) / "plugin_data" / "astrbot_plugin_points"
        data_dir.mkdir(parents=True, exist_ok=True)

        # 账户数据文件
        self.accounts_file = data_dir / "accounts.json"
        self.account_data = AccountData(self.accounts_file)

        # 积分数据文件
        self.points_file = data_dir / "points.json"
        self.points_data = PointsData(self.points_file)

        # 卡片存储目录
        self.cards_dir = data_dir / "cards"
        self.cards_dir.mkdir(parents=True, exist_ok=True)

        logger.info("积分管理系统插件已加载")

    def _is_user_registered(self, qq_id: str) -> bool:
        """检查用户是否已注册"""
        return self.account_data.is_registered(qq_id)

    def _generate_points_card(self, username: str, qq_id: str, points: int, rank: int, total_users: int) -> str:
        """生成积分卡片图片"""
        # 图片尺寸
        width, height = 400, 300

        # 创建图片
        img = Image.new('RGB', (width, height), color=(45, 55, 72))
        draw = ImageDraw.Draw(img)

        # 尝试加载字体
        try:
            font_title = ImageFont.truetype("msyh.ttc", 32)
            font_large = ImageFont.truetype("msyh.ttc", 48)
            font_normal = ImageFont.truetype("msyh.ttc", 20)
            font_small = ImageFont.truetype("msyh.ttc", 16)
        except Exception:
            try:
                font_title = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 32)
                font_large = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 48)
                font_normal = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 20)
                font_small = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 16)
            except Exception:
                font_title = ImageFont.load_default()
                font_large = ImageFont.load_default()
                font_normal = ImageFont.load_default()
                font_small = ImageFont.load_default()

        # 绘制渐变背景效果
        for i in range(height):
            draw.rectangle([(0, i), (width, i + 1)], fill=(55, 65, 81))

        # 绘制顶部金色装饰条
        draw.rectangle([(0, 0), (width, 8)], fill=(251, 191, 36))

        # 绘制标题
        title = "积分查询"
        title_bbox = draw.textbbox((0, 0), title, font=font_title)
        title_width = title_bbox[2] - title_bbox[0]
        draw.text(((width - title_width) // 2, 25), title, font=font_title, fill=(255, 255, 255))

        # 绘制用户名
        display_name = username if username else f"用户{qq_id}"
        if len(display_name) > 15:
            display_name = display_name[:12] + "..."
        name_bbox = draw.textbbox((0, 0), display_name, font=font_normal)
        name_width = name_bbox[2] - name_bbox[0]
        draw.text(((width - name_width) // 2, 75), display_name, font=font_normal, fill=(156, 163, 175))

        # 绘制账号
        account_text = f"账号: {qq_id}"
        account_bbox = draw.textbbox((0, 0), account_text, font=font_small)
        account_width = account_bbox[2] - account_bbox[0]
        draw.text(((width - account_width) // 2, 100), account_text, font=font_small, fill=(107, 114, 128))

        # 绘制分隔线
        draw.line([(50, 130), (width - 50, 130)], fill=(75, 85, 99), width=2)

        # 绘制积分标签
        points_label = "我的积分"
        label_bbox = draw.textbbox((0, 0), points_label, font=font_normal)
        label_width = label_bbox[2] - label_bbox[0]
        draw.text(((width - label_width) // 2, 145), points_label, font=font_normal, fill=(156, 163, 175))

        # 绘制积分数字
        points_str = f"{points:,}"
        points_bbox = draw.textbbox((0, 0), points_str, font=font_large)
        points_width = points_bbox[2] - points_bbox[0]
        draw.text(((width - points_width) // 2, 170), points_str, font=font_large, fill=(251, 191, 36))

        # 绘制排名信息
        rank_text = f"群排名: 第 {rank} 名 / 共 {total_users} 人"
        rank_bbox = draw.textbbox((0, 0), rank_text, font=font_small)
        rank_width = rank_bbox[2] - rank_bbox[0]
        draw.text(((width - rank_width) // 2, 250), rank_text, font=font_small, fill=(107, 114, 128))

        # 保存图片
        card_path = self.cards_dir / f"card_{qq_id}.png"
        img.save(card_path, 'PNG')
        return str(card_path)

    @filter.command("注册")
    async def register_account(self, event: AstrMessageEvent):
        """注册账户 - /注册 用户名"""
        qq_id = event.get_sender_id()

        # 检查是否已注册
        if self._is_user_registered(qq_id):
            username = self.account_data.get_username(qq_id)
            yield event.plain_result(f"您已经注册过了，您的用户名：{username}")
            return

        # 提取用户名
        message = event.message_str
        # 去掉命令部分，获取用户名
        match = re.match(r'^注册\s+(.+)$', message)
        if not match:
            yield event.plain_result("请输入用户名，格式：/注册 你的用户名")
            return

        username = match.group(1).strip()

        # 检查用户名长度
        if len(username) < 2 or len(username) > 20:
            yield event.plain_result("用户名长度需在2-20个字符之间")
            return

        # 注册账户
        if self.account_data.register(qq_id, username):
            # 初始化积分
            initial_points = self.config.get("initial_points", 100)
            group_id = event.message_obj.group_id or "private"
            self.points_data.set_points(qq_id, group_id, initial_points)

            yield event.plain_result(
                f"注册成功！\n"
                f"用户名：{username}\n"
                f"账号：{qq_id}\n"
                f"初始积分：{initial_points}\n\n"
                f"欢迎使用积分管理系统！"
            )
        else:
            yield event.plain_result("注册失败，用户名已被占用，请换一个用户名试试")

    @filter.command("积分", alias={"points", "score"})
    async def query_my_points(self, event: AstrMessageEvent):
        """查询自己的积分 - 使用 /积分 或 /points"""
        qq_id = event.get_sender_id()
        group_id = event.message_obj.group_id or "private"

        # 检查是否已注册
        if not self._is_user_registered(qq_id):
            yield event.plain_result("您还未注册，请先使用 /注册 你的用户名 来注册账户")
            return

        username = self.account_data.get_username(qq_id)
        info = self.points_data.get_user_info(qq_id, group_id)

        # 生成积分卡片图片
        try:
            card_path = self._generate_points_card(
                username=username,
                qq_id=qq_id,
                points=info['points'],
                rank=info['rank'],
                total_users=info['total_users']
            )
            yield event.image_result(card_path)
        except Exception as e:
            logger.error(f"生成积分卡片失败: {e}")
            result = (
                f"@{username} 的积分信息：\n"
                f"账号：{qq_id}\n"
                f"当前积分：{info['points']}\n"
                f"群排名：第 {info['rank']} 名（共 {info['total_users']} 人）"
            )
            yield event.plain_result(result)

    @filter.command("积分帮助", alias={"points_help"})
    async def points_help(self, event: AstrMessageEvent):
        """积分系统帮助信息"""
        help_text = (
            "【积分管理系统】使用说明：\n\n"
            "📝 首次使用：\n"
            "/注册 用户名 - 注册账户（用户名2-20字符）\n\n"
            "📌 用户指令：\n"
            "/积分 或 /points - 查询自己的积分\n"
            "/排行榜 或 /rank - 查看群积分排行榜\n"
            "/转账 @用户 数值 - 向指定用户转账积分\n"
            "/修改用户名 新名字 - 修改您的用户名\n"
            "/积分帮助 - 查看此帮助信息\n\n"
            "🔧 管理员指令：\n"
            "/加积分 @用户 数值 - 给指定用户增加积分\n"
            "/扣积分 @用户 数值 - 扣除指定用户的积分\n"
            "/设置积分 @用户 数值 - 设置指定用户的积分为指定值\n"
            "/重置积分 @用户 - 重置指定用户的积分为初始值"
        )
        yield event.plain_result(help_text)

    @filter.command("修改用户名")
    async def update_username(self, event: AstrMessageEvent):
        """修改用户名"""
        qq_id = event.get_sender_id()

        # 检查是否已注册
        if not self._is_user_registered(qq_id):
            yield event.plain_result("您还未注册，请先使用 /注册 你的用户名 来注册账户")
            return

        message = event.message_str
        match = re.match(r'^修改用户名\s+(.+)$', message)
        if not match:
            yield event.plain_result("请输入新用户名，格式：/修改用户名 新名字")
            return

        new_username = match.group(1).strip()

        # 检查用户名长度
        if len(new_username) < 2 or len(new_username) > 20:
            yield event.plain_result("用户名长度需在2-20个字符之间")
            return

        if self.account_data.update_username(qq_id, new_username):
            yield event.plain_result(f"用户名修改成功！新用户名：{new_username}")
        else:
            yield event.plain_result("用户名修改失败，新用户名已被占用")

    @filter.command("排行榜", alias={"rank", "ranking"})
    async def show_ranking(self, event: AstrMessageEvent):
        """查看群积分排行榜"""
        group_id = event.message_obj.group_id
        if not group_id:
            yield event.plain_result("排行榜功能仅在群聊中可用")
            return

        limit = self.config.get("rank_display_count", 10)
        rankings = self.points_data.get_group_ranking(group_id, limit)

        if not rankings:
            yield event.plain_result("当前群暂无积分数据，快去赚取积分吧！")
            return

        # 构建排行榜消息
        result_lines = ["【群积分排行榜】\n"]

        medal = ["🥇", "🥈", "🥉"]
        for i, (qq_id, points) in enumerate(rankings):
            if i < 3:
                medal_str = medal[i]
            else:
                medal_str = f"{i + 1}."

            # 获取用户名（如果已注册的话）
            username = self.account_data.get_username(qq_id)
            if not username:
                username = f"用户{qq_id}"

            result_lines.append(f"{medal_str} {username}: {points} 积分")

        yield event.plain_result("\n".join(result_lines))

    @filter.command("加积分")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def add_points_to_user(self, event: AstrMessageEvent):
        """管理员给用户增加积分"""
        qq_id = event.get_sender_id()
        group_id = event.message_obj.group_id or "private"

        # 检查管理员是否已注册
        if not self._is_user_registered(qq_id):
            yield event.plain_result("您还未注册，请先使用 /注册 你的用户名 来注册账户")
            return

        amount = self._extract_number_from_message(event.message_str)
        if amount is None or amount <= 0:
            yield event.plain_result("请指定要增加的积分数量，格式：/加积分 @用户 数值")
            return

        # 检查是否超过单次最大限制
        max_points = self.config.get("max_points", 10000)
        if amount > max_points:
            yield event.plain_result(f"单次操作最大积分数为 {max_points}")
            return

        target_qq_id = self._extract_at_user(event)
        if not target_qq_id:
            yield event.plain_result("请 @要增加积分的用户")
            return

        new_points, success = self.points_data.add_points(target_qq_id, group_id, amount)

        if success:
            target_name = self.account_data.get_username(target_qq_id) or f"用户{target_qq_id}"
            yield event.plain_result(f"已为 {target_name} 增加 {amount} 积分，当前积分：{new_points}")
        else:
            yield event.plain_result("操作失败")

    @filter.command("扣积分")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def deduct_points_from_user(self, event: AstrMessageEvent):
        """管理员扣除用户积分"""
        qq_id = event.get_sender_id()

        # 检查管理员是否已注册
        if not self._is_user_registered(qq_id):
            yield event.plain_result("您还未注册，请先使用 /注册 你的用户名 来注册账户")
            return

        amount = self._extract_number_from_message(event.message_str)
        if amount is None or amount <= 0:
            yield event.plain_result("请指定要扣除的积分数量，格式：/扣积分 @用户 数值")
            return

        target_qq_id = self._extract_at_user(event)
        if not target_qq_id:
            yield event.plain_result("请 @要扣除积分的用户")
            return

        group_id = event.message_obj.group_id or "private"
        new_points, success = self.points_data.add_points(target_qq_id, group_id, -amount)

        if success:
            target_name = self.account_data.get_username(target_qq_id) or f"用户{target_qq_id}"
            yield event.plain_result(f"已扣除 {target_name} 的 {amount} 积分，当前积分：{new_points}")
        else:
            current = self.points_data.get_points(target_qq_id, group_id)
            yield event.plain_result(f"扣除失败，用户当前积分为 {current}，不足扣除 {amount} 积分")

    @filter.command("设置积分")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def set_user_points(self, event: AstrMessageEvent):
        """管理员设置用户积分"""
        qq_id = event.get_sender_id()

        # 检查管理员是否已注册
        if not self._is_user_registered(qq_id):
            yield event.plain_result("您还未注册，请先使用 /注册 你的用户名 来注册账户")
            return

        amount = self._extract_number_from_message(event.message_str)
        if amount is None or amount < 0:
            yield event.plain_result("请指定要设置的积分数量（必须为正数），格式：/设置积分 @用户 数值")
            return

        # 检查最低积分限制
        min_points = self.config.get("min_points", 0)
        if amount < min_points:
            yield event.plain_result(f"积分不能低于最低限制 {min_points}")
            return

        target_qq_id = self._extract_at_user(event)
        if not target_qq_id:
            yield event.plain_result("请 @要设置积分的用户")
            return

        group_id = event.message_obj.group_id or "private"
        self.points_data.set_points(target_qq_id, group_id, amount)

        target_name = self.account_data.get_username(target_qq_id) or f"用户{target_qq_id}"
        yield event.plain_result(f"已将 {target_name} 的积分设置为 {amount}")

    @filter.command("重置积分")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def reset_user_points(self, event: AstrMessageEvent):
        """管理员重置用户积分为初始值"""
        qq_id = event.get_sender_id()

        # 检查管理员是否已注册
        if not self._is_user_registered(qq_id):
            yield event.plain_result("您还未注册，请先使用 /注册 你的用户名 来注册账户")
            return

        target_qq_id = self._extract_at_user(event)
        if not target_qq_id:
            yield event.plain_result("请 @要重置积分的用户")
            return

        group_id = event.message_obj.group_id or "private"
        initial_points = self.config.get("initial_points", 100)

        self.points_data.set_points(target_qq_id, group_id, initial_points)

        target_name = self.account_data.get_username(target_qq_id) or f"用户{target_qq_id}"
        yield event.plain_result(f"已将 {target_name} 的积分重置为初始值 {initial_points}")

    @filter.command("转账")
    async def transfer_points(self, event: AstrMessageEvent):
        """用户之间转账积分"""
        sender_id = event.get_sender_id()

        # 检查是否已注册
        if not self._is_user_registered(sender_id):
            yield event.plain_result("您还未注册，请先使用 /注册 你的用户名 来注册账户")
            return

        amount = self._extract_number_from_message(event.message_str)
        if amount is None or amount <= 0:
            yield event.plain_result("请指定要转账的积分数量，格式：/转账 @用户 数值")
            return

        receiver_id = self._extract_at_user(event)
        if not receiver_id:
            yield event.plain_result("请 @要转账的目标用户")
            return

        if sender_id == receiver_id:
            yield event.plain_result("不能给自己转账")
            return

        group_id = event.message_obj.group_id or "private"

        # 检查发送者积分是否足够
        sender_current = self.points_data.get_points(sender_id, group_id)
        if sender_current < amount:
            yield event.plain_result(f"积分不足，当前积分：{sender_current}")
            return

        # 扣除发送者积分
        new_sender_points, success = self.points_data.add_points(sender_id, group_id, -amount)
        if not success:
            yield event.plain_result(f"转账失败，当前积分：{sender_current}")
            return

        # 增加接收者积分
        receiver_new_points = self.points_data.add_points(receiver_id, group_id, amount)[0]

        sender_name = self.account_data.get_username(sender_id) or f"用户{sender_id}"
        receiver_name = self.account_data.get_username(receiver_id) or f"用户{receiver_id}"

        yield event.plain_result(
            f"转账成功！\n"
            f"你向 {receiver_name} 转账了 {amount} 积分\n"
            f"你的当前积分：{new_sender_points}\n"
            f"{receiver_name} 的当前积分：{receiver_new_points}"
        )

    async def terminate(self):
        """插件卸载时保存数据"""
        logger.info("积分管理系统插件已卸载，数据已保存")

    def _extract_at_user(self, event: AstrMessageEvent) -> Optional[str]:
        """从消息中提取被@的用户ID"""
        from astrbot.api.message_components import At

        for segment in event.message_obj.message:
            if isinstance(segment, At):
                if hasattr(segment, 'qq') and segment.qq:
                    return str(segment.qq)
        return None

    def _extract_number_from_message(self, message_str: str) -> Optional[int]:
        """从消息中提取数字"""
        numbers = re.findall(r'-?\d+', message_str)
        if numbers:
            try:
                return int(numbers[-1])
            except ValueError:
                return None
        return None