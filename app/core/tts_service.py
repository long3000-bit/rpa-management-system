"""文本转语音服务

基于 edge-tts 库实现文本转语音功能
"""

import asyncio
import os
import tempfile
import time
import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Dict, Optional
from pathlib import Path

import edge_tts
from edge_tts import Communicate, SubMaker

from app.storage.database import Database


@dataclass
class TTSResult:
    """TTS生成结果"""
    success: bool
    mp3_path: Optional[str] = None
    srt_path: Optional[str] = None
    error_message: Optional[str] = None
    duration: float = 0.0  # 生成用时（秒）
    audio_size: int = 0    # 音频文件大小（字节）
    srt_size: int = 0      # 字幕文件大小（字节）


@dataclass
class VoiceInfo:
    """语音信息"""
    name: str
    locale: str
    friendly_name: str
    gender: str
    language: str
    categories: List[str]
    personalities: List[str]


class TTSService:
    """文本转语音服务"""
    
    def __init__(self, db: Database):
        self.db = db
        self.output_dir = self._get_output_dir()
        os.makedirs(self.output_dir, exist_ok=True)
    
    def _get_output_dir(self) -> str:
        """获取输出目录"""
        # 使用临时目录存储生成的音频文件
        output_dir = os.path.join(tempfile.gettempdir(), "rpa_tts_output")
        os.makedirs(output_dir, exist_ok=True)
        return output_dir
    
    def get_available_voices(self, show_all: bool = False) -> List[VoiceInfo]:
        """获取可用的语音列表
        
        Args:
            show_all: 是否显示所有语言的语音（默认只显示中文）
        
        Returns:
            List[VoiceInfo]: 语音信息列表
        """
        try:
            voices = asyncio.run(edge_tts.list_voices())
            result = []
            
            for v in voices:
                locale = (v.get("Locale") or "").lower()
                vt = v.get("VoiceTag") or {}
                
                # 默认只显示中文语音
                if not show_all and not locale.startswith("zh"):
                    continue
                
                voice_info = VoiceInfo(
                    name=v.get("ShortName") or v.get("Name", ""),
                    locale=v.get("Locale", ""),
                    friendly_name=v.get("FriendlyName", ""),
                    gender=v.get("Gender", ""),
                    language=locale.split("-")[0],
                    categories=vt.get("ContentCategories", []),
                    personalities=vt.get("VoicePersonalities", [])
                )
                result.append(voice_info)
            
            # 按语言和名称排序
            result.sort(key=lambda x: (x.locale, x.name))
            
            return result
            
        except Exception as e:
            print(f"获取语音列表失败: {e}")
            return []
    
    def generate_tts(
        self,
        text: str,
        voice: str = "zh-CN-XiaoxiaoNeural",
        rate: str = "+0%",
        volume: str = "+0%",
        pitch: str = "+0Hz",
        bgm_path: Optional[str] = None,
        bgm_volume: int = 20
    ) -> TTSResult:
        """生成文本转语音
        
        Args:
            text: 要转换的文本
            voice: 语音名称
            rate: 语速调整（如 +20%, -10%）
            volume: 音量调整（如 +50%, -20%）
            pitch: 音调调整（如 +10Hz, -5Hz）
            bgm_path: 背景音乐文件路径（可选）
            bgm_volume: 背景音乐音量百分比（0-100）
        
        Returns:
            TTSResult: 生成结果
        """
        if not text or not text.strip():
            return TTSResult(
                success=False,
                error_message="文本内容不能为空"
            )
        
        # 格式化参数
        rate = self._format_percent(rate)
        volume = self._format_percent(volume)
        pitch = self._format_pitch(pitch)
        
        # 生成唯一文件名
        timestamp = int(time.time() * 1000)
        voice_mp3_path = os.path.join(self.output_dir, f"{timestamp}_voice.mp3")
        final_mp3_path = os.path.join(self.output_dir, f"{timestamp}.mp3")
        srt_path = os.path.join(self.output_dir, f"{timestamp}.srt")
        
        start_time = time.time()
        
        try:
            # 1. 生成TTS语音
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
            
            print(f"TTS生成完成: {audio_bytes/1024:.1f} KB, {word_count} 个片段")
            
            # 2. 生成字幕文件
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write(submaker.get_srt())
            
            # 3. 混音（如果有背景音乐）
            if bgm_path and os.path.exists(bgm_path):
                bgm_size = os.path.getsize(bgm_path)
                
                if bgm_size < 1024:
                    print("背景音乐文件过小，跳过混音")
                    shutil.copy(voice_mp3_path, final_mp3_path)
                else:
                    ffmpeg_path = self._find_ffmpeg()
                    
                    if ffmpeg_path:
                        print(f"使用ffmpeg混音 (bgm_volume={bgm_volume}%)...")
                        self._mix_with_bgm(
                            voice_path=voice_mp3_path,
                            bgm_path=bgm_path,
                            output_path=final_mp3_path,
                            bgm_volume_percent=bgm_volume
                        )
                    else:
                        print("未找到ffmpeg，使用纯语音输出")
                        shutil.copy(voice_mp3_path, final_mp3_path)
            else:
                shutil.copy(voice_mp3_path, final_mp3_path)
            
            # 清理临时文件
            try:
                if os.path.exists(voice_mp3_path):
                    os.remove(voice_mp3_path)
            except:
                pass
            
            duration = time.time() - start_time
            audio_size = os.path.getsize(final_mp3_path)
            srt_size = os.path.getsize(srt_path)
            
            print(f"TTS生成完成，用时 {duration:.1f}s, MP3 {audio_size/1024:.1f} KB")
            
            return TTSResult(
                success=True,
                mp3_path=final_mp3_path,
                srt_path=srt_path,
                duration=duration,
                audio_size=audio_size,
                srt_size=srt_size
            )
            
        except Exception as e:
            # 清理临时文件
            for path in [voice_mp3_path, final_mp3_path, srt_path]:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except:
                    pass
            
            return TTSResult(
                success=False,
                error_message=str(e)
            )
    
    def _format_percent(self, value: str, default_sign: str = "+") -> str:
        """格式化百分比参数"""
        value = (value or "").strip()
        if not value:
            return "+0%"
        
        try:
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
    
    def _format_pitch(self, value: str) -> str:
        """格式化音调参数"""
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
    
    def _find_ffmpeg(self) -> Optional[str]:
        """查找ffmpeg可执行文件"""
        # 1. 尝试使用imageio-ffmpeg
        try:
            import imageio_ffmpeg
            path = imageio_ffmpeg.get_ffmpeg_exe()
            if path and os.path.isfile(path):
                return path
        except:
            pass
        
        # 2. 从系统PATH查找
        found = shutil.which("ffmpeg")
        if found:
            return found
        
        # 3. Windows常见路径
        for candidate in [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\ffmpeg\bin\ffmpeg.exe"),
        ]:
            if os.path.isfile(candidate):
                return candidate
        
        return None
    
    def _mix_with_bgm(
        self,
        voice_path: str,
        bgm_path: str,
        output_path: str,
        bgm_volume_percent: int
    ) -> None:
        """使用ffmpeg混音"""
        ffmpeg = self._find_ffmpeg()
        if not ffmpeg:
            raise RuntimeError("未找到ffmpeg，无法混音")
        
        bgm_gain = max(0.0, min(1.0, float(bgm_volume_percent) / 100.0))
        
        cmd = [
            ffmpeg,
            "-y",
            "-i", voice_path,
            "-stream_loop", "-1",
            "-i", bgm_path,
            "-shortest",
            "-filter_complex",
            f"[1:a]volume={bgm_gain:.3f}[a1];[0:a][a1]amix=inputs=2:duration=first:normalize=0[aout]",
            "-map", "[aout]",
            "-c:a", "libmp3lame",
            "-b:a", "192k",
            output_path
        ]
        
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg混音失败: {proc.stderr[-500:]}")
    
    def cleanup_old_files(self, max_age_hours: int = 1):
        """清理旧的音频文件
        
        Args:
            max_age_hours: 文件最大保留时间（小时）
        """
        now = time.time()
        max_age_seconds = max_age_hours * 3600
        
        try:
            for filename in os.listdir(self.output_dir):
                filepath = os.path.join(self.output_dir, filename)
                
                if os.path.isfile(filepath):
                    file_age = now - os.path.getmtime(filepath)
                    
                    if file_age > max_age_seconds:
                        try:
                            os.remove(filepath)
                            print(f"清理旧文件: {filename}")
                        except:
                            pass
        except Exception as e:
            print(f"清理文件失败: {e}")