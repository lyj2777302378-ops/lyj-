# -*- coding: utf-8 -*-
"""SnapVid 万能视频下载站 — FastAPI 后端
封装 yt-dlp：解析视频信息 / 服务器中转下载（带 SSE 进度）/ 直链下载支持
"""
import asyncio
import glob
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path

import yt_dlp
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

try:
    import imageio_ffmpeg

    FFMPEG_LOCATION = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG_LOCATION = None  # 依赖系统 PATH 中的 ffmpeg

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
STATIC_DIR = BASE_DIR / "static"
COOKIES_FILE = BASE_DIR / "cookies.txt"  # 可选：用户自放 cookies 以解锁风控平台
DOWNLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI(title="SnapVid")

# task_id -> {status, percent, speed, eta, filename, path, error, title}
TASKS: dict[str, dict] = {}


def base_opts() -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": False,
        "socket_timeout": 20,
    }
    if FFMPEG_LOCATION:
        opts["ffmpeg_location"] = FFMPEG_LOCATION
    if COOKIES_FILE.exists():
        opts["cookiefile"] = str(COOKIES_FILE)
    return opts


URL_RE = re.compile(r"https?://[^\s，。；！？\"'<>）)】\]]+")


def extract_url(text: str) -> str:
    """从分享文案（如抖音/快手的一整段文字）中提取第一个链接。"""
    text = (text or "").strip()
    if text.startswith(("http://", "https://")):
        return text.split()[0]
    m = URL_RE.search(text)
    return m.group(0) if m else ""


class ParseReq(BaseModel):
    url: str


class DownloadReq(BaseModel):
    url: str
    selector: str = "best"
    title: str = ""


def _fmt_size(n):
    if not n:
        return None
    return round(n / 1024 / 1024, 1)  # MB


def build_options(info: dict) -> list[dict]:
    """从 yt-dlp formats 中提取清晰度选项。"""
    formats = info.get("formats") or []
    heights = sorted(
        {f["height"] for f in formats if f.get("vcodec") not in (None, "none") and f.get("height")},
        reverse=True,
    )
    options = []
    for h in heights[:6]:  # 最多展示 6 档
        # 找该分辨率下的「音视频合一」格式作为直链候选
        direct = next(
            (
                f
                for f in formats
                if f.get("height") == h
                and f.get("acodec") not in (None, "none")
                and f.get("vcodec") not in (None, "none")
                and f.get("url")
            ),
            None,
        )
        ref = next((f for f in formats if f.get("height") == h), {})
        options.append(
            {
                "label": f"{h}P",
                "height": h,
                "selector": f"bestvideo[height<={h}]+bestaudio/best[height<={h}]/best",
                "ext": (direct or ref).get("ext", "mp4"),
                "direct_url": direct.get("url") if direct else None,
                "size_mb": _fmt_size((direct or ref).get("filesize") or (direct or ref).get("filesize_approx")),
            }
        )
    # 纯音频选项
    if any(f.get("vcodec") in (None, "none") and f.get("acodec") not in (None, "none") for f in formats):
        options.append(
            {
                "label": "仅音频",
                "height": 0,
                "selector": "bestaudio/best",
                "ext": "m4a",
                "direct_url": None,
                "size_mb": None,
            }
        )
    if not options:
        options.append({"label": "最佳画质", "height": 0, "selector": "best", "ext": "mp4", "direct_url": None, "size_mb": None})
    return options


@app.post("/api/parse")
def parse(req: ParseReq):
    url = extract_url(req.url)
    if not url:
        raise HTTPException(400, "未识别到有效链接，请确认粘贴的内容中包含 http(s):// 地址")
    try:
        with yt_dlp.YoutubeDL(base_opts()) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(422, f"解析失败：{str(e)[:200]}")
    except Exception as e:
        raise HTTPException(500, f"解析异常：{str(e)[:200]}")

    if info.get("_type") == "playlist" or (info.get("entries") and not info.get("formats")):
        entries = []
        for ent in list(info.get("entries") or [])[:50]:
            if not ent:
                continue
            entries.append(
                {
                    "title": ent.get("title") or "未命名",
                    "url": ent.get("webpage_url") or ent.get("url"),
                    "duration": ent.get("duration"),
                    "thumbnail": ent.get("thumbnail"),
                }
            )
        return {
            "type": "playlist",
            "title": info.get("title") or "播放列表",
            "count": len(entries),
            "entries": entries,
        }

    return {
        "type": "video",
        "title": info.get("title") or "未命名视频",
        "thumbnail": info.get("thumbnail"),
        "duration": info.get("duration"),
        "uploader": info.get("uploader") or info.get("channel"),
        "platform": info.get("extractor_key"),
        "options": build_options(info),
    }


def _progress_hook(task_id: str):
    def hook(d):
        t = TASKS.get(task_id)
        if t is None:
            return
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes", 0)
            t["percent"] = round(done * 100 / total, 1) if total else None
            t["speed"] = d.get("_speed_str", "").strip()
            t["eta"] = d.get("_eta_str", "").strip()
            t["status"] = "downloading"
        elif d["status"] == "finished":
            t["status"] = "merging"
            t["percent"] = 100

    return hook


def _run_download(task_id: str, url: str, selector: str):
    t = TASKS[task_id]
    opts = base_opts()
    opts.update(
        {
            "format": selector,
            "outtmpl": str(DOWNLOAD_DIR / f"{task_id}.%(ext)s"),
            "progress_hooks": [_progress_hook(task_id)],
            "noplaylist": True,
        }
    )
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        files = sorted(DOWNLOAD_DIR.glob(f"{task_id}.*"), key=os.path.getmtime, reverse=True)
        if not files:
            raise RuntimeError("下载完成但未找到文件")
        t["path"] = str(files[0])
        t["ext"] = files[0].suffix.lstrip(".")
        t["status"] = "completed"
    except Exception as e:
        t["status"] = "error"
        t["error"] = str(e)[:300]


@app.post("/api/download")
def start_download(req: DownloadReq):
    url = extract_url(req.url)
    if not url:
        raise HTTPException(400, "未识别到有效链接")
    task_id = uuid.uuid4().hex[:12]
    safe_title = re.sub(r'[\\/:*?"<>|]+', "_", (req.title or "video"))[:80] or "video"
    TASKS[task_id] = {
        "status": "pending",
        "percent": 0,
        "speed": "",
        "eta": "",
        "filename": safe_title,
        "path": None,
        "ext": "mp4",
        "error": None,
    }
    threading.Thread(target=_run_download, args=(task_id, url, req.selector), daemon=True).start()
    return {"task_id": task_id}


@app.get("/api/progress/{task_id}")
async def progress(task_id: str):
    async def gen():
        while True:
            t = TASKS.get(task_id)
            if t is None:
                yield f"data: {json.dumps({'status': 'error', 'error': '任务不存在'})}\n\n"
                return
            yield f"data: {json.dumps(t, ensure_ascii=False)}\n\n"
            if t["status"] in ("completed", "error"):
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/api/file/{task_id}")
def get_file(task_id: str, background: BackgroundTasks):
    t = TASKS.get(task_id)
    if not t or t["status"] != "completed" or not t["path"]:
        raise HTTPException(404, "文件不存在或尚未下载完成")
    path = t["path"]

    def cleanup():
        try:
            os.remove(path)
        except OSError:
            pass
        TASKS.pop(task_id, None)

    background.add_task(cleanup)  # 发送后立即删除，服务器不留存
    return FileResponse(path, filename=f"{t['filename']}.{t['ext']}")


def _janitor():
    """定期清理超过 1 小时的残留文件。"""
    while True:
        time.sleep(600)
        now = time.time()
        for f in DOWNLOAD_DIR.glob("*"):
            try:
                if now - f.stat().st_mtime > 3600:
                    f.unlink()
            except OSError:
                pass


@app.on_event("startup")
def startup():
    for f in DOWNLOAD_DIR.glob("*"):
        try:
            f.unlink()
        except OSError:
            pass
    threading.Thread(target=_janitor, daemon=True).start()


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
