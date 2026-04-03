# LanScreenMonitor V1

> 局域网屏幕监控 —— 零配置、扫码即看、账号密码保护

## 功能特性

- 🖥️ **零配置启动** — 双击即运行，自动检测 IP / 端口
- 📱 **扫码即看** — 手机扫二维码，浏览器打开即可观看电脑屏幕
- 🔐 **账号密码登录** — 首次启动设置账号密码，PBKDF2-SHA256 哈希存储
- 🔑 **密码管理** — 支持修改密码、重置密码（忘记密码时）
- 🎬 **双协议推流** — WebRTC 低延迟优先，自动降级 MJPEG
- 📊 **三档画质** — 流畅 / 高清 / 省流，可手动切换
- ⚡ **过载自动降级** — 帧率不足时自动切换低档位
- 🔌 **断连检测** — PC 端退出后手机端即时提示，支持一键重连
- 🛡️ **安全机制** — Token 有效期 10 分钟 + IP 限频 + 登录限速
- 🎯 **科技感启动画面** — 全屏动画 Splash Screen

## 快速开始

### 方式一：直接运行（开发环境）

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 运行
python app.py
```

### 方式二：打包为 exe

**推荐：双击一键打包**
```bash
# 直接双击 build.bat 即可完成打包（自动安装依赖 + 打包）
build.bat
```

**手动打包**
```bash
# 1. 安装依赖 + pyinstaller
pip install -r requirements.txt pyinstaller

# 2. 打包（onedir 模式，--noconfirm 自动覆盖旧输出）
python -m PyInstaller --noconfirm LanScreenMonitor.spec

# 3. 输出在 dist/LanScreenMonitor/ 目录
```

> **注意**：如果 `pyinstaller` 命令提示找不到，请使用 `python -m PyInstaller` 代替。
> 这在 Microsoft Store 版 Python 中很常见（Scripts 目录未加入 PATH）。

## 使用方法

1. **双击** `LanScreenMonitor.exe`（或 `python app.py`）
2. 首次启动会弹出 **设置账号密码** 窗口
3. 看到 **弹窗二维码**，控制台也会显示访问地址
4. 手机（同一局域网）**扫码** → 打开页面 → 输入账号密码登录 → 点击 **"开始播放"**
5. 观看屏幕画面，可切换 **流畅 / 高清 / 省流**

## 弹窗功能按钮

| 按钮 | 功能 |
|------|------|
| 🔄 刷新口令 | 刷新 Token，所有已登录用户需重新登录 |
| 🔑 修改密码 | 验证旧密码后设置新密码 |
| 🧩 重置密码 | 忘记密码时重新设置账号和密码 |
| ❌ 退出 | 关闭程序 |

## 控制台命令

| 按键 | 功能 |
|------|------|
| `R`  | 刷新 Token（旧二维码失效，生成新二维码） |
| `Q`  | 退出程序 |

## 画质档位

| 档位 | 分辨率 | 帧率 | 适用场景 |
|------|--------|------|----------|
| 流畅 (smooth) | 1280×720  | 15fps | 默认，兼顾流畅与清晰 |
| 高清 (hd)     | 1920×1080 | 30fps | 带宽充裕时使用 |
| 省流 (low)    | 854×480   | 10fps | 低带宽 / 低性能兜底 |

## 安全机制

- 🔐 首次启动必须设置登录账号密码
- 🔒 密码使用 PBKDF2-SHA256（260,000 次迭代）哈希存储，不保存明文
- 🎫 登录成功后服务端颁发 Token，有效期 10 分钟
- 🚫 同 IP 每分钟最多 10 次登录尝试
- 🚫 同 IP 每分钟最多 20 次非法访问
- 📁 认证配置存储于 `%LOCALAPPDATA%\LanScreenMonitor\auth.json`

## 断连检测

PC 端退出程序后，手机端会通过 5 层检测机制即时感知：

1. 服务端主动推送 `server_shutdown` 消息
2. WebSocket `onclose` 事件
3. WebRTC 连接状态监听
4. 媒体轨道 `ended` 事件
5. 定时健康检查轮询（3 秒间隔）

断连后显示遮罩提示，支持一键重连。

## 故障排查

| 问题 | 解决方案 |
|------|----------|
| 手机无法连接 | 允许程序通过 Windows 防火墙（专用网络） |
| 画面卡顿 | 切换到"流畅"或"省流"模式 |
| 端口冲突 | 程序会自动尝试 9000-9049 |
| WebRTC 失败 | 自动降级为 MJPEG（延迟略高但可看） |
| 忘记密码 | 点击弹窗"重置密码"按钮重新设置 |

## 项目结构

```
Screen_monitoring/
├── app.py                # 主入口 (App 协调器)
├── config.py             # 全局常量配置
├── log_setup.py          # 日志初始化
├── net_selector.py       # 网络选择 (IP/端口)
├── token_manager.py      # Token 管理
├── auth_manager.py       # 认证管理 (账号密码/PBKDF2)
├── screen_capture.py     # 屏幕采集 (mss)
├── webrtc_manager.py     # WebRTC 会话管理
├── mjpeg_streamer.py     # MJPEG 降级流
├── web_server.py         # aiohttp Web 服务器
├── qr_window.py          # 二维码弹窗 (tkinter)
├── splash_window.py      # 科技感启动画面
├── single_instance.py    # 单实例锁 (Windows)
├── web/
│   └── index.html        # 前端 Viewer 页面 (登录+播放+断连检测)
├── requirements.txt      # Python 依赖
├── LanScreenMonitor.spec # PyInstaller 打包配置
├── build.bat             # 一键打包脚本（双击即用）
├── file_version_info.txt # exe 版本信息
└── README.md
```

## 技术栈

- **后端**: Python 3.10+, aiohttp, aiortc, mss
- **前端**: 原生 HTML/JS/CSS（无框架依赖）
- **编码**: VP8 (WebRTC) / JPEG (MJPEG 降级)
- **认证**: PBKDF2-SHA256 哈希 + Token 鉴权
- **GUI**: tkinter（二维码弹窗 + 启动画面 + 密码对话框）
- **打包**: PyInstaller (onedir)

## 系统要求

- Windows 10/11
- Python 3.10+（开发时）
- 同一局域网内的手机浏览器（Chrome / Safari）
