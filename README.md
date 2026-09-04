# 虎牙直播间自动化

当前版本实现以下功能：

- 连接已启用远程调试的 Microsoft Edge；
- 使用独立的 Edge 自动化用户目录，不影响日常 Edge；
- 复用已经打开的 `https://www.huya.com/660002` 标签页；
- 目标标签页不存在时自动创建；
- 检测虎牙登录状态，未登录时执行账号密码登录；
- 检测并进入剧场模式。

## 安装

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

## 运行

```bash
.venv/bin/huya-open-room
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

程序不会复制或修改日常 Edge 用户数据。
