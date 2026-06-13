"""Simple Web UI for edge-tts.

Provides endpoints:
- GET  /                         → render HTML page
- GET  /api/voices                → list available voices
- POST /api/generate               → generate mp3 + srt and returns audio stream / download
- GET  /api/download/<token>/<kind>   → download previously generated mp3 or srt
"""

import asyncio
import io
import os
import secrets
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional

from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    send_file,
    send_from_directory,
)

import edge_tts
from edge_tts import Communicate, SubMaker


OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Keep small files around for a short time so users can download.
FILE_TTL_SECONDS = 30 * 60  # 30 minutes


@dataclass
class Job:
    mp3_path: str
    srt_path: str
    created_at: float
    text: str
    voice: str
    rate: str
    volume: str
    pitch: str


JOBS: Dict[str, Job] = {}
_JOBS_LOCK = threading.Lock()


def find_ffmpeg() -> Optional[str]:
    """Locate the ffmpeg executable.

    Priority:
    1. imageio-ffmpeg (pip package that bundles a static build)
    2. system PATH
    3. common Windows installation paths
    """
    try:
        import imageio_ffmpeg  # type: ignore

        path = imageio_ffmpeg.get_ffmpeg_exe()
        if path and os.path.isfile(path):
            return path
    except Exception:  # noqa: BLE001
        pass

    found = shutil.which("ffmpeg")
    if found:
        return found

    # Common Windows paths
    for candidate in (
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\ffmpeg\bin\ffmpeg.exe"),
    ):
        if os.path.isfile(candidate):
            return candidate
    return None


FFMPEG_NOT_FOUND_MSG = (
    "未找到 ffmpeg，无法混音。请安装后重试：\n"
    "方式一：pip install imageio-ffmpeg  （自动带 ffmpeg 二进制）\n"
    "方式二：从 https://www.gyan.dev/ffmpeg/builds/ 下载并加入 PATH\n"
    "方式三：winget install Gyan.FFmpeg  （需 Windows 10+）"
)


def mix_with_bgm(
    voice_path: str,
    bgm_path: str,
    output_path: str,
    bgm_volume_percent: int,
) -> None:
    """Mix TTS voice with a background music file using ffmpeg.

    The music is looped (or trimmed) to match voice duration,
    then its volume is reduced and mixed with the voice.
    """
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError(FFMPEG_NOT_FOUND_MSG)

    # bgm_volume_percent comes in 0-100; ffmpeg volume filter uses multiplicative gain
    # 1.0 = original volume. We usually want background music to be softer, so we
    # interpret the percent as: 20 → 0.2x original music volume.
    bgm_gain = max(0.0, min(1.0, float(bgm_volume_percent) / 100.0))

    # ffmpeg command:
    #   -i voice.mp3  -stream_loop -1 -i bgm.mp3
    #   -shortest  → stop when the first (voice) input ends
    #   -filter_complex "[1:a]volume=0.2[a1];[0:a][a1]amix=inputs=2:duration=first:normalize=0"
    #   -c:a libmp3lame -b:a 192k output.mp3
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        voice_path,
        "-stream_loop",
        "-1",
        "-i",
        bgm_path,
        "-shortest",
        "-filter_complex",
        f"[1:a]volume={bgm_gain:.3f}[a1];[0:a][a1]amix=inputs=2:duration=first:normalize=0[aout]",
        "-map",
        "[aout]",
        "-c:a",
        "libmp3lame",
        "-b:a",
        "192k",
        output_path,
    ]

    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg 混音失败 (exit={proc.returncode})\n"
            f"stderr:\n{proc.stderr[-2000:]}"
        )


def _cleanup_old_jobs() -> None:
    """Remove jobs/files older than FILE_TTL_SECONDS."""
    now = time.time()
    with _JOBS_LOCK:
        expired = [
            token
            for token, job in JOBS.items()
            if now - job.created_at > FILE_TTL_SECONDS
        ]
        for token in expired:
            job = JOBS.pop(token)
            for p in (job.mp3_path, job.srt_path):
                try:
                    if p and os.path.exists(p):
                        os.remove(p)
                except OSError:
                    pass


def _schedule_cleanup() -> None:
    _cleanup_old_jobs()
    threading.Timer(60, _schedule_cleanup).daemon = True
    threading.Timer(60, _schedule_cleanup).start()


_schedule_cleanup()


app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

_VERSION = str(int(time.time()))


def _cached_static_version() -> str:
    """A cheap "file-hash" version string; busts the browser cache whenever
    static/app.js changes. Uses mtime so no file content is read.
    """
    js_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "static", "app.js"
    )
    try:
        return str(int(os.path.getmtime(js_path)))
    except OSError:
        return _VERSION


@app.after_request
def _add_no_cache_headers(resp):  # noqa: D401
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


def _format_percent(value: str, default_sign: str = "+") -> str:
    """Normalize a user-supplied percent value like '+10%' or '10' to '10%'."""
    value = (value or "").strip()
    if not value:
        return "+0%"
    # Allow raw integers like 10 or -5
    try:
        # Try to parse as integer (percent)
        f = float(value.rstrip("%"))
        sign = "-" if f < 0 else "+"
        return f"{sign}{int(abs(f))}%"
    except ValueError:
        pass
    if value[0] not in ("+", "-"):
        value = f"{default_sign}{value}"
    if not value.endswith("%"):
        value = f"{value}%"
    return value


def _format_pitch(value: str) -> str:
    """Normalize a pitch value like '+10Hz' or '10' to '+10Hz'."""
    value = (value or "").strip()
    if not value:
        return "+0Hz"
    try:
        f = float(value.rstrip("Hz").strip() or "0")
        sign = "-" if f < 0 else "+"
        return f"{sign}{int(abs(f))}Hz"
    except ValueError:
        pass
    if value[0] not in ("+", "-"):
        value = f"+{value}"
    if not value.lower().endswith("hz"):
        value = f"{value}Hz"
    return value


@app.route("/")
def index():
    return render_template("index.html", version=_cached_static_version())


@app.route("/api/voices")
def api_voices():
    show_all = (request.args.get("all") or "").lower() in ("1", "true", "yes")
    try:
        voices = asyncio.run(edge_tts.list_voices())
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500
    result = []
    for v in voices:
        locale = (v.get("Locale") or "").lower()
        vt = v.get("VoiceTag") or {}
        entry = {
            "name": v.get("ShortName") or v.get("Name", ""),
            "locale": v.get("Locale", ""),
            "friendly": v.get("FriendlyName", ""),
            "gender": v.get("Gender", ""),
            "language": locale.split("-")[0],
            "categories": vt.get("ContentCategories", []),
            "personalities": vt.get("VoicePersonalities", []),
        }
        if show_all or locale.startswith("zh"):
            result.append(entry)
    result.sort(key=lambda x: (x["locale"], x["name"]))
    return jsonify(result)


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


@app.post("/api/generate")
def api_generate():
    text = (request.form.get("text") or "").strip()
    voice = (request.form.get("voice") or "").strip() or "en-US-AriaNeural"
    rate = _format_percent(request.form.get("rate") or "+0%")
    volume = _format_percent(request.form.get("volume") or "+0%")
    pitch = _format_pitch(request.form.get("pitch") or "+0Hz")

    bgm_file = request.files.get("bgm")
    has_bgm = bool(bgm_file and bgm_file.filename and bgm_file.mimetype)
    bgm_volume_raw = request.form.get("bgm_volume") or "20"
    try:
        bgm_volume = int(bgm_volume_raw)
    except (TypeError, ValueError):
        bgm_volume = 20
    bgm_volume = max(0, min(100, bgm_volume))

    if not text:
        return jsonify({"error": "text is required"}), 400

    _log(f"开始生成: text={len(text)} 字, voice={voice}, bgm={has_bgm}")
    t0 = time.time()

    token = secrets.token_urlsafe(16)
    voice_mp3_path = os.path.join(OUTPUT_DIR, f"{token}_voice.mp3")
    final_mp3_path = os.path.join(OUTPUT_DIR, f"{token}.mp3")
    srt_path = os.path.join(OUTPUT_DIR, f"{token}.srt")
    bgm_temp_path: Optional[str] = None
    err_msg: Optional[str] = None

    try:
        # 1) Generate TTS voice
        communicate = Communicate(text, voice, rate=rate, volume=volume, pitch=pitch)
        submaker = SubMaker()
        audio_bytes = 0
        word_count = 0
        with open(voice_mp3_path, "wb") as f:
            for chunk in communicate.stream_sync():
                if chunk["type"] == "audio":
                    data = chunk["data"]
                    audio_bytes += len(data)
                    f.write(data)
                elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                    submaker.feed(chunk)
                    word_count += 1

        _log(f"  TTS 完成: {audio_bytes/1024:.1f} KB, {word_count} 个片段, 用时 {time.time()-t0:.1f}s")

        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(submaker.get_srt())

        # 2) Mix with background music if provided and valid
        if has_bgm:
            assert bgm_file is not None
            ext = os.path.splitext(bgm_file.filename)[1].lower() or ".mp3"
            bgm_temp_path = os.path.join(OUTPUT_DIR, f"{token}_bgm{ext}")
            bgm_file.save(bgm_temp_path)
            bgm_size = os.path.getsize(bgm_temp_path)
            _log(f"  背景音乐已保存: {bgm_size/1024:.1f} KB ({ext})")

            if bgm_size < 1024:
                _log("  背景音乐文件过小 (<1KB), 跳过混音")
                shutil.copy(voice_mp3_path, final_mp3_path)
            else:
                ffmpeg_path = find_ffmpeg()
                if not ffmpeg_path:
                    _log("  未找到 ffmpeg, 回退到纯语音输出")
                    shutil.copy(voice_mp3_path, final_mp3_path)
                    err_msg = FFMPEG_NOT_FOUND_MSG + "\n（已为你生成纯语音版本）"
                else:
                    _log(f"  使用 ffmpeg 混音 (bgm_volume={bgm_volume}%) ...")
                    t1 = time.time()
                    mix_with_bgm(
                        voice_path=voice_mp3_path,
                        bgm_path=bgm_temp_path,
                        output_path=final_mp3_path,
                        bgm_volume_percent=bgm_volume,
                    )
                    _log(f"  混音完成, 用时 {time.time()-t1:.1f}s")
        else:
            shutil.copy(voice_mp3_path, final_mp3_path)
    except Exception as exc:  # noqa: BLE001
        _log(f"  出错: {exc}")
        for p in (voice_mp3_path, final_mp3_path, srt_path, bgm_temp_path):
            try:
                if p and os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass
        return jsonify({"error": str(exc)}), 500
    finally:
        for p in (voice_mp3_path, bgm_temp_path):
            try:
                if p and os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass

    with _JOBS_LOCK:
        JOBS[token] = Job(
            mp3_path=final_mp3_path,
            srt_path=srt_path,
            created_at=time.time(),
            text=text,
            voice=voice,
            rate=rate,
            volume=volume,
            pitch=pitch,
        )

    final_size = os.path.getsize(final_mp3_path)
    _log(f"完成: 总用时 {time.time()-t0:.1f}s, MP3 {final_size/1024:.1f} KB")

    resp = {
        "token": token,
        "mp3_size": final_size,
        "srt_size": os.path.getsize(srt_path),
        "mp3_url": f"/api/download/{token}/mp3",
        "srt_url": f"/api/download/{token}/srt",
    }
    if err_msg:
        resp["error"] = err_msg
        resp["warning"] = "ffmpeg-not-available"
    return jsonify(resp)


@app.get("/api/ping")
def api_ping():
    return jsonify({"ok": True, "time": time.time()})


@app.get("/api/download/<token>/<kind>")
def api_download(token: str, kind: str):
    with _JOBS_LOCK:
        job: Optional[Job] = JOBS.get(token)
    if job is None:
        return jsonify({"error": "not found or expired"}), 404
    if kind == "mp3":
        return send_file(
            job.mp3_path, mimetype="audio/mpeg", as_attachment=True, download_name="tts.mp3"
        )
    if kind == "srt":
        return send_file(
            job.srt_path,
            mimetype="text/plain; charset=utf-8",
            as_attachment=True,
            download_name="tts.srt",
        )
    return jsonify({"error": "invalid kind"}), 400


@app.get("/api/listen/<token>")
def api_listen(token: str):
    """Serve mp3 inline so the browser audio tag can play it."""
    with _JOBS_LOCK:
        job: Optional[Job] = JOBS.get(token)
    if job is None:
        return jsonify({"error": "not found or expired"}), 404
    return send_file(job.mp3_path, mimetype="audio/mpeg", as_attachment=False)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Web UI for edge-tts")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    print(f"edge-tts Web UI running at http://{args.host}:{args.port}/")
    print("  （用浏览器打开上面的地址；直接双击 HTML 文件会因浏览器安全策略无法 fetch）")
    # threaded=True: 允许并发处理多个请求（否则 Flask 内置开发服务器是单线程的，
    #   生成期间浏览器的其他请求会排队超时，出现"Failed to fetch"）
    # passthrough_errors=True: 调试时更容易看到完整异常栈
    app.run(
        host=args.host,
        port=args.port,
        debug=args.debug,
        threaded=True,
        passthrough_errors=args.debug,
    )


if __name__ == "__main__":
    main()
