# 地下偶像抽签 AstrBot 插件

QQ 群里 `@机器人 /抽签` 后，返回一张地下偶像主题的每日运势图。

## 功能

- 每个 QQ 号每天的结果固定，以上海时区零点刷新。
- 运势随机为 `大吉`、`吉`、`中`、`凶`、`大凶`。
- 从 `吃ota饭`、`反切`、`关门`、`看活`、`规划远征`、`睡觉`、`喝酒`、`版聊` 中抽取 4 个，随机分到 `宜` 和 `忌`。
- 返回极简 PCIE 科技风图片，底图由代码生成，不依赖外部图片素材。

## 安装

把本目录放到 AstrBot 的 `data/plugins/` 下，确保插件目录里有：

- `main.py`
- `fortune_card.py`
- `metadata.yaml`
- `requirements.txt`
- `README.md`
- `.gitignore`
- `__init__.py`
- `pcie_background.png`
- `NotoSansSC-Regular.otf`
- `FONT_LICENSE.txt`

AstrBot 会按 `requirements.txt` 安装 `Pillow`。

Windows Server 会优先使用微软雅黑。如果系统自带 `C:/Windows/Fonts/msyh.ttc`，或你把 `msyh.ttc` 放在插件根目录，插件会优先加载它。仓库里保留 `NotoSansSC-Regular.otf` 作为开源中文字体兜底。

更新代码后请重启 AstrBot。新版缓存文件名会带 `_yahei1`，如果生成的图片文件名不是 `_yahei1`，说明 AstrBot 还在运行旧代码或旧缓存。

插件也会查找插件根目录里的这些字体文件：

- `msyh.ttc`
- `msyhbd.ttc`
- `simhei.ttf`
- `simsun.ttc`
- `Deng.ttf`
- `NotoSansCJK-Regular.ttc`
- `NotoSansSC-Regular.otf`

如果 AstrBot 跑在 Docker、虚拟环境或精简系统里，最稳的做法是把一个中文字体文件直接放到插件同级目录，例如：

```text
main.py
fortune_card.py
metadata.yaml
requirements.txt
msyh.ttc
```

插件也会查找这些 Windows 系统字体：

- `C:/Windows/Fonts/msyh.ttc`，微软雅黑
- `C:/Windows/Fonts/simhei.ttf`，黑体
- `C:/Windows/Fonts/simsun.ttc`，宋体
- `C:/Windows/Fonts/Deng.ttf`，等线

如果服务器是精简版系统，可以安装中文语言包，或把可用的中文字体文件放进插件目录后重启 AstrBot。

## 使用

在群聊里发送：

```text
@机器人 /抽签
```

插件会生成并缓存当天图片，同一 QQ 号当天重复抽签会得到同一张图。
