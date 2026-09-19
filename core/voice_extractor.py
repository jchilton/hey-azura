import os
import shutil
import subprocess
import logging
import requests
from pathlib import Path
from typing import Tuple, Optional, List

logger = logging.getLogger(__name__)

def find_all_morrowind_videos(morrowind_path: str) -> List[str]:
    """Search given Morrowind path for all available Azura BIK cinematic files (mw_cavern, mw_intro, mw_end)."""
    if not morrowind_path or not os.path.exists(morrowind_path):
        return []
    
    possible_dirs = [
        os.path.join(morrowind_path, "Data Files", "Video"),
        os.path.join(morrowind_path, "Video"),
        morrowind_path
    ]
    target_names = ["mw_cavern.bik", "mw_intro.bik", "mw_end.bik"]
    found = []

    for d in possible_dirs:
        if os.path.exists(d):
            for name in target_names:
                p = os.path.join(d, name)
                if os.path.exists(p) and p not in found:
                    found.append(p)
    return found

def find_morrowind_video(morrowind_path: str) -> Optional[str]:
    """Backwards compatible single-file finder."""
    vids = find_all_morrowind_videos(morrowind_path)
    return vids[0] if vids else None

def extract_azura_voice_from_bik(bik_path: str, output_wav_path: str, duration_sec: float = 15.0) -> Tuple[bool, str]:
    """Extract voice sample from a single BIK file."""
    return extract_azura_voice_from_biks([bik_path], output_wav_path, duration_per_file=duration_sec)

def get_ffmpeg_path() -> Optional[str]:
    """Find ffmpeg binary cross-platform (Linux, macOS, and Windows)."""
    bin_path = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if bin_path:
        return bin_path

    app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    local_candidates = [
        os.path.join(app_dir, "ffmpeg.exe"),
        os.path.join(app_dir, "ffmpeg", "bin", "ffmpeg.exe"),
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
    ]
    for c in local_candidates:
        if os.path.exists(c):
            return c
    return None

def extract_azura_voice_from_biks(bik_paths: List[str], output_wav_path: str, duration_per_file: float = 10.0) -> Tuple[bool, str]:
    """Use ffmpeg to extract and concatenate samples from all found Morrowind cutscenes into a single high-quality reference audio track."""
    ffmpeg_bin = get_ffmpeg_path()
    if not ffmpeg_bin:
        return False, "ffmpeg binary not found in system PATH or app folder. Please install ffmpeg or place ffmpeg.exe in the app folder."

    if not bik_paths:
        return False, "No Morrowind BIK video files provided."

    try:
        Path(output_wav_path).parent.mkdir(parents=True, exist_ok=True)
        
        cmd = [ffmpeg_bin, "-y"]
        for bp in bik_paths:
            cmd.extend(["-ss", "00:00:01", "-t", str(duration_per_file), "-i", bp])

        if len(bik_paths) > 1:
            filter_str = "".join(f"[{i}:a]" for i in range(len(bik_paths))) + f"concat=n={len(bik_paths)}:v=0:a=1[a]"
            cmd.extend([
                "-filter_complex", filter_str,
                "-map", "[a]"
            ])
        else:
            cmd.extend(["-vn"])

        cmd.extend([
            "-acodec", "pcm_s16le",
            "-ar", "22050",
            "-ac", "1",
            output_wav_path
        ])

        res = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        if res.returncode == 0 and os.path.exists(output_wav_path) and os.path.getsize(output_wav_path) > 1000:
            count_str = f"{len(bik_paths)} cutscene(s): {', '.join([os.path.basename(p) for p in bik_paths])}"
            return True, f"Successfully extracted & merged voice samples from {count_str}."
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
