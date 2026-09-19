import requests
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class ChatterboxTTSClient:
    """Client for Chatterbox TTS Server running locally."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        chatterbox_cfg = cfg.get("chatterbox", {})
        self.host = chatterbox_cfg.get("host")
        if self.host:
            self.port = chatterbox_cfg.get("port", 8030)
            self.base_url = f"http://{self.host}:{self.port}".rstrip("/")
        else:
            self.base_url = chatterbox_cfg.get("url", "http://localhost:8030").rstrip("/")
            from urllib.parse import urlparse
            p = urlparse(self.base_url)
            self.host = p.hostname or "localhost"
            self.port = p.port or 8030
        self.endpoint = chatterbox_cfg.get("endpoint", "/tts")
        self.voice_mode = chatterbox_cfg.get("voice_mode", "clone")
        self.reference_audio = chatterbox_cfg.get("reference_audio", "azura_cavern_15s.wav")
        self.output_format = chatterbox_cfg.get("output_format", "wav")
        self.temperature = chatterbox_cfg.get("temperature", 0.7)
        self.exaggeration = chatterbox_cfg.get("exaggeration", 1.0)
        self.speed_factor = chatterbox_cfg.get("speed_factor", 1.0)
        self.timeout = chatterbox_cfg.get("timeout_sec", 30)

    @property
    def tts_url(self) -> str:
        return f"{self.base_url}{self.endpoint}"

    def is_healthy(self) -> bool:
        """Check if Chatterbox server is up and responsive."""
        try:
            r = requests.get(f"{self.base_url}/get_reference_files", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def get_available_reference_audio(self) -> list[str]:
        """Fetch list of reference audio files available on the server."""
        try:
            r = requests.get(f"{self.base_url}/get_reference_files", timeout=4)
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            logger.warning(f"Failed to fetch reference audio files: {e}")
        return []

    def synthesize(self, text: str, output_path: Optional[str] = None) -> Optional[bytes]:
        """Synthesize text to audio using Azura voice clone."""
        clean_text = text.strip()
        if not clean_text:
            return None

        payload = {
            "text": clean_text,
            "voice_mode": self.voice_mode,
            "reference_audio_filename": self.reference_audio,
            "output_format": self.output_format,
            "temperature": self.temperature,
            "exaggeration": self.exaggeration,
            "speed_factor": self.speed_factor
        }

        try:
            response = requests.post(
                self.tts_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=self.timeout
            )

            if response.status_code == 200:
                audio_bytes = response.content
                # Sanity check that we got audio, not an error json masquerading as 200
                if len(audio_bytes) > 200:
                    if output_path:
                        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                        with open(output_path, "wb") as f:
                            f.write(audio_bytes)
                    return audio_bytes
                else:
                    logger.error(f"TTS returned tiny response ({len(audio_bytes)} bytes): {response.text}")
                    return None
            else:
                logger.error(f"Chatterbox TTS error HTTP {response.status_code}: {response.text}")
                return None
        except Exception as e:
            logger.error(f"TTS request failed: {e}")
            return None
