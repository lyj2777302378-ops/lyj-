# SnapVid 万能视频下载站

粘贴视频链接（或整段分享文案），即可从 1000+ 平台下载视频。PC / 手机浏览器均可使用。

> 仅供学习与技术研究使用，请尊重原创版权。

## 功能

- 链接/分享文案解析：自动提取文本中的链接，返回标题、封面、清晰度档位、大小预估
- 双下载模式：直链下载（走平台 CDN）+ 中转下载（服务器代下，SSE 实时进度）
- 播放列表识别、纯音频提取
- 响应式 UI，手机浏览器直接用
- 服务器零留存：文件发送后即删 + 定时清理
- 风控平台支持：项目根目录放 `cookies.txt` 自动生效

## 技术栈

- 后端：FastAPI + yt-dlp（pip 封装，不改源码），无数据库
- 前端：原生 HTML/CSS/JS 单页（`static/`）
- ffmpeg：imageio-ffmpeg 自带二进制

## 快速开始

```bash
pip install fastapi "uvicorn[standard]" yt-dlp imageio-ffmpeg
python main.py
# 浏览器打开 http://localhost:8000
```

Windows 用户可直接双击 `启动.bat`。

## 风控平台 cookies

部分平台（抖音、B站高清等）需要 fresh cookies：

```bash
python tools/refresh_cookies.py        # 用本机 Chrome 访问抖音并导出 cookies.txt
python tools/refresh_cookies.py <url>  # 指定其他站点
```

依赖：`pip install playwright`，脚本默认使用本机已有的 Chrome/Chromium。

## 文档

- [需求分析](docs/需求分析.md)
- [方案设计](docs/方案设计.md)（含接口契约、验数记录、扩展点）
