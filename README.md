# Huya OH

[![Tests](https://github.com/yazhuo-wyze/huya-oh/actions/workflows/tests.yml/badge.svg)](https://github.com/yazhuo-wyze/huya-oh/actions/workflows/tests.yml)

基于 Python、Playwright 和本机 Chromium 浏览器的虎牙直播间自动化工具。

程序目前固定服务于直播间
[`https://www.huya.com/660002`](https://www.huya.com/660002)，可自动完成浏览器
连接、登录状态检查、播放器初始化和“欧皇时刻”活动监控。

> [!IMPORTANT]
> 本项目支持 macOS 和 Windows，依赖本机安装的 Microsoft Edge 或 Google Chrome。
> 页面自动化依赖虎牙现有 DOM 结构，网站改版后可能需要更新选择器。

## 功能

- 优先使用 Microsoft Edge，未安装 Edge 时自动回退到 Google Chrome。
- 支持多个虎牙账号使用独立浏览器实例并行运行。
- 使用独立的自动化 Profile，不读取或修改日常浏览器数据。
- 复用已打开的目标直播间标签页，不存在时才新建标签页。
- 检测登录状态，从本地 `config.toml` 读取账号密码。
- 自动静音直播间、关闭播放器弹幕并进入剧场模式。
- 每 5–10 秒随机检查一次“欧皇时刻”活动。
- 仅通过“免费抽 / 看视频免费参与”累计幸运值。
- 活动倒计时不足 1 分钟时，不再发起新的免费广告。
- 广告完成后自动确认任务，并等待幸运值实际到账。
- 开奖后领取基础金币，并通过追加广告领取页面允许的额外金币。
- 广告显示“没有获取到广告信息”时，关闭对应广告弹层并有限重试。
- 使用文件锁限制单实例运行，避免多个进程同时操作同一标签页。
- 输出浏览器、登录、活动、广告、幸运值和金币领取等运行日志。

## 安全边界

- 普通活动不会点击任何消耗金币的参与按钮。
- 免费参与按钮必须严格匹配“看视频免费参与”。
- 广告、奖励和活动状态无法确认时停止当前流程，不进行盲目点击。
- `dry-run` 模式只检测和记录状态，不执行登录、播放器或活动点击。
- `config.toml`、浏览器 Profile 和运行日志均不会提交到 Git。
- 程序不会复制、修改或关闭日常 Edge、Chrome 的用户数据。

## 环境要求

| 项目 | 要求 |
|---|---|
| 操作系统 | macOS、Windows 10/11 |
| Python | 3.11 或更高版本 |
| 浏览器 | Microsoft Edge（优先）或 Google Chrome |
| 目标直播间 | `https://www.huya.com/660002` |

无需执行 `playwright install`。程序通过 CDP 连接本机已经安装的 Edge 或 Chrome，
不会下载 Playwright 自带浏览器。

## 安装

### macOS

```bash
git clone https://github.com/yazhuo-wyze/huya-oh.git
cd huya-oh

python3 -m venv .venv
.venv/bin/python -m pip install -e .
source .venv/bin/activate
```

### Windows PowerShell

```powershell
git clone https://github.com/yazhuo-wyze/huya-oh.git
Set-Location huya-oh

py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\Activate.ps1
```

后续示例默认已经激活虚拟环境。安装完成后可执行
`huya-open-room --help` 查看命令说明。

## 账号配置

复制账号配置模板：

macOS：

```bash
cp config.example.toml config.toml
```

Windows PowerShell：

```powershell
Copy-Item config.example.toml config.toml
```

每个账号只需要填写虎牙用户名；`username` 同时作为账号 ID：

```toml
[[accounts]]
enabled = true
username = "账号A"
password = "密码A"

[[accounts]]
enabled = true
username = "账号B"
password = "密码B"
```

`config.toml` 已被 Git 忽略，程序不会在日志中输出密码；`username` 会作为
账号 ID 出现在日志中。请限制该文件只对当前用户可读，不要复制到公共位置。
不同账号必须使用不同的 `username`。CDP 端口由程序启动时自动选择，无需配置。

`username` 和 `password` 可以同时省略，以复用对应浏览器 Profile 中已有的
登录状态。如果虎牙要求验证码，自动登录会停止，并保留浏览器供人工处理。

## 运行

### 持续监控活动

```bash
huya-open-room
```

默认并行运行 `config.toml` 中所有 `enabled=true` 的账号，并持续检测活动。
按 `Ctrl+C` 停止全部账号工作进程。

### 仅初始化直播间

```bash
huya-open-room --no-monitor
```

完成登录检查、静音、关闭弹幕和剧场模式初始化后退出，浏览器保持打开。

### 只检测，不点击

```bash
huya-open-room --dry-run
```

该模式仍会启动或连接自动化浏览器并打开直播间，但不会提交登录信息、切换
播放器状态或参与活动。

### 运行一个配置账号

```bash
huya-open-room --account "账号A"
```

该账号使用独立浏览器 Profile 和程序自动分配的 CDP 端口。即使
`enabled=false`，仍可通过该命令单独启动，便于调试或人工登录。

### 并行运行全部账号

```bash
huya-open-room --all-accounts
```

该参数与直接运行 `huya-open-room` 等价，用于显式表达运行全部账号。程序会
为每个 `enabled=true` 的账号启动独立工作进程和浏览器实例。按 `Ctrl+C`
会停止所有账号工作进程，但已启动的浏览器窗口仍会保留。

如果不希望在 `config.toml` 保存密码，可以省略对应账号的 `username` 和
`password`，再用以下命令打开所有独立 Profile：

```bash
huya-open-room --all-accounts --no-monitor
```

在每个浏览器窗口中人工完成对应账号登录后，再启动正式监控。未配置该账号
凭据且对应 Profile 尚未登录时，该账号会输出错误并退出，不会影响其他账号。

## 浏览器数据

Edge 与 Chrome 使用不同的自动化 Profile。

macOS：

```text
~/Library/Application Support/Huya Automation/Edge
~/Library/Application Support/Huya Automation/Chrome
```

Windows：

```text
%LOCALAPPDATA%\Huya Automation\Edge
%LOCALAPPDATA%\Huya Automation\Chrome
```

多账号模式在上述目录下增加账号隔离层。为兼容邮箱、手机号和 Windows 文件
系统，目录名是根据 `username` 生成的稳定哈希，而不是明文用户名：

```text
# macOS
~/Library/Application Support/Huya Automation/Accounts/account-<hash>/Edge

# Windows
%LOCALAPPDATA%\Huya Automation\Accounts\account-<hash>\Edge
```

首次切换到另一种浏览器时，需要在对应 Profile 中重新登录虎牙。之后运行会
继续复用该浏览器的登录状态。

浏览器选择顺序：

1. Microsoft Edge
2. Google Chrome
3. 两者均未安装时终止并输出错误

## 欧皇时刻流程

1. 每 5–10 秒读取播放器工具栏中的活动入口状态。
2. 入口显示倒计时时，打开活动面板并选择“免费抽”。
3. 严格确认按钮为“看视频免费参与”后启动广告。
4. 广告出现“恭喜完成任务”后点击完成。
5. 等待累计幸运值实际增加，再继续下一次免费参与。
6. 幸运值达到目标、免费入口不可用或倒计时不足 1 分钟时停止发起新广告。
7. 开奖后点击“只领xxxx金币”，并确认“开心收下”。
8. 如果存在“不够！再领xxx金币”，通过广告继续领取，直到达到页面上限。

如果广告显示“没有获取到广告信息”，程序只关闭包含该广告 iframe 的弹层，
等待弹层消失后重新定位参与按钮，最多自动重试一次，不会误关活动面板或无限刷新。

程序重启后如果页面仍保留“恭喜完成任务”或金币奖励弹层，会优先恢复并完成
遗留流程。

## 日志

日志格式为：

```text
时间 | 级别 | 账号 ID | 模块 | 消息
```

示例：

```text
2026-09-07 10:14:28 | INFO | 账号A | huya_automation.main | 已选择 Microsoft Edge
2026-09-07 10:14:51 | INFO | 账号B | huya_automation.room | 找到已打开的目标直播间标签页
```

浏览器调试输出保存在系统的 `Huya Automation` 应用数据目录中，文件名为
`edge-debug.log` 或 `chrome-debug.log`。

## 常见问题

### 提示自动化浏览器正在运行，但没有开放调试端口

关闭自动化专用的 Edge 或 Chrome 窗口后重新运行。不要删除自动化 Profile，
否则会丢失该 Profile 中的登录状态。

### 提示 CDP 端口被其他浏览器占用

关闭提示中对应的自动化浏览器后重新运行。新浏览器的 CDP 端口由程序自动
选择；已运行的账号浏览器会自动发现并复用原端口。

### 程序提示已有实例运行

同一账号不能重复启动，不同账号可以并行运行；全部账号模式的监督进程也有
独立锁，避免重复启动两组工作进程。

### 登录时出现验证码

在程序打开的自动化浏览器中完成人工验证，然后重新运行程序。

### 网站改版后找不到按钮

停止程序并查看终端日志。不要反复启动或手动修改选择器后直接投入金币操作。
相关页面选择器和活动逻辑集中在 `src/huya_automation/`。

## 开发与测试

GitHub Actions 会在 macOS 和 Windows 上使用 Python 3.11、3.14 运行测试。
本地运行全部测试：

```bash
python -m unittest discover -s tests -v
```

项目主要模块：

```text
src/huya_automation/
├── accounts.py       # 多账号配置读取与校验
├── auth.py           # 登录状态与账号密码登录
├── browser.py        # Edge/Chrome 检测、启动和 CDP 连接
├── instance_lock.py  # 单实例文件锁
├── lucky_event.py    # 欧皇时刻、广告、幸运值和金币流程
├── main.py           # 命令行入口
└── room.py           # 标签页、静音、弹幕和剧场模式
```

更完整的需求和安全约束见 [`xuqiu.md`](xuqiu.md)。

## 免责声明

本项目仅供学习和个人自动化研究。使用者应自行确认并遵守虎牙服务协议、活动
规则及所在地区的法律法规。因使用本项目产生的账号限制、奖励变化或其他后果，
由使用者自行承担。
