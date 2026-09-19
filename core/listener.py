import os
from pathlib import Path

# Redirect HuggingFace cache & XET log directory to prevent permission errors
hf_cache = Path.home() / ".cache" / "hf_azura"
os.environ["HF_HOME"] = str(hf_cache)
os.environ["XET_LOG_DIR"] = str(hf_cache / "xet_logs")
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
hf_cache.mkdir(parents=True, exist_ok=True)
(hf_cache / "xet_logs").mkdir(parents=True, exist_ok=True)

import time
import queue
import logging
import threading
import numpy as np
import sounddevice as sd
from collections import deque
from typing import Callable, Optional, List, Dict, Any
from faster_whisper import WhisperModel
from core.entity_resolver import EntityResolver

logger = logging.getLogger(__name__)

class AudioListener:
    """
    Continuous audio listener that detects 'Hey Azura', glows while listening to the query,
    and signals prompt completion for spinning/researching.
    Uses Adaptive Noise Floor Tracking and bounded Ring Buffers for 100% stability.
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        on_wake_started: Optional[Callable[[], None]] = None,
        on_wake_detected: Optional[Callable[[str], None]] = None,
        on_state_change: Optional[Callable[[str, float], None]] = None
    ):
        cfg = config or {}
        self.wake_words = [w.lower().strip() for w in cfg.get("wake_words", ["hey azura", "azura", "lady azura"])]
        
        # Initialize Phonetic Entity Resolver & Structured Domain Prompt
        self.entity_resolver = EntityResolver()
        vocab_names = self.entity_resolver.get_prompt_vocab_string()
        self.prompt_prefix = (
            "The following is a transcript of a player discussing The Elder Scrolls III: Morrowind, "
            "Bloodmoon, Tribunal, and Tamriel Rebuilt. Proper names and terms: " + vocab_names + "."
        )

        audio_cfg = cfg.get("audio", {})
        self.sample_rate = 16000  # Whisper requires 16000Hz
        self.manual_threshold = audio_cfg.get("mic_energy_threshold", None)
        self.energy_threshold = 8.0
        self.pause_threshold = audio_cfg.get("pause_threshold", 0.9)
        self.device_index = audio_cfg.get("input_device_index", None)
        self.beam_size = audio_cfg.get("beam_size", 5)
        
        self.on_wake_started = on_wake_started
        self.on_wake_detected = on_wake_detected
        self.on_state_change = on_state_change

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._audio_queue: queue.Queue = queue.Queue()
        self.in_active_session = False
        self.session_timestamp = 0.0
        self._wake_notified_for_current_speech = False
        self._whisper_lock = threading.Lock()
        
        # Load local whisper model (default: small.en)
        whisper_model_name = audio_cfg.get("whisper_model", "small.en")
        compute_type = audio_cfg.get("compute_type", "int8")
        logger.info(f"Loading local Whisper STT model '{whisper_model_name}'...")
        self.whisper = WhisperModel(whisper_model_name, device="cpu", compute_type=compute_type)
        logger.info("Whisper STT model loaded successfully.")

    def _notify_state(self, state: str, rms: float = 0.0):
        if self.on_state_change:
            try:
                self.on_state_change(state, rms)
            except Exception as e:
                logger.debug(f"Error in on_state_change callback: {e}")

    def _trigger_wake_started(self):
        """Notify that 'Hey Azura' was detected and we are actively waiting for/listening to the query."""
        if not self._wake_notified_for_current_speech:
            self._wake_notified_for_current_speech = True
            self.in_active_session = True
            self.session_timestamp = time.time()
            if self.on_wake_started:
                try:
                    self.on_wake_started()
                except Exception as e:
                    logger.error(f"Error in on_wake_started callback: {e}")

    def start(self):
        """Start continuous listening in background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        logger.info("AudioListener started.")

    def stop(self):
        """Stop listening."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.3)
        logger.info("AudioListener stopped.")

    def _audio_callback(self, indata, frames, time_info, status):
        """sounddevice audio stream input callback."""
        if status:
            logger.debug(f"Audio status: {status}")
        if self._running:
            self._audio_queue.put(indata.copy())

    def _is_wake_word_present(self, text: str) -> tuple[bool, str]:
        """Check if any wake word appears in text and return remaining query."""
        clean = text.lower().strip()
        clean_nopunct = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in clean)
        words = clean_nopunct.split()
        normalized_str = " ".join(words)

        for ww in self.wake_words:
            if ww in normalized_str:
                idx = normalized_str.find(ww)
                after = normalized_str[idx + len(ww):].strip()
                return True, after

        return False, ""

    def _listen_loop(self):
        """Continuous capture, adaptive noise floor tracking, and silence detection loop."""
        chunk_duration = 0.1  # 100ms per block
        block_size = int(self.sample_rate * chunk_duration)

        try:
            stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                blocksize=block_size,
                device=self.device_index,
                callback=self._audio_callback
            )
        except Exception as e:
            logger.error(f"Failed to open audio input stream: {e}")
            self._notify_state("ERROR", 0.0)
            return

        with stream:
            # 1. Ambient noise calibration phase (0.8s)
            self._notify_state("CALIBRATING", 0.0)
            calibration_rms_vals = []
            calib_start = time.time()
            while time.time() - calib_start < 0.8 and self._running:
                try:
                    chunk = self._audio_queue.get(timeout=0.1)
                    rms = float(np.sqrt(np.mean(chunk ** 2)) * 1000.0)
                    calibration_rms_vals.append(rms)
                except queue.Empty:
                    continue

            ambient_noise_floor = float(np.mean(calibration_rms_vals)) if calibration_rms_vals else 3.0
            ambient_noise_floor = max(2.0, ambient_noise_floor)
            logger.info(f"Calibrated mic: initial ambient noise floor = {ambient_noise_floor:.2f} RMS")

            self._notify_state("LISTENING", 0.0)
            
            # Ring buffer for audio chunks (max 150 blocks = 15 seconds)
            recorded_chunks: deque = deque(maxlen=150)
            is_speaking = False
            consecutive_voice_blocks = 0
            consecutive_silence_blocks = 0

            while self._running:
                # Active session timeout check (10s max waiting for user query after wake word)
                if self.in_active_session and time.time() - self.session_timestamp > 10.0:
                    self.in_active_session = False
                    logger.info("Active session timed out after 10s of inactivity.")
                    self._notify_state("LISTENING", 0.0)

                try:
                    chunk = self._audio_queue.get(timeout=0.15)
                except queue.Empty:
                    continue

                rms = float(np.sqrt(np.mean(chunk ** 2)) * 1000.0)

                # Dynamic speech trigger threshold based on ambient noise floor
                speech_threshold = max(6.0, ambient_noise_floor * 2.4)

                if not is_speaking:
                    # Update running noise floor slowly while not speaking
                    ambient_noise_floor = 0.97 * ambient_noise_floor + 0.03 * rms
                    
                    if rms >= speech_threshold:
                        consecutive_voice_blocks += 1
                        recorded_chunks.append(chunk)
                        # Require 2 consecutive voice blocks (200ms) to trigger speech start
                        if consecutive_voice_blocks >= 2:
                            is_speaking = True
                            consecutive_silence_blocks = 0
                            self._notify_state("HEARING_SPEECH", rms)
                    else:
                        consecutive_voice_blocks = 0
                        recorded_chunks.clear()
                        self._notify_state("LISTENING", rms)
                else:
                    # Currently in speaking mode
                    recorded_chunks.append(chunk)
                    
                    silence_cutoff = max(3.5, ambient_noise_floor * 1.5)
                    if rms <= silence_cutoff:
                        consecutive_silence_blocks += 1
                    else:
                        consecutive_silence_blocks = 0

                    # 7 consecutive silent blocks (0.7s) OR ring buffer full (15s) -> end utterance
                    if consecutive_silence_blocks >= 7 or len(recorded_chunks) >= 150:
                        is_speaking = False
                        consecutive_voice_blocks = 0
                        consecutive_silence_blocks = 0
                        self._notify_state("PROCESSING_AUDIO", rms)

                        if recorded_chunks:
                            audio_data = np.concatenate(list(recorded_chunks), axis=0).flatten()
                            recorded_chunks.clear()
                            self._process_utterance(audio_data)

                        self._wake_notified_for_current_speech = False
                        self._notify_state("LISTENING", 0.0)

    def _process_utterance(self, audio_data: np.ndarray):
        """Transcribe audio with Whisper and handle wake word and question."""
        if len(audio_data) < self.sample_rate * 0.5:
            return

        try:
            with self._whisper_lock:
                segments, _ = self.whisper.transcribe(
                    audio_data,
                    language="en",
                    beam_size=self.beam_size,
                    temperature=0.0,
                    condition_on_previous_text=True,
                    vad_filter=True,
                    initial_prompt=self.prompt_prefix
                )
                raw_transcription = " ".join(s.text for s in segments).strip()
            
            if not raw_transcription:
                return

            # Apply Phonetic Entity Resolution
            transcription, replacements = self.entity_resolver.resolve_entities(raw_transcription)

            logger.info(f"Heard utterance: '{raw_transcription}' -> Resolved: '{transcription}'")
            has_wake_word, query = self._is_wake_word_present(transcription)

            if has_wake_word:
                # If user spoke "Hey Azura [question]" in one breath:
                if query.strip():
                    # Query is complete!
                    logger.info(f"[Single-breath Query] '{query}'")
                    self.in_active_session = False
                    if self.on_wake_detected:
                        self.on_wake_detected(query)
                else:
                    # User only said "Hey Azura" and paused -> Wait for prompt while glowing!
                    logger.info("[Wake Word Triggered] Waiting for user prompt...")
                    self._trigger_wake_started()
            elif self.in_active_session:
                # We were waiting for the prompt and user just spoke it!
                logger.info(f"[Follow-up Query Received] '{transcription}'")
                self.in_active_session = False
                if self.on_wake_detected:
                    self.on_wake_detected(transcription)
            else:
                logger.debug(f"Ignored speech (no wake word, no active session): '{transcription}'")

        except Exception as e:
            logger.error(f"Error processing audio utterance: {e}")
