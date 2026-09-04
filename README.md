# 虎牙直播间自动化

当前版本实现以下功能：

- 连接已启用远程调试的 Microsoft Edge；
- 使用独立的 Edge 自动化用户目录，不影响日常 Edge；
- 复用已经打开的 `https://www.huya.com/660002` 标签页；
- 目标标签页不存在时自动创建；
- 检测虎牙登录状态，未登录时执行账号密码登录；
- 检测直播声音并自动静音；
- 检测并关闭播放器弹幕；
- 检测并进入剧场模式；
- 每 15 秒检测欧皇时刻，每秒检查广告完成状态；
- 只通过“免费抽/看视频免费参与”累计幸运值，达到 200 后停止本轮。

## 安装

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

## 运行

```bash
.venv/bin/huya-open-room
```

程序会持续检测活动，按 `Ctrl+C` 停止。只初始化直播间、不监控活动：

```bash
.venv/bin/huya-open-room --no-monitor
```

程序不会保存账号或密码。自动化 Profile 位于：

```text
~/Library/Application Support/Huya Automation/Edge
```

登录状态由 Edge 保存在该专用 Profile 中，后续运行会自动复用。
复制示例并填写本地 `.env`：

```bash
cp .env.example .env
```

```dotenv
HUYA_USERNAME=你的账号
HUYA_PASSWORD=你的密码
```

程序会自动读取 `.env`。该文件已被 Git 忽略，不会提交到仓库。
未配置时，程序会在终端提示输入账号，并隐藏密码输入。若虎牙要求验证码，
程序会停止后续自动操作，并保留登录框供人工完成验证。日常 Edge 可以同时运行。

只检查计划执行的操作、不切换剧场模式：

```bash
.venv/bin/huya-open-room --dry-run
```

活动入口显示倒计时时才视为本轮开启；显示“已结束”、活动面板消失或
免费广告入口不可用时，会立即停止本轮操作并等待下一轮。本阶段不会点击
任何金币参与控件。

程序不会复制或修改日常 Edge 用户数据。
