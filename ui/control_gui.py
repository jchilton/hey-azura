#!/usr/bin/env python3
"""
Lady Azura Companion - Unified Control Dashboard (PySide6)
Integrates microphone listening, Chatterbox Docker status, live VU meters,
interactive text/voice chat, OBS overlay status, and inline configuration into a single master GUI.
"""

import sys
import os
import json
import time
import logging
import threading
import numpy as np
import sounddevice as sd

from PySide6.QtCore import Qt, QTimer, Signal, Slot, QObject
from PySide6.QtGui import QFont, QIcon, QColor, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QProgressBar, QGroupBox,
    QComboBox, QCheckBox, QTabWidget, QSplitter, QFrame, QMessageBox, QStatusBar
)

from core.chatterbox_tts import ChatterboxTTSClient
from core.audio_player import AudioPlayer
from core.llm_azura import AzuraLLM
from core.listener import AudioListener
from core.chatterbox_manager import ChatterboxDockerManager
from ui.overlay_server import OverlayServer
from ui.settings_dialog import AzuraSettingsDialog, show_settings_dialog

logger = logging.getLogger(__name__)

MASTER_GUI_STYLE = """
QMainWindow, QWidget#centralWidget {
    background-color: #0d0718;
    color: #e0d6f2;
    font-family: 'Segoe UI', Roboto, sans-serif;
}
QGroupBox {
    border: 1px solid #3c2463;
    border-radius: 8px;
    margin-top: 10px;
    padding-top: 12px;
    font-weight: bold;
    color: #ffd700;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
}
QLabel#badgeActive {
    background-color: #1a4d2e;
    color: #4caf50;
    border: 1px solid #2e7d32;
    border-radius: 10px;
    padding: 3px 10px;
    font-weight: bold;
    font-size: 11px;
}
QLabel#badgeWorking {
    background-color: #4a3800;
    color: #ffd700;
    border: 1px solid #8c6e00;
    border-radius: 10px;
    padding: 3px 10px;
    font-weight: bold;
    font-size: 11px;
}
QLabel#badgeOffline {
    background-color: #4a151b;
    color: #f44336;
    border: 1px solid #b71c1c;
    border-radius: 10px;
    padding: 3px 10px;
    font-weight: bold;
    font-size: 11px;
}
QTextEdit#chatLog {
    background-color: #140c24;
    border: 1px solid #3c2463;
    border-radius: 8px;
    padding: 10px;
    color: #e0d6f2;
    font-size: 13px;
    selection-background-color: #6336a1;
}
QLineEdit#inputField {
    background-color: #1b1030;
    border: 1px solid #5c438c;
    border-radius: 6px;
    padding: 8px 12px;
    color: #ffffff;
    font-size: 13px;
}
QLineEdit#inputField:focus {
    border-color: #ffd700;
}
QPushButton {
    background-color: #3b1d66;
    color: #ffffff;
    border: 1px solid #6b3ba8;
    border-radius: 6px;
    padding: 7px 16px;
    font-weight: bold;
    font-size: 12px;
}
QPushButton:hover {
    background-color: #552a94;
    border-color: #ffd700;
}
QPushButton#sendBtn {
    background-color: #8c62d9;
    border-color: #ffd700;
    color: #ffffff;
}
QPushButton#sendBtn:hover {
    background-color: #9f75ed;
}
QProgressBar#vuBar {
    border: 1px solid #3c2463;
    border-radius: 5px;
    background-color: #120921;
    height: 12px;
}
QProgressBar#vuBar::chunk {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6b3ba8, stop:0.7 #a872e6, stop:1 #ffd700);
    border-radius: 4px;
}
QComboBox {
    background-color: #1b1030;
    border: 1px solid #5c438c;
    border-radius: 6px;
    padding: 3px 8px;
    color: #ffd700;
    font-weight: bold;
    font-size: 11px;
}
QComboBox:hover {
    border-color: #ffd700;
}
QComboBox QAbstractItemView {
    background-color: #140c24;
    color: #e0d6f2;
    selection-background-color: #6336a1;
    border: 1px solid #5c438c;
}
"""

class BridgeWorker(QObject):
    """Signals for background threads to safely update Qt GUI components."""
    status_changed = Signal(str, float)
    wake_started = Signal()
    query_received = Signal(str)
    response_ready = Signal(str, str, list, float)  # (question, response, sources, elapsed)
    listener_ready = Signal()
    listener_failed = Signal(str)

class AzuraControlDashboard(QMainWindow):
    """Single Unified Control Window for Lady Azura Companion."""

    def __init__(self, config_path: str = "config.json"):
        super().__init__()
        self.config_path = config_path
        self.config = {}
        self.bridge = BridgeWorker()
        self.listener = None
        self.docker_mgr = None
        self.tts = None
        self.player = None
        self.llm = None
        self.overlay = None
        self._smoothed_vu = 0

        self.setWindowTitle("Lady Azura Companion - Master Control Dashboard")
        self.resize(920, 680)

        self._load_config()
        self._init_ui()
        self._connect_signals()

        # Defer heavy model and Docker loading so GUI window opens INSTANTLY
        QTimer.singleShot(50, self._async_init_subsystems)

    def _load_config(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
            except Exception as e:
                logger.error(f"Error loading config {self.config_path}: {e}")

    def _async_init_subsystems(self):
        self.statusBar.showMessage("Starting Chatterbox Docker & initializing audio engines...")
        out_idx = self.config.get("audio", {}).get("output_device_index")
        
        # 1. Docker & Chatterbox Manager
        try:
            self.docker_mgr = ChatterboxDockerManager(self.config)
            self.docker_mgr.ensure_started()
        except Exception as e:
            logger.warning(f"Docker manager warning: {e}")

        # 2. TTS Client & Audio Player
        self.tts = ChatterboxTTSClient(self.config)
        self.player = AudioPlayer(device_index=out_idx)

        # 3. LLM Engine
        try:
            self.llm = AzuraLLM(self.config)
        except Exception as e:
            logger.error(f"Error initializing LLM engine: {e}")
        self._update_llm_badge()

        # 4. OBS Overlay Web Server
        overlay_port = self.config.get("ui", {}).get("overlay_port", 8035)
        self.overlay = OverlayServer(port=overlay_port)
        self.overlay.start()

        # Update initial TTS status badge
        self._update_tts_badge()

        # 5. Start Audio Listener
        self.statusBar.showMessage("Loading Whisper STT model...")
        self._start_listening()
        self.statusBar.showMessage("Lady Azura Companion is active and watching over Vvardenfell.")

    def _init_ui(self):
        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)
        self.setStyleSheet(MASTER_GUI_STYLE)

        layout = QVBoxLayout(central)

        # Header Title Banner
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        t_label = QLabel("✦ L A D Y   A Z U R A ✦")
        t_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        t_label.setStyleSheet("color: #ffd700;")
        s_label = QLabel("The Elder Scrolls III: Morrowind Voice AI Companion • Master Control Dashboard")
        s_label.setStyleSheet("color: #9d8db8; font-size: 12px;")
        title_box.addWidget(t_label)
        title_box.addWidget(s_label)
        header.addLayout(title_box)

        header.addStretch()

        settings_btn = QPushButton("⚙ Settings")
        settings_btn.clicked.connect(self._open_settings)
        header.addWidget(settings_btn)

        clear_btn = QPushButton("Reset Memory")
        clear_btn.clicked.connect(self._clear_memory)
        header.addWidget(clear_btn)

        layout.addLayout(header)

        # Subsystems Status Panel
        status_box = QGroupBox("System Status & Service Health")
        status_layout = QHBoxLayout(status_box)

        # Status 1: Listener
        status_layout.addWidget(QLabel("Voice Listener:"))
        self.lbl_listener = QLabel("INITIALIZING...")
        self.lbl_listener.setObjectName("badgeWorking")
        status_layout.addWidget(self.lbl_listener)
        status_layout.addSpacing(15)

        # Status 2: Chatterbox TTS
        status_layout.addWidget(QLabel("Chatterbox TTS:"))
        self.lbl_tts = QLabel("CHECKING...")
        self.lbl_tts.setObjectName("badgeWorking")
        status_layout.addWidget(self.lbl_tts)
        status_layout.addSpacing(15)

        # Status 3: LLM Engine Badge
        status_layout.addWidget(QLabel("LLM Engine:"))
        self.lbl_llm = QLabel("INITIALIZING...")
        self.lbl_llm.setObjectName("badgeActive")
        status_layout.addWidget(self.lbl_llm)
        status_layout.addSpacing(15)

        # Status 4: OBS Overlay Copy Button
        status_layout.addWidget(QLabel("OBS Overlay:"))
        overlay_port = self.config.get("ui", {}).get("overlay_port", 8035)
        self.overlay_url = f"http://localhost:{overlay_port}"

        copy_overlay_btn = QPushButton("📋 Copy URL")
        copy_overlay_btn.setToolTip(f"Copy OBS Browser Source URL ({self.overlay_url}) to Clipboard")
        copy_overlay_btn.clicked.connect(self._copy_overlay_url)
        status_layout.addWidget(copy_overlay_btn)

        status_layout.addStretch()

        layout.addWidget(status_box)

        # Live VU Meter Panel
        vu_box = QGroupBox("Microphone Input & Voice Meter")
        vu_vlayout = QVBoxLayout(vu_box)

        # Top Row: Status Text (Left) & Mute Button (Right)
        status_row = QHBoxLayout()
        self.mic_status_lbl = QLabel("Listening for 'Hey Azura'...")
        self.mic_status_lbl.setStyleSheet("color: #b5a2d9; font-style: italic; font-size: 12px;")
        status_row.addWidget(self.mic_status_lbl, stretch=1)

        self.mute_btn = QPushButton("Mute Mic")
        self.mute_btn.setCheckable(True)
        self.mute_btn.toggled.connect(self._toggle_mute)
        status_row.addWidget(self.mute_btn)

        vu_vlayout.addLayout(status_row)

        # Bottom Row: Full-width smoothed VU bar without text
        self.vu_bar = QProgressBar()
        self.vu_bar.setObjectName("vuBar")
        self.vu_bar.setRange(0, 100)
        self.vu_bar.setValue(0)
        self.vu_bar.setTextVisible(False)
        vu_vlayout.addWidget(self.vu_bar)

        layout.addWidget(vu_box)

        # Chat Conversation History Window
        self.chat_log = QTextEdit()
        self.chat_log.setObjectName("chatLog")
        self.chat_log.setReadOnly(True)
        layout.addWidget(self.chat_log, stretch=1)

        # Interactive Query Input Bar
        input_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setObjectName("inputField")
        self.input_field.setPlaceholderText("Type a question or ask aloud with 'Hey Azura'...")
        self.input_field.returnPressed.connect(self._submit_text_query)
        input_layout.addWidget(self.input_field, stretch=1)

        send_btn = QPushButton("Ask Azura")
        send_btn.setObjectName("sendBtn")
        send_btn.clicked.connect(self._submit_text_query)
        input_layout.addWidget(send_btn)

        layout.addLayout(input_layout)

        # Status Bar
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Lady Azura Companion is active and watching over Vvardenfell.")

        # Update initial TTS and LLM status badges
        self._update_tts_badge()
        self._update_llm_badge()

    def _update_tts_badge(self):
        if self.tts and self.tts.is_healthy():
            self.lbl_tts.setText(f"CONNECTED ({self.tts.host}:{self.tts.port})")
            self.lbl_tts.setObjectName("badgeActive")
        else:
            self.lbl_tts.setText("CHECKING...")
            self.lbl_tts.setObjectName("badgeWorking")
        self.lbl_tts.style().unpolish(self.lbl_tts)
        self.lbl_tts.style().polish(self.lbl_tts)

    def _update_llm_badge(self):
        llm_cfg = self.config.get("llm", {})
        provider = llm_cfg.get("provider", "gemini").title()
        model = llm_cfg.get("model") or llm_cfg.get("gemini_model", "gemini-3.5-flash")
        self.lbl_llm.setText(f"{provider} ({model})")
        self.lbl_llm.setObjectName("badgeActive")
        self.lbl_llm.style().unpolish(self.lbl_llm)
        self.lbl_llm.style().polish(self.lbl_llm)

    def _connect_signals(self):
        self.bridge.status_changed.connect(self._on_listener_status)
        self.bridge.wake_started.connect(self._on_wake_started)
        self.bridge.query_received.connect(self._on_query_received)
        self.bridge.response_ready.connect(self._on_response_ready)
        self.bridge.listener_ready.connect(self._on_listener_ready)
        self.bridge.listener_failed.connect(self._on_listener_failed)

    def _start_listening(self):
        def on_wake_started():
            if hasattr(self, "overlay") and self.overlay:
                self.overlay.set_state("listening")
            self.bridge.wake_started.emit()

        def on_wake_detected(query_text: str):
            self.bridge.query_received.emit(query_text)

        def on_state(state: str, rms: float):
            self.bridge.status_changed.emit(state, rms)

        def _init_listener_thread():
            try:
                listener = AudioListener(
                    config=self.config,
                    on_wake_started=on_wake_started,
                    on_wake_detected=on_wake_detected,
                    on_state_change=on_state
                )
                listener.start()
                self.listener = listener
                self.bridge.listener_ready.emit()
            except Exception as e:
                logger.error(f"Failed to start AudioListener: {e}")
                err_msg = str(e)
                self.bridge.listener_failed.emit(err_msg)

        threading.Thread(target=_init_listener_thread, daemon=True).start()

    @Slot()
    def _on_listener_ready(self):
        self.lbl_listener.setText("ACTIVE")
        self.lbl_listener.setObjectName("badgeActive")
        self.lbl_listener.style().unpolish(self.lbl_listener)
        self.lbl_listener.style().polish(self.lbl_listener)
        self.mic_status_lbl.setText("Listening for 'Hey Azura'...")
        self.statusBar.showMessage("Lady Azura Companion is active and watching over Vvardenfell.")

    @Slot(str)
    def _on_listener_failed(self, err_msg: str):
        self.lbl_listener.setText("OFFLINE")
        self.lbl_listener.setObjectName("badgeOffline")
        self.lbl_listener.style().unpolish(self.lbl_listener)
        self.lbl_listener.style().polish(self.lbl_listener)
        self.mic_status_lbl.setText(f"Listener offline ({err_msg})")
        self.statusBar.showMessage(f"Voice Listener Error: {err_msg}")

    @Slot(str, float)
    def _on_listener_status(self, state: str, rms: float):
        target_val = int(min(100, rms * 3.5))
        self._smoothed_vu = int(self._smoothed_vu * 0.55 + target_val * 0.45)
        if abs(self._smoothed_vu - self.vu_bar.value()) >= 1:
            self.vu_bar.setValue(self._smoothed_vu)

        if self.lbl_listener.text() != "ACTIVE" and state in ["LISTENING", "HEARING_SPEECH", "PROCESSING_AUDIO", "CALIBRATING"]:
            self.lbl_listener.setText("ACTIVE")
            self.lbl_listener.setObjectName("badgeActive")
            self.lbl_listener.style().unpolish(self.lbl_listener)
            self.lbl_listener.style().polish(self.lbl_listener)

        if state == "CALIBRATING":
            self.mic_status_lbl.setText("Calibrating mic ambient noise...")
        elif state == "LISTENING":
            self.mic_status_lbl.setText("Listening for 'Hey Azura'...")
        elif state == "HEARING_SPEECH":
            self.mic_status_lbl.setText("Voice Detected - Recording query...")
        elif state == "PROCESSING_AUDIO":
            self.mic_status_lbl.setText("Transcribing speech...")

    @Slot()
    def _on_wake_started(self):
        self.statusBar.showMessage("Wake word detected! Listening to user prompt...")

    @Slot(str)
    def _on_query_received(self, query_text: str):
        if not query_text.strip():
            self.overlay.set_state("idle")
            return
        
        self.statusBar.showMessage(f"Processing query: '{query_text}'...")
        # Process query in background thread so GUI stays perfectly responsive
        threading.Thread(target=self._process_query_thread, args=(query_text,), daemon=True).start()

    def _process_query_thread(self, user_question: str):
        if hasattr(self, "overlay") and self.overlay:
            self.overlay.set_state("researching")
        start_t = time.time()
        if not self.llm:
            return
        spoken_response, sources = self.llm.query(user_question)
        elapsed = time.time() - start_t

        self.bridge.response_ready.emit(user_question, spoken_response, sources, elapsed)

        # Synthesize & Play Audio
        if self.tts:
            audio_bytes = self.tts.synthesize(spoken_response)
            if audio_bytes and self.player:
                if hasattr(self, "overlay") and self.overlay:
                    self.overlay.set_state("speaking")
                self.player.play_bytes(audio_bytes, blocking=True)

        if hasattr(self, "overlay") and self.overlay:
            self.overlay.set_state("idle")

    @Slot(str, str, list, float)
    def _on_response_ready(self, question: str, response: str, sources: list, elapsed: float):
        # Format HTML log entry
        q_html = f"<div style='margin-bottom: 8px;'><b style='color: #00e5ff;'>You:</b> {question}</div>"
        r_html = f"<div style='margin-bottom: 12px;'><b style='color: #ffd700;'>✦ Lady Azura:</b> \"{response}\"<br><span style='color: #7d6b99; font-size: 11px;'>(Reasoning: {elapsed:.2f}s)</span></div>"
        
        if sources:
            src_str = ", ".join([s['title'] for s in sources])
            r_html += f"<div style='color: #9d8db8; font-size: 11px; margin-bottom: 14px;'>Consulted: {src_str}</div>"

        self.chat_log.append(q_html + r_html)
        self.chat_log.moveCursor(QTextCursor.End)
        self.statusBar.showMessage("Lady Azura answered.")

    def _submit_text_query(self):
        text = self.input_field.text().strip()
        if not text:
            return
        self.input_field.clear()
        self._on_query_received(text)

    def _toggle_mute(self, checked: bool):
        if checked:
            if self.listener:
                self.listener.stop()
            self.lbl_listener.setText("MUTED")
            self.lbl_listener.setObjectName("badgeOffline")
            self.mic_status_lbl.setText("Microphone muted.")
        else:
            self._start_listening()
            self.mic_status_lbl.setText("Listening for 'Hey Azura'...")
        self.lbl_listener.style().unpolish(self.lbl_listener)
    def _copy_overlay_url(self):
        QApplication.clipboard().setText(self.overlay_url)
        self.statusBar.showMessage(f"Copied OBS Overlay URL to clipboard: {self.overlay_url}", 4000)

    def _clear_memory(self):
        if self.llm:
            self.llm.clear_history()
        self.chat_log.append("<div style='color: #ffd700; margin-bottom: 10px;'><i>✦ Past inquiries cleared from Azura's memory.</i></div>")
        self.statusBar.showMessage("Conversational memory cleared.")

    def _open_settings(self):
        accepted = show_settings_dialog(self.config_path)
        if accepted:
            self._load_config()
            self._update_tts_badge()
            self._update_llm_badge()
            try:
                self.llm = AzuraLLM(self.config)
            except Exception as e:
                logger.error(f"Failed to re-initialize LLM: {e}")
            self.statusBar.showMessage("Settings reloaded and applied active configuration.", 5000)

    def closeEvent(self, event):
        logger.info("Closing Master Control Dashboard...")
        if self.listener:
            self.listener.stop()
        if self.player:
            self.player.stop()
        if hasattr(self, "overlay") and self.overlay:
            self.overlay.stop()
        if hasattr(self, "docker_mgr") and self.docker_mgr:
            self.docker_mgr.stop_container()
        super().closeEvent(event)

def launch_control_gui(config_path: str = "config.json"):
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    win = AzuraControlDashboard(config_path=config_path)
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    launch_control_gui()
