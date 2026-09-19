import sys
import os
import json
import logging
import numpy as np
import sounddevice as sd

from PySide6.QtCore import Qt, QTimer, Slot, QObject, Signal
from PySide6.QtGui import QFont, QIcon, QColor, QPalette
from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QComboBox, QLineEdit, QPushButton, QCheckBox, QProgressBar,
    QGroupBox, QTabWidget, QWidget, QMessageBox, QFileDialog
)

from core.voice_extractor import (
    find_all_morrowind_videos, extract_azura_voice_from_biks, upload_voice_sample_to_chatterbox
)

logger = logging.getLogger(__name__)

# Daedric Twilight Palette Stylesheet
DARK_TWILIGHT_STYLE = """
QDialog {
    background-color: #120b1f;
    color: #e0d6f2;
    font-family: 'Segoe UI', Roboto, sans-serif;
}
QGroupBox {
    border: 1px solid #4a3475;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 14px;
    font-weight: bold;
    color: #ffd700;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QLabel {
    color: #c9b6e4;
    font-size: 13px;
}
QComboBox, QLineEdit {
    background-color: #1f1433;
    border: 1px solid #5c438c;
    border-radius: 6px;
    padding: 6px 10px;
    color: #ffffff;
    font-size: 13px;
}
QComboBox:hover, QLineEdit:hover {
    border-color: #8c62d9;
}
QComboBox:focus, QLineEdit:focus {
    border-color: #ffd700;
}
QComboBox::drop-down {
    border: none;
    width: 20px;
}
QPushButton {
    background-color: #4a287a;
    color: #ffffff;
    border: 1px solid #794bb8;
    border-radius: 6px;
    padding: 8px 18px;
    font-weight: bold;
    font-size: 13px;
}
QPushButton:hover {
    background-color: #6336a1;
    border-color: #ffd700;
}
QPushButton:pressed {
    background-color: #381b5e;
}
QPushButton#saveBtn {
    background-color: #8c62d9;
    color: #ffffff;
    border: 1px solid #ffd700;
    font-size: 14px;
    padding: 10px 24px;
}
QPushButton#saveBtn:hover {
    background-color: #9d73eb;
}
QProgressBar {
    border: 1px solid #4a3475;
    border-radius: 6px;
    text-align: center;
    background-color: #1f1433;
    color: white;
}
QProgressBar::chunk {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4a287a, stop:1 #ffd700);
    border-radius: 5px;
}
QCheckBox {
    color: #c9b6e4;
    font-size: 13px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid #5c438c;
    background-color: #1f1433;
}
QCheckBox::indicator:checked {
    background-color: #ffd700;
    border-color: #ffd700;
}
"""

class SettingsSignalBridge(QObject):
    mic_level_changed = Signal(int)

class AzuraSettingsDialog(QDialog):
    """Graphical setup and settings dialog for audio devices, Chatterbox host/port, and LLM configs."""

    def __init__(self, config_path: str = "config.json", parent=None):
        super().__init__(parent)
        self.config_path = config_path
        self.config = {}
        self.mic_stream = None
        self.sig_bridge = SettingsSignalBridge()

        self.setWindowTitle("Lady Azura Companion - Configuration & Settings")
        self.resize(540, 680)
        self.setStyleSheet(DARK_TWILIGHT_STYLE)

        self._load_config()
        self._init_ui()
        self.sig_bridge.mic_level_changed.connect(self.vu_bar.setValue)
        self._populate_audio_devices()

    def _load_config(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
            except Exception as e:
                logger.error(f"Error reading config file {self.config_path}: {e}")

        llm_cfg = self.config.get("llm", {})
        self._provider_keys = dict(llm_cfg.get("keys", {}))
        self._provider_urls = dict(llm_cfg.get("urls", {}))
        self._provider_models = dict(llm_cfg.get("models", {}))

        # Backwards compatibility fallbacks
        if "gemini" not in self._provider_keys:
            self._provider_keys["gemini"] = llm_cfg.get("gemini_api_key") or llm_cfg.get("api_key") or ""
        if "openai" not in self._provider_keys and llm_cfg.get("provider") == "openai":
            self._provider_keys["openai"] = llm_cfg.get("api_key") or ""

        if "gemini" not in self._provider_models:
            self._provider_models["gemini"] = llm_cfg.get("gemini_model") or llm_cfg.get("model") or "gemini-3.5-flash"
        if "openai" not in self._provider_models:
            self._provider_models["openai"] = llm_cfg.get("model") or "gpt-4o"
        if "ollama" not in self._provider_models:
            self._provider_models["ollama"] = llm_cfg.get("model") or "llama3.2:3b"

        if "gemini" not in self._provider_urls:
            self._provider_urls["gemini"] = ""
        if "openai" not in self._provider_urls:
            self._provider_urls["openai"] = "https://api.openai.com/v1"
        if "ollama" not in self._provider_urls:
            self._provider_urls["ollama"] = llm_cfg.get("ollama_url") or "http://localhost:11434"

        self._active_provider = llm_cfg.get("provider", "gemini")

    def _init_ui(self):
        main_layout = QVBoxLayout(self)

        # Header Title
        title_label = QLabel("✦ L A D Y   A Z U R A   S E T T I N G S ✦")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title_label.setStyleSheet("color: #ffd700; margin-bottom: 4px;")
        main_layout.addWidget(title_label)

        sub_label = QLabel("Configure hardware devices, Chatterbox TTS server host, and LLM engines.")
        sub_label.setAlignment(Qt.AlignCenter)
        sub_label.setStyleSheet("color: #9d8db8; font-size: 12px; margin-bottom: 12px;")
        main_layout.addWidget(sub_label)

        # 1. Audio Devices Group Box
        audio_box = QGroupBox("Audio Devices Setup")
        audio_layout = QGridLayout(audio_box)

        audio_layout.addWidget(QLabel("Microphone (Audio In):"), 0, 0)
        self.input_combo = QComboBox()
        audio_layout.addWidget(self.input_combo, 0, 1)

        audio_layout.addWidget(QLabel("Speakers (Audio Out):"), 1, 0)
        self.output_combo = QComboBox()
        audio_layout.addWidget(self.output_combo, 1, 1)

        # Mic Test / VU Meter
        audio_layout.addWidget(QLabel("Live Microphone Test:"), 2, 0)
        self.vu_bar = QProgressBar()
        self.vu_bar.setRange(0, 100)
        self.vu_bar.setValue(0)
        audio_layout.addWidget(self.vu_bar, 2, 1)

        self.test_mic_btn = QPushButton("Test Microphone")
        self.test_mic_btn.setCheckable(True)
        self.test_mic_btn.toggled.connect(self._toggle_mic_test)
        audio_layout.addWidget(self.test_mic_btn, 3, 1, Qt.AlignRight)

        main_layout.addWidget(audio_box)

        # 2. Chatterbox TTS Server Group Box
        tts_box = QGroupBox("Chatterbox TTS Server Settings")
        tts_layout = QGridLayout(tts_box)

        chatterbox_cfg = self.config.get("chatterbox", {})
        host_val = chatterbox_cfg.get("host", "localhost")
        port_val = str(chatterbox_cfg.get("port", 8030))

        tts_layout.addWidget(QLabel("Chatterbox Host:"), 0, 0)
        self.host_edit = QLineEdit(host_val)
        self.host_edit.setPlaceholderText("localhost or LAN IP (e.g. 192.168.1.50)")
        tts_layout.addWidget(self.host_edit, 0, 1)

        tts_layout.addWidget(QLabel("Chatterbox Port:"), 1, 0)
        self.port_edit = QLineEdit(port_val)
        self.port_edit.setPlaceholderText("8030")
        tts_layout.addWidget(self.port_edit, 1, 1)

        mw_path_val = self.config.get("morrowind_path", "")
        tts_layout.addWidget(QLabel("Morrowind Directory:"), 2, 0)
        mw_layout = QHBoxLayout()
        self.mw_path_edit = QLineEdit(mw_path_val)
        self.mw_path_edit.setPlaceholderText("Path to Morrowind installation (e.g. /home/.../Morrowind)")
        mw_layout.addWidget(self.mw_path_edit)

        self.browse_mw_btn = QPushButton("Browse...")
        self.browse_mw_btn.clicked.connect(self._browse_morrowind_dir)
        mw_layout.addWidget(self.browse_mw_btn)

        self.extract_voice_btn = QPushButton("Extract Voice Sample")
        self.extract_voice_btn.setToolTip("Locates mw_cavern.bik in Morrowind Data Files/Video and extracts PCM WAV for Chatterbox voice cloning")
        self.extract_voice_btn.clicked.connect(self._extract_game_voice_sample)
        mw_layout.addWidget(self.extract_voice_btn)

        tts_layout.addLayout(mw_layout, 2, 1)

        self.manage_docker_cb = QCheckBox("Auto-manage local Chatterbox Docker container on startup/exit")
        self.manage_docker_cb.setChecked(chatterbox_cfg.get("manage_docker", True))
        tts_layout.addWidget(self.manage_docker_cb, 3, 0, 1, 2)

        vram_lbl = QLabel("💡 VRAM Footprint: Chatterbox TTS uses ~1.8 – 2.0 GB VRAM on GPU during voice synthesis.")
        vram_lbl.setStyleSheet("color: #a08dc0; font-size: 11px; font-style: italic;")
        tts_layout.addWidget(vram_lbl, 4, 0, 1, 2)

        main_layout.addWidget(tts_box)

        # 3. Whisper Speech Recognition Group Box
        whisper_box = QGroupBox("Whisper Speech Recognition Settings (Local STT)")
        whisper_layout = QGridLayout(whisper_box)

        whisper_layout.addWidget(QLabel("Whisper STT Model:"), 0, 0)
        self.whisper_combo = QComboBox()
        self.whisper_combo.addItems(["small.en", "base.en", "tiny.en", "medium.en", "turbo"])
        current_whisper = self.config.get("audio", {}).get("whisper_model", "small.en")
        idx = self.whisper_combo.findText(current_whisper)
        if idx >= 0:
            self.whisper_combo.setCurrentIndex(idx)
        whisper_layout.addWidget(self.whisper_combo, 0, 1)

        main_layout.addWidget(whisper_box)

        # 4. LLM Engine Group Box
        llm_box = QGroupBox("LLM Engine Settings")
        llm_layout = QGridLayout(llm_box)

        llm_cfg = self.config.get("llm", {})
        provider_val = llm_cfg.get("provider", "gemini")
        api_url_val = llm_cfg.get("api_url", "")
        if not api_url_val and provider_val == "ollama":
            api_url_val = llm_cfg.get("ollama_url", "http://localhost:11434")

        api_key_val = llm_cfg.get("api_key") or llm_cfg.get("gemini_api_key", "")
        model_val = llm_cfg.get("model") or llm_cfg.get("gemini_model", "gemini-3.5-flash")

        llm_layout.addWidget(QLabel("LLM Provider:"), 0, 0)
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(["gemini", "openai", "ollama", "custom"])
        p_idx = self.provider_combo.findText(provider_val)
        if p_idx >= 0:
            self.provider_combo.setCurrentIndex(p_idx)
        llm_layout.addWidget(self.provider_combo, 0, 1)

        llm_layout.addWidget(QLabel("API Base URL:"), 1, 0)
        self.api_url_edit = QLineEdit(api_url_val)
        self.api_url_edit.setPlaceholderText("(Optional for Gemini) or http://localhost:11434")
        llm_layout.addWidget(self.api_url_edit, 1, 1)

        llm_layout.addWidget(QLabel("API Key:"), 2, 0)
        self.api_key_edit = QLineEdit(api_key_val)
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.api_key_edit.setPlaceholderText("Enter API Key (Gemini, OpenAI, etc.)")
        llm_layout.addWidget(self.api_key_edit, 2, 1)

        self.api_key_note = QLabel("⚠️ Note: Gemini free API keys (from Google AI Studio) can hit rate limits or quota caps after just 2–3 queries. For unlimited usage, local Ollama or a paid key is recommended.")
        self.api_key_note.setStyleSheet("color: #d4a755; font-size: 11px; font-style: italic;")
        self.api_key_note.setWordWrap(True)
        llm_layout.addWidget(self.api_key_note, 3, 1)

        llm_layout.addWidget(QLabel("Model Name:"), 4, 0)
        self.model_combo = QComboBox()
        llm_layout.addWidget(self.model_combo, 4, 1)

        self.provider_combo.currentTextChanged.connect(self._on_provider_changed)
        self.api_url_edit.editingFinished.connect(lambda: self._populate_model_options(self.provider_combo.currentText(), self.api_url_edit.text().strip(), self.api_key_edit.text().strip()))
        self.api_key_edit.editingFinished.connect(lambda: self._populate_model_options(self.provider_combo.currentText(), self.api_url_edit.text().strip(), self.api_key_edit.text().strip()))
        self._on_provider_changed(provider_val)
        if model_val:
            m_idx = self.model_combo.findText(model_val)
            if m_idx >= 0:
                self.model_combo.setCurrentIndex(m_idx)

        main_layout.addWidget(llm_box)

        # 4. Data Sources & Content Packs Group Box
        ds_box = QGroupBox("Data Sources & Content Packs")
        ds_layout = QVBoxLayout(ds_box)

        ds_cfg = self.config.get("data_sources", {})

        self.cb_mw = QCheckBox("Morrowind Base Game (Required)")
        self.cb_mw.setChecked(True)
        self.cb_mw.setEnabled(False)
        ds_layout.addWidget(self.cb_mw)

        self.cb_goty = QCheckBox("GOTY Expansions (Tribunal & Bloodmoon)")
        self.cb_goty.setChecked(ds_cfg.get("goty", True))
        ds_layout.addWidget(self.cb_goty)

        self.cb_tr = QCheckBox("Tamriel Rebuilt (Mainland & Poison Song)")
        self.cb_tr.setChecked(ds_cfg.get("tamriel_rebuilt", True))
        ds_layout.addWidget(self.cb_tr)

        main_layout.addWidget(ds_box)

        # Save / Cancel Buttons
        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Save Settings")
        save_btn.setObjectName("saveBtn")
        save_btn.clicked.connect(self._save_settings)
        btn_layout.addWidget(save_btn)

        main_layout.addLayout(btn_layout)

    def _on_provider_changed(self, new_provider: str):
        # 1. Save currently displayed fields into active provider memory before switching
        if hasattr(self, "_active_provider") and self._active_provider:
            old_p = self._active_provider
            if hasattr(self, "api_key_edit"):
                self._provider_keys[old_p] = self.api_key_edit.text().strip()
            if hasattr(self, "api_url_edit"):
                self._provider_urls[old_p] = self.api_url_edit.text().strip()
            if hasattr(self, "model_combo"):
                self._provider_models[old_p] = self.model_combo.currentText().strip()

        self._active_provider = new_provider

        # 2. Retrieve new provider's saved values
        new_url = self._provider_urls.get(new_provider, "")
        if not new_url:
            if new_provider == "ollama":
                new_url = "http://localhost:11434"
            elif new_provider == "openai":
                new_url = "https://api.openai.com/v1"
            elif new_provider == "gemini":
                new_url = ""

        new_key = self._provider_keys.get(new_provider, "")
        new_model = self._provider_models.get(new_provider, "")

        if hasattr(self, "api_url_edit"):
            self.api_url_edit.setText(new_url)
            if new_provider == "gemini":
                self.api_url_edit.setPlaceholderText("(Optional for Gemini)")
            elif new_provider == "ollama":
                self.api_url_edit.setPlaceholderText("http://localhost:11434")
            elif new_provider == "openai":
                self.api_url_edit.setPlaceholderText("https://api.openai.com/v1")
            else:
                self.api_url_edit.setPlaceholderText("http://localhost:8000/v1")

        if hasattr(self, "api_key_edit"):
            self.api_key_edit.setText(new_key)
            self.api_key_edit.setPlaceholderText(f"Enter {new_provider.title()} API Key")

        self._populate_model_options(new_provider, new_url, target_model=new_model)

    def _populate_model_options(self, provider: str, api_url: str, target_model: str = "", api_key: str = ""):
        if not hasattr(self, "model_combo"):
            return
        curr_text = target_model or self.model_combo.currentText().strip()
        self.model_combo.clear()

        key = api_key or (self.api_key_edit.text().strip() if hasattr(self, "api_key_edit") else "")
        if not key:
            key = self._provider_keys.get(provider, "")

        fetched = self._fetch_models_for_provider(provider, api_url, key)

        models = []
        if fetched:
            models = fetched

        # Curated defaults fallback if live query yields no items
        fallback_defaults = {
            "gemini": ["gemini-3.5-flash", "gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-pro", "gemini-1.5-flash"],
            "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o3-mini"],
            "ollama": ["llama3.2:3b", "llama3:latest", "mistral", "phi3", "gemma2"],
            "custom": ["openrouter/auto", "mistralai/mistral-7b-instruct", "meta-llama/llama-3-8b-instruct"]
        }

        for m in fallback_defaults.get(provider, []):
            if m not in models:
                models.append(m)

        if curr_text and curr_text not in models:
            models.insert(0, curr_text)

        self.model_combo.addItems(models)
        if curr_text:
            idx = self.model_combo.findText(curr_text)
            if idx >= 0:
                self.model_combo.setCurrentIndex(idx)

    def _fetch_models_for_provider(self, provider: str, api_url: str, api_key: str) -> list:
        import urllib.request
        import json

        models = []
        try:
            if provider == "gemini" and api_key:
                url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
                req = urllib.request.Request(url, headers={'User-Agent': 'HeyAzura/1.0'})
                with urllib.request.urlopen(req, timeout=2.0) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode('utf-8'))
                        for m in data.get('models', []):
                            name = m.get('name', '').replace('models/', '')
                            methods = m.get('supportedGenerationMethods', [])
                            if "generateContent" not in methods:
                                continue
                            if any(bad in name.lower() for bad in ["embedding", "bison", "aqa", "tuning", "imagen", "veo"]):
                                continue
                            if name and 'gemini' in name.lower():
                                models.append(name)
            elif provider == "ollama":
                base_url = (api_url or "http://localhost:11434").rstrip("/")
                url = f"{base_url}/api/tags"
                req = urllib.request.Request(url, headers={'User-Agent': 'HeyAzura/1.0'})
                with urllib.request.urlopen(req, timeout=2.0) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode('utf-8'))
                        models = [m['name'] for m in data.get('models', []) if 'name' in m]
            elif provider in ["openai", "custom"]:
                base_url = (api_url or ("https://api.openai.com/v1" if provider == "openai" else "http://localhost:8000/v1")).rstrip("/")
                if not base_url.endswith("/v1") and provider == "openai":
                    base_url += "/v1"
                url = f"{base_url}/models"
                headers = {'User-Agent': 'HeyAzura/1.0'}
                if api_key:
                    headers['Authorization'] = f"Bearer {api_key}"
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=2.0) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode('utf-8'))
                        for m in data.get('data', []):
                            if isinstance(m, dict) and 'id' in m:
                                models.append(m['id'])
        except Exception as e:
            logger.debug(f"Failed to fetch live models for {provider}: {e}")

        return models

    def _populate_audio_devices(self):
        """Populate comboboxes with available sounddevice input/output devices."""
        self.input_combo.clear()
        self.output_combo.clear()

        devices = sd.query_devices()
        default_in, default_out = sd.default.device

        cfg_audio = self.config.get("audio", {})
        cfg_in = cfg_audio.get("input_device_index")
        cfg_out = cfg_audio.get("output_device_index")

        in_selected_idx = 0
        out_selected_idx = 0

        for idx, d in enumerate(devices):
            if d['max_input_channels'] > 0:
                name = f"[{idx}] {d['name']}"
                self.input_combo.addItem(name, userData=idx)
                if (cfg_in is not None and idx == cfg_in) or (cfg_in is None and idx == default_in):
                    in_selected_idx = self.input_combo.count() - 1

            if d['max_output_channels'] > 0:
                name = f"[{idx}] {d['name']}"
                self.output_combo.addItem(name, userData=idx)
                if (cfg_out is not None and idx == cfg_out) or (cfg_out is None and idx == default_out):
                    out_selected_idx = self.output_combo.count() - 1

        self.input_combo.setCurrentIndex(in_selected_idx)
        self.output_combo.setCurrentIndex(out_selected_idx)

    def _toggle_mic_test(self, checked: bool):
        if checked:
            idx = self.input_combo.currentData()
            try:
                def audio_cb(indata, frames, time_info, status):
                    rms = float(np.sqrt(np.mean(indata ** 2)))
                    val = int(min(100, max(0, rms * 500.0)))
                    self.sig_bridge.mic_level_changed.emit(val)

                self.mic_stream = sd.InputStream(
                    samplerate=16000,
                    channels=1,
                    device=idx,
                    callback=audio_cb,
                    blocksize=1600
                )
                self.mic_stream.start()
                self.test_mic_btn.setText("Stop Test")
            except Exception as e:
                logger.error(f"Mic test error: {e}")
                QMessageBox.warning(self, "Audio Error", f"Failed to open input device: {e}")
                self.test_mic_btn.setChecked(False)
        else:
            if self.mic_stream:
                try:
                    self.mic_stream.stop()
                    self.mic_stream.close()
                except Exception:
                    pass
                self.mic_stream = None
            self.vu_bar.setValue(0)
            self.test_mic_btn.setText("Test Microphone")

    def _browse_morrowind_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Morrowind Installation Directory")
        if dir_path:
            self.mw_path_edit.setText(dir_path)

    def _extract_game_voice_sample(self):
        mw_dir = self.mw_path_edit.text().strip()
        if not mw_dir or not os.path.exists(mw_dir):
            QMessageBox.warning(self, "Morrowind Directory Invalid", "Please select a valid Morrowind installation directory.")
            return

        bik_paths = find_all_morrowind_videos(mw_dir)
        if not bik_paths:
            QMessageBox.warning(self, "Video Files Not Found", f"Could not locate 'mw_cavern.bik', 'mw_intro.bik', or 'mw_end.bik' in '{mw_dir}'.")
            return

        out_wav = os.path.join("azura_voice_samples", "azura_cavern_15s.wav")
        ok, msg = extract_azura_voice_from_biks(bik_paths, out_wav, duration_per_file=10.0)
        if not ok:
            QMessageBox.critical(self, "Voice Extraction Failed", msg)
            return

        # Upload to Chatterbox server if available
        c_host = self.host_edit.text().strip() or "localhost"
        c_port = self.port_edit.text().strip() or "8030"
        c_url = f"http://{c_host}:{c_port}"
        up_ok, up_msg = upload_voice_sample_to_chatterbox(c_url, out_wav)
        
        info_msg = f"{msg}\n\n{up_msg}" if up_ok else f"{msg}\n\nNote: {up_msg}"
        QMessageBox.information(self, "Voice Extraction Complete", info_msg)

    def _save_settings(self):
        """Write selected settings back to config.json."""
        if self.mic_stream:
            try:
                self.mic_stream.stop()
                self.mic_stream.close()
            except Exception:
                pass

        in_idx = self.input_combo.currentData()
        out_idx = self.output_combo.currentData()

        # Update Morrowind Path
        self.config["morrowind_path"] = self.mw_path_edit.text().strip()

        # Update Audio config
        audio_cfg = self.config.setdefault("audio", {})
        audio_cfg["input_device_index"] = in_idx
        audio_cfg["output_device_index"] = out_idx
        audio_cfg["whisper_model"] = self.whisper_combo.currentText()

        # Update Chatterbox config
        chatterbox_cfg = self.config.setdefault("chatterbox", {})
        host_str = self.host_edit.text().strip() or "localhost"
        try:
            port_num = int(self.port_edit.text().strip() or "8030")
        except ValueError:
            port_num = 8030

        chatterbox_cfg["host"] = host_str
        chatterbox_cfg["port"] = port_num
        chatterbox_cfg["url"] = f"http://{host_str}:{port_num}"
        chatterbox_cfg["manage_docker"] = self.manage_docker_cb.isChecked()

        # Update LLM config
        llm_cfg = self.config.setdefault("llm", {})
        prov = self.provider_combo.currentText()
        llm_cfg["provider"] = prov

        # Save currently displayed values into dict memory
        self._provider_keys[prov] = self.api_key_edit.text().strip()
        self._provider_urls[prov] = self.api_url_edit.text().strip()
        self._provider_models[prov] = self.model_combo.currentText().strip()

        llm_cfg["keys"] = self._provider_keys
        llm_cfg["urls"] = self._provider_urls
        llm_cfg["models"] = self._provider_models

        # Active top-level attributes for backwards compatibility
        llm_cfg["api_key"] = self._provider_keys.get(prov, "")
        llm_cfg["api_url"] = self._provider_urls.get(prov, "")
        llm_cfg["model"] = self._provider_models.get(prov, "")
        llm_cfg["gemini_api_key"] = self._provider_keys.get("gemini", "")
        llm_cfg["gemini_model"] = self._provider_models.get("gemini", "gemini-3.5-flash")

        # Update Data Sources config
        ds_cfg = self.config.setdefault("data_sources", {})
        ds_cfg["morrowind"] = True
        ds_cfg["goty"] = self.cb_goty.isChecked()
        ds_cfg["tamriel_rebuilt"] = self.cb_tr.isChecked()

        # Save file
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2)
            QMessageBox.information(self, "Settings Saved", "Settings saved and applied successfully!")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error Saving Config", f"Failed to save {self.config_path}: {e}")

    def closeEvent(self, event):
        if self.mic_stream:
            try:
                self.mic_stream.stop()
                self.mic_stream.close()
            except Exception:
                pass
        super().closeEvent(event)

def show_settings_dialog(config_path: str = "config.json") -> bool:
    """Helper to launch PySide6 settings GUI app."""
    app = QApplication.instance()
    owns_app = False
    if app is None:
        app = QApplication(sys.argv)
        owns_app = True

    dialog = AzuraSettingsDialog(config_path=config_path)
    res = dialog.exec()
    return res == QDialog.Accepted

if __name__ == "__main__":
    show_settings_dialog("config.json")
