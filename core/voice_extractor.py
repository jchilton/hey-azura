import os
import shutil
import subprocess
import logging
import requests
from pathlib import Path
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

def find_morrowind_video(morrowind_path: str) -> Optional[str]:
    """Search given Morrowind path for Azura BIK cinematic files."""
    if not morrowind_path or not os.path.exists(morrowind_path):
        return None
    
    candidates = [
        os.path.join(morrowind_path, "Data Files", "Video", "mw_cavern.bik"),
        os.path.join(morrowind_path, "Data Files", "Video", "mw_intro.bik"),
        os.path.join(morrowind_path, "Video", "mw_cavern.bik"),
        os.path.join(morrowind_path, "mw_cavern.bik"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None

def extract_azura_voice_from_bik(bik_path: str, output_wav_path: str, duration_sec: float = 15.0) -> Tuple[bool, str]:
    """Use ffmpeg to extract a 15-second mono PCM WAV sample from a Morrowind .bik file."""
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        return False, "ffmpeg binary not found in system PATH. Please install ffmpeg."

    try:
        Path(output_wav_path).parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            ffmpeg_bin, "-y",
            "-i", bik_path,
            "-ss", "00:00:01",
            "-t", str(duration_sec),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "22050",
            "-ac", "1",
            output_wav_path
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if res.returncode == 0 and os.path.exists(output_wav_path) and os.path.getsize(output_wav_path) > 1000:
            return True, f"Successfully extracted sample to {output_wav_path}"
        else:
            return False, f"ffmpeg extraction failed: {res.stderr}"
    except Exception as e:
        return False, f"Error running ffmpeg: {e}"

def upload_voice_sample_to_chatterbox(chatterbox_url: str, wav_path: str) -> Tuple[bool, str]:
    """Upload extracted .wav sample to Chatterbox TTS /upload_reference endpoint."""
    if not os.path.exists(wav_path):
        return False, f"Voice sample file not found at {wav_path}"

    filename = os.path.basename(wav_path)
    url = f"{chatterbox_url.rstrip('/')}/upload_reference"

    try:
        with open(wav_path, "rb") as f:
            files = {"files": (filename, f, "audio/wav")}
            res = requests.post(url, files=files, timeout=10)
            if res.status_code == 200:
                return True, f"Successfully uploaded '{filename}' to Chatterbox server."
            else:
                return False, f"Chatterbox upload failed (HTTP {res.status_code}): {res.text}"
    except Exception as e:
        return False, f"Error connecting to Chatterbox at {url}: {e}"
