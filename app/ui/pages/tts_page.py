"""文本转语音页面

提供文本转语音功能的UI界面
"""

import os
import threading
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QComboBox, QSpinBox,
    QGroupBox, QFormLayout, QFileDialog, QProgressBar,
    QMessageBox, QSlider, QFrame, QCheckBox
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtGui import QStandardItemModel, QStandardItem

from app.storage.database import Database
from app.core.tts_service import TTSService, TTSResult, VoiceInfo


class TTSWorker(QThread):
    """TTS生成工作线程"""
    
    finished = Signal(TTSResult)
    
    def __init__(
        self,
        tts_service: TTSService,
        text: str,
        voice: str,
        rate: str,
        volume: str,
        pitch: str,
        bgm_path: str = None,
        bgm_volume: int = 20
    ):
        super().__init__()
        self.tts_service = tts_service
        self.text = text
        self.voice = voice
        self.rate = rate
        self.volume = volume
        self.pitch = pitch
        self.bgm_path = bgm_path
        self.bgm_volume = bgm_volume
    
    def run(self):
        result = self.tts_service.generate_tts(
            text=self.text,
            voice=self.voice,
            rate=self.rate,
            volume=self.volume,
            pitch=self.pitch,
            bgm_path=self.bgm_path,
            bgm_volume=self.bgm_volume
        )
        self.finished.emit(result)


class TTSPage(QWidget):
    """文本转语音页面"""
    
    def __init__(self, db: Database, user: dict):
        super().__init__()
        self.db = db
        self.user = user
        self.tts_service = TTSService(db)
        
        # 当前生成的音频文件路径
        self.current_mp3_path = None
        self.current_srt_path = None
        
        # 播放器
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        
        # 工作线程
        self.tts_worker = None
        
        self._init_ui()
        self._load_voices()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        
        # 标题
        title = QLabel("文本转语音")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #333;")
        layout.addWidget(title)
        
        # 文本输入区
        text_group = QGroupBox("文本内容")
        text_layout = QVBoxLayout(text_group)
        
        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText("在此输入要朗读的文本...")
        self.text_input.setMinimumHeight(150)
        self.text_input.setText("你好，欢迎使用文本转语音服务。你可以在这里输入任意中文文本，然后点击生成按钮。")
        text_layout.addWidget(self.text_input)
        
        layout.addWidget(text_group)
        
        # 语音参数设置
        params_group = QGroupBox("语音参数")
        params_layout = QFormLayout(params_group)
        
        # 语音选择
        voice_row = QHBoxLayout()
        self.voice_combo = QComboBox()
        self.voice_combo.setMinimumWidth(300)
        voice_row.addWidget(self.voice_combo)
        
        self.show_all_checkbox = QCheckBox("显示全部语言")
        self.show_all_checkbox.stateChanged.connect(self._on_show_all_changed)
        voice_row.addWidget(self.show_all_checkbox)
        
        voice_row.addStretch()
        params_layout.addRow("选择语音:", voice_row)
        
        # 语音信息显示
        self.voice_info_label = QLabel()
        self.voice_info_label.setStyleSheet("color: #666; font-size: 12px;")
        params_layout.addRow("", self.voice_info_label)
        
        # 语速、音量、音调
        params_row = QHBoxLayout()
        
        # 语速
        rate_widget = QWidget()
        rate_layout = QVBoxLayout(rate_widget)
        rate_layout.setContentsMargins(0, 0, 0, 0)
        rate_layout.addWidget(QLabel("语速 (%)"))
        self.rate_spin = QSpinBox()
        self.rate_spin.setRange(-100, 100)
        self.rate_spin.setValue(0)
        self.rate_spin.setSingleStep(5)
        rate_layout.addWidget(self.rate_spin)
        params_row.addWidget(rate_widget)
        
        # 音量
        volume_widget = QWidget()
        volume_layout = QVBoxLayout(volume_widget)
        volume_layout.setContentsMargins(0, 0, 0, 0)
        volume_layout.addWidget(QLabel("音量 (%)"))
        self.volume_spin = QSpinBox()
        self.volume_spin.setRange(-100, 100)
        self.volume_spin.setValue(0)
        self.volume_spin.setSingleStep(5)
        volume_layout.addWidget(self.volume_spin)
        params_row.addWidget(volume_widget)
        
        # 音调
        pitch_widget = QWidget()
        pitch_layout = QVBoxLayout(pitch_widget)
        pitch_layout.setContentsMargins(0, 0, 0, 0)
        pitch_layout.addWidget(QLabel("音调 (Hz)"))
        self.pitch_spin = QSpinBox()
        self.pitch_spin.setRange(-50, 50)
        self.pitch_spin.setValue(0)
        self.pitch_spin.setSingleStep(5)
        pitch_layout.addWidget(self.pitch_spin)
        params_row.addWidget(pitch_widget)
        
        params_row.addStretch()
        params_layout.addRow("", params_row)
        
        layout.addWidget(params_group)
        
        # 背景音乐设置
        bgm_group = QGroupBox("背景音乐（可选）")
        bgm_layout = QVBoxLayout(bgm_group)
        
        bgm_file_row = QHBoxLayout()
        self.bgm_path_label = QLabel("未选择背景音乐")
        self.bgm_path_label.setStyleSheet("color: #666;")
        bgm_file_row.addWidget(self.bgm_path_label)
        
        select_bgm_btn = QPushButton("选择音乐文件")
        select_bgm_btn.clicked.connect(self._select_bgm_file)
        bgm_file_row.addWidget(select_bgm_btn)
        
        clear_bgm_btn = QPushButton("清除")
        clear_bgm_btn.clicked.connect(self._clear_bgm_file)
        bgm_file_row.addWidget(clear_bgm_btn)
        
        bgm_file_row.addStretch()
        bgm_layout.addLayout(bgm_file_row)
        
        # 背景音乐音量
        bgm_volume_row = QHBoxLayout()
        bgm_volume_row.addWidget(QLabel("背景音乐音量:"))
        
        self.bgm_volume_slider = QSlider(Qt.Horizontal)
        self.bgm_volume_slider.setRange(0, 100)
        self.bgm_volume_slider.setValue(20)
        self.bgm_volume_slider.valueChanged.connect(self._on_bgm_volume_changed)
        bgm_volume_row.addWidget(self.bgm_volume_slider)
        
        self.bgm_volume_label = QLabel("20%")
        self.bgm_volume_label.setMinimumWidth(50)
        bgm_volume_row.addWidget(self.bgm_volume_label)
        
        bgm_layout.addLayout(bgm_volume_row)
        
        layout.addWidget(bgm_group)
        
        # 生成按钮
        btn_row = QHBoxLayout()
        
        self.generate_btn = QPushButton("生成语音")
        self.generate_btn.setMinimumHeight(40)
        self.generate_btn.clicked.connect(self._generate_tts)
        btn_row.addWidget(self.generate_btn)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        btn_row.addWidget(self.progress_bar)
        
        btn_row.addStretch()
        
        layout.addLayout(btn_row)
        
        # 结果显示区
        result_group = QGroupBox("生成结果")
        result_layout = QVBoxLayout(result_group)
        
        # 播放控制
        play_row = QHBoxLayout()
        
        self.play_btn = QPushButton("播放")
        self.play_btn.setEnabled(False)
        self.play_btn.clicked.connect(self._play_audio)
        play_row.addWidget(self.play_btn)
        
        self.stop_btn = QPushButton("停止")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_audio)
        play_row.addWidget(self.stop_btn)
        
        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: #666;")
        play_row.addWidget(self.status_label)
        
        play_row.addStretch()
        result_layout.addLayout(play_row)
        
        # 下载按钮
        download_row = QHBoxLayout()
        
        self.download_mp3_btn = QPushButton("下载MP3")
        self.download_mp3_btn.setEnabled(False)
        self.download_mp3_btn.clicked.connect(self._download_mp3)
        download_row.addWidget(self.download_mp3_btn)
        
        self.download_srt_btn = QPushButton("下载字幕")
        self.download_srt_btn.setEnabled(False)
        self.download_srt_btn.clicked.connect(self._download_srt)
        download_row.addWidget(self.download_srt_btn)
        
        download_row.addStretch()
        result_layout.addLayout(download_row)
        
        # 结果信息
        self.result_info_label = QLabel()
        self.result_info_label.setStyleSheet("color: #333; font-size: 13px;")
        result_layout.addWidget(self.result_info_label)
        
        layout.addWidget(result_group)
        
        # 说明
        note_label = QLabel(
            "说明：基于 Microsoft Edge 在线 TTS 服务。生成的文件会保存在临时目录，建议及时下载保存。"
        )
        note_label.setStyleSheet("color: #888; font-size: 12px; padding: 8px;")
        layout.addWidget(note_label)
        
        layout.addStretch()
    
    def _load_voices(self):
        """加载语音列表"""
        show_all = self.show_all_checkbox.isChecked()
        voices = self.tts_service.get_available_voices(show_all=show_all)
        
        self.voice_combo.clear()
        
        for voice in voices:
            # 显示友好名称
            display_text = f"{voice.friendly_name} ({voice.locale})"
            self.voice_combo.addItem(display_text, voice.name)
        
        # 默认选择第一个中文语音
        if self.voice_combo.count() > 0:
            self.voice_combo.setCurrentIndex(0)
            self._update_voice_info()
        
        self.voice_combo.currentIndexChanged.connect(self._update_voice_info)
    
    def _on_show_all_changed(self, state):
        """显示全部语言选项改变"""
        self._load_voices()
    
    def _update_voice_info(self):
        """更新语音信息显示"""
        show_all = self.show_all_checkbox.isChecked()
        voices = self.tts_service.get_available_voices(show_all=show_all)
        
        current_index = self.voice_combo.currentIndex()
        if current_index >= 0 and current_index < len(voices):
            voice = voices[current_index]
            
            info_parts = []
            if voice.gender:
                info_parts.append(f"性别: {voice.gender}")
            if voice.categories:
                info_parts.append(f"类别: {', '.join(voice.categories)}")
            
            self.voice_info_label.setText(" | ".join(info_parts) if info_parts else "")
    
    def _select_bgm_file(self):
        """选择背景音乐文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择背景音乐文件",
            "",
            "音频文件 (*.mp3 *.wav *.m4a *.ogg *.flac);;所有文件 (*.*)"
        )
        
        if file_path:
            self.bgm_path = file_path
            filename = os.path.basename(file_path)
            self.bgm_path_label.setText(f"已选择: {filename}")
            self.bgm_path_label.setStyleSheet("color: #333;")
    
    def _clear_bgm_file(self):
        """清除背景音乐文件"""
        self.bgm_path = None
        self.bgm_path_label.setText("未选择背景音乐")
        self.bgm_path_label.setStyleSheet("color: #666;")
    
    def _on_bgm_volume_changed(self, value):
        """背景音乐音量改变"""
        self.bgm_volume_label.setText(f"{value}%")
    
    def _generate_tts(self):
        """生成TTS"""
        text = self.text_input.toPlainText().strip()
        
        if not text:
            QMessageBox.warning(self, "提示", "请输入要转换的文本内容")
            return
        
        # 获取参数
        voice_name = self.voice_combo.currentData()
        if not voice_name:
            QMessageBox.warning(self, "提示", "请选择语音")
            return
        
        rate = f"{self.rate_spin.value()}%"
        volume = f"{self.volume_spin.value()}%"
        pitch = f"{self.pitch_spin.value()}Hz"
        bgm_volume = self.bgm_volume_slider.value()
        
        # 禁用按钮，显示进度
        self.generate_btn.setEnabled(False)
        self.generate_btn.setText("生成中...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # 无限进度条
        
        self.status_label.setText("正在生成...")
        
        # 启动工作线程
        self.tts_worker = TTSWorker(
            self.tts_service,
            text,
            voice_name,
            rate,
            volume,
            pitch,
            self.bgm_path,
            bgm_volume
        )
        self.tts_worker.finished.connect(self._on_tts_finished)
        self.tts_worker.start()
    
    def _on_tts_finished(self, result: TTSResult):
        """TTS生成完成"""
        # 恢复按钮状态
        self.generate_btn.setEnabled(True)
        self.generate_btn.setText("生成语音")
        self.progress_bar.setVisible(False)
        
        if result.success:
            self.current_mp3_path = result.mp3_path
            self.current_srt_path = result.srt_path
            
            # 更新状态
            self.status_label.setText(f"生成完成，用时 {result.duration:.1f}s")
            
            # 更新结果信息
            info_text = f"音频大小: {result.audio_size/1024:.1f} KB | 字幕大小: {result.srt_size/1024:.1f} KB"
            self.result_info_label.setText(info_text)
            
            # 启用播放和下载按钮
            self.play_btn.setEnabled(True)
            self.download_mp3_btn.setEnabled(True)
            self.download_srt_btn.setEnabled(True)
            
            QMessageBox.information(
                self,
                "生成成功",
                f"语音已生成完成！\n用时: {result.duration:.1f}秒\n音频大小: {result.audio_size/1024:.1f} KB"
            )
        else:
            self.status_label.setText("生成失败")
            QMessageBox.warning(
                self,
                "生成失败",
                f"语音生成失败：{result.error_message}"
            )
    
    def _play_audio(self):
        """播放音频"""
        if self.current_mp3_path and os.path.exists(self.current_mp3_path):
            self.player.setSource(self.current_mp3_path)
            self.player.play()
            
            self.play_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.status_label.setText("正在播放...")
            
            # 监听播放状态
            self.player.playbackStateChanged.connect(self._on_playback_state_changed)
    
    def _stop_audio(self):
        """停止播放"""
        self.player.stop()
        self.play_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText("已停止")
    
    def _on_playback_state_changed(self, state):
        """播放状态改变"""
        if state == QMediaPlayer.StoppedState:
            self.play_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.status_label.setText("播放完成")
    
    def _download_mp3(self):
        """下载MP3文件"""
        if not self.current_mp3_path or not os.path.exists(self.current_mp3_path):
            QMessageBox.warning(self, "提示", "没有可下载的音频文件")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存MP3文件",
            "tts_output.mp3",
            "MP3文件 (*.mp3)"
        )
        
        if file_path:
            try:
                import shutil
                shutil.copy(self.current_mp3_path, file_path)
                QMessageBox.information(self, "成功", f"MP3文件已保存到: {file_path}")
            except Exception as e:
                QMessageBox.warning(self, "失败", f"保存文件失败: {e}")
    
    def _download_srt(self):
        """下载字幕文件"""
        if not self.current_srt_path or not os.path.exists(self.current_srt_path):
            QMessageBox.warning(self, "提示", "没有可下载的字幕文件")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存字幕文件",
            "tts_output.srt",
            "字幕文件 (*.srt)"
        )
        
        if file_path:
            try:
                import shutil
                shutil.copy(self.current_srt_path, file_path)
                QMessageBox.information(self, "成功", f"字幕文件已保存到: {file_path}")
            except Exception as e:
                QMessageBox.warning(self, "失败", f"保存文件失败: {e}")
    
    def cleanup(self):
        """清理资源"""
        # 停止播放
        if self.player:
            self.player.stop()
        
        # 停止工作线程
        if self.tts_worker and self.tts_worker.isRunning():
            self.tts_worker.terminate()
            self.tts_worker.wait()
        
        # 清理临时文件
        self.tts_service.cleanup_old_files(max_age_hours=1)