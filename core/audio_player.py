import io
import logging
import threading
import numpy as np
import soundfile as sf
import sounddevice as sd
from typing import Optional

logger = logging.getLogger(__name__)

class AudioPlayer:
    """In-process audio playback engine with a persistent OutputStream for PipeWire stability."""

    def __init__(self, device_index: Optional[int] = None, sample_rate: int = 24000):
        self.device_index = device_index
        self.sample_rate = sample_rate
        self._buffer = np.array([], dtype=np.float32)
        self._lock = threading.Lock()
        
        # Start persistent stream so PipeWire node stays permanently connected
        try:
            self.stream = sd.OutputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                device=self.device_index,
                callback=self._audio_callback
            )
            self.stream.start()
            logger.info("AudioPlayer persistent OutputStream started.")
        except Exception as e:
            logger.error(f"Failed to start persistent OutputStream: {e}")
            self.stream = None

    def _audio_callback(self, outdata, frames, time_info, status):
        if status:
            logger.debug(f"AudioPlayer stream status: {status}")
        
        needed = frames
        with self._lock:
            buf_len = len(self._buffer)
            if buf_len > 0:
                take = min(needed, buf_len)
                outdata[:take, 0] = self._buffer[:take]
                self._buffer = self._buffer[take:]
                if take < needed:
                    outdata[take:, 0] = 0
            else:
                outdata.fill(0)

    @property
    def is_playing(self) -> bool:
        with self._lock:
            return len(self._buffer) > 0

    def stop(self):
        """Immediately stop currently playing audio (barge-in / interrupt)."""
        with self._lock:
            self._buffer = np.array([], dtype=np.float32)

    def play_bytes(self, audio_bytes: bytes, blocking: bool = False):
        """Queue WAV audio bytes for playback through persistent stream."""
        try:
            data, fs = sf.read(io.BytesIO(audio_bytes), dtype="float32")
            if data.ndim > 1:
                data = data.mean(axis=1)
            
            # Resample if sample_rate differs from stream
            if fs != self.sample_rate:
                from scipy import signal
                num_samples = int(len(data) * self.sample_rate / fs)
                data = signal.resample(data, num_samples).astype(np.float32)
            
            with self._lock:
                # Add to buffer in exact contiguous chronological order
                self._buffer = np.append(self._buffer, data)
                
            if blocking:
                while self.is_playing:
                    sd.sleep(50)
                    
        except Exception as e:
            logger.error(f"Failed to queue audio bytes for playback: {e}")

    def play_file(self, file_path: str, blocking: bool = False):
        """Play WAV audio file."""
        try:
            with open(file_path, "rb") as f:
                self.play_bytes(f.read(), blocking=blocking)
        except Exception as e:
            logger.error(f"Failed to read audio file '{file_path}': {e}")
