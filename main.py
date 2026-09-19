#!/usr/bin/env python3
"""
Morrowind Voice AI Companion ("Azura")
A dedicated voice-activated companion for playing The Elder Scrolls III: Morrowind,
Tamriel Rebuilt (Poison Song), and UMOPP.
"""

import sys
import os
import time
import argparse
import logging
import signal
from pathlib import Path

# Redirect Hugging Face cache to avoid root/permission conflicts & suppress unauthenticated warnings
hf_cache = Path.home() / ".cache" / "hf_azura"
os.environ["HF_HOME"] = str(hf_cache)
os.environ["XET_LOG_DIR"] = str(hf_cache / "xet_logs")
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
hf_cache.mkdir(parents=True, exist_ok=True)
(hf_cache / "xet_logs").mkdir(parents=True, exist_ok=True)

import sounddevice as sd

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.chatterbox_tts import ChatterboxTTSClient
from core.audio_player import AudioPlayer
from core.llm_azura import AzuraLLM
from core.listener import AudioListener
from core.chatterbox_manager import ChatterboxDockerManager
from ui.overlay_server import OverlayServer

# ANSI styling for Daedric Twilight theme
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_PURPLE = "\033[38;5;141m"
C_DARK_PURPLE = "\033[38;5;99m"
C_GOLD = "\033[38;5;220m"
C_CYAN = "\033[38;5;81m"
C_DIM = "\033[2m"
C_GREEN = "\033[32m"
C_RED = "\033[31m"
C_YELLOW = "\033[33m"

def print_banner():
    banner = f"""{C_DARK_PURPLE}
    .☆。• *₊°。 ✮°。   
  {C_PURPLE}✦ L A D Y   A Z U R A ✦{C_DARK_PURPLE}
    .☆。• *₊°。 ✮°。   
{C_GOLD}  The Elder Scrolls III: Morrowind Voice AI Companion{C_RESET}
{C_DIM}  Tamriel Rebuilt (Poison Song) • UMOPP • UESP Live Integration{C_RESET}
"""
    print(banner)

def list_devices():
    """Print all available audio input and output devices."""
    print(f"\n{C_GOLD}{C_BOLD}=== AVAILABLE AUDIO DEVICES ==={C_RESET}")
    devices = sd.query_devices()
    default_in, default_out = sd.default.device
    
    print(f"\n{C_CYAN}--- Input Devices (Microphones) ---{C_RESET}")
    for idx, d in enumerate(devices):
        if d['max_input_channels'] > 0:
            is_def = " [DEFAULT]" if idx == default_in else ""
            print(f"  [{idx:2d}] {d['name']}{C_GREEN}{is_def}{C_RESET}")

    print(f"\n{C_CYAN}--- Output Devices (Speakers / Headphones) ---{C_RESET}")
    for idx, d in enumerate(devices):
        if d['max_output_channels'] > 0:
            is_def = " [DEFAULT]" if idx == default_out else ""
            print(f"  [{idx:2d}] {d['name']}{C_GREEN}{is_def}{C_RESET}")
    print()

class AzuraCompanionApp:
    def __init__(self, config_path: str = "config.json", input_dev: int = None, output_dev: int = None):
        import json
        self.config_path = PROJECT_ROOT / config_path
        self.config = {}
        if self.config_path.exists():
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.config = json.load(f)

        if input_dev is not None:
            self.config.setdefault("audio", {})["input_device_index"] = input_dev
        if output_dev is not None:
            self.config.setdefault("audio", {})["output_device_index"] = output_dev

        out_idx = self.config.get("audio", {}).get("output_device_index")
        in_idx = self.config.get("audio", {}).get("input_device_index")

        print(f"{C_CYAN}Initializing Azura Companion engines...{C_RESET}")

        # Check and manage Chatterbox Docker Container
        self.docker_mgr = ChatterboxDockerManager(self.config)
        self.docker_mgr.ensure_started()
        
        # Initialize Subsystems
        self.tts = ChatterboxTTSClient(self.config)
        self.player = AudioPlayer(device_index=out_idx)
        self.llm = AzuraLLM(self.config)
        self.listener = None
        self._running = True

        # Check TTS Server health
        if self.tts.is_healthy():
            print(f"  [{C_GREEN}✓{C_RESET}] Chatterbox TTS Server: Connected ({self.tts.base_url})")
            refs = self.tts.get_available_reference_audio()
            if self.tts.reference_audio in refs:
                print(f"  [{C_GREEN}✓{C_RESET}] Azura Voice Clone Sample: {C_GOLD}{self.tts.reference_audio}{C_RESET}")
            else:
                print(f"  [{C_RED}!{C_RESET}] Voice sample '{self.tts.reference_audio}' not found in Chatterbox! Available: {refs}")
        else:
            print(f"  [{C_RED}✗{C_RESET}] Chatterbox TTS Server: Not responding at {self.tts.base_url}")

        # Check LLM Provider
        active_model = self.llm.gemini_model if self.llm.provider == "gemini" else self.llm.model
        print(f"  [{C_GREEN}✓{C_RESET}] LLM Provider: {C_PURPLE}{active_model} via {self.llm.provider}{C_RESET}")
        print(f"  [{C_GREEN}✓{C_RESET}] UESP Real-time MediaWiki API: Ready")
        
        # Overlay UI Server (for OBS / Browser floating window)
        overlay_port = self.config.get("ui", {}).get("overlay_port", 8035)
        self.overlay = OverlayServer(port=overlay_port)
        self.overlay.start()

        # Audio device info
        dev_in_name = sd.query_devices(in_idx)['name'] if in_idx is not None else sd.query_devices(sd.default.device[0])['name']
        dev_out_name = sd.query_devices(out_idx)['name'] if out_idx is not None else sd.query_devices(sd.default.device[1])['name']
        print(f"  [{C_GREEN}✓{C_RESET}] Audio In:  {C_DIM}{dev_in_name}{C_RESET}")
        print(f"  [{C_GREEN}✓{C_RESET}] Audio Out: {C_DIM}{dev_out_name}{C_RESET}")
        print(f"  [{C_GREEN}✓{C_RESET}] OBS / UI Overlay: {C_GOLD}http://localhost:{overlay_port}{C_RESET} {C_DIM}(Transparent Browser Source){C_RESET}")
        print()

    def handle_query(self, user_question: str):
        """Process question, query UESP+LLM, synthesize voice, and play."""
        if not user_question.strip():
            return

        # Stop any audio already playing
        self.player.stop()

        # Set overlay state: researching (STARTS SPINNING)
        self.overlay.set_state("researching")

        try:
            print(f"\n{C_CYAN}➤ Question:{C_RESET} {C_BOLD}{user_question}{C_RESET}")
            
            # Check for conversational memory reset command
            q_lower = user_question.lower().strip()
            if any(p in q_lower for p in ["forget everything", "clear memory", "clear history", "reset conversation", "start over"]):
                self.llm.clear_history()
                spoken_response = "The slate is wiped clean, Moon-and-Star. Ask anew, and I shall unveil the path."
                sources = []
                elapsed = 0.0
            else:
                print(f"{C_DIM}  Consulting the stars & UESP archives...{C_RESET}")
                start_t = time.time()
                spoken_response, sources = self.llm.query(user_question)
                elapsed = time.time() - start_t

            # 2. Display Azura's response
            print(f"\n{C_PURPLE}{C_BOLD}✦ Lady Azura:{C_RESET} {C_GOLD}\"{spoken_response}\"{C_RESET}")
            
            if sources:
                print(f"{C_DIM}  Sources consulted:{C_RESET}")
                for s in sources:
                    print(f"{C_DIM}   - {s['title']} ({s['url']}){C_RESET}")
            print(f"{C_DIM}  (Reasoning: {elapsed:.2f}s){C_RESET}\n")

            # 3. Voice Synthesis
            print(f"{C_CYAN}  Synthesizing Azura's voice...{C_RESET}")
            synth_t = time.time()
            audio_bytes = self.tts.synthesize(spoken_response)
            synth_elapsed = time.time() - synth_t

            # 4. Audio Playback
            if audio_bytes:
                print(f"{C_GREEN}  Speaking aloud via Chatterbox ({synth_elapsed:.2f}s synthesis)...{C_RESET}")
                # Set overlay state: speaking (STOPS SPINNING & GLOWS PALE YELLOW)
                self.overlay.set_state("speaking")
                self.player.play_bytes(audio_bytes, blocking=True)
            else:
                print(f"{C_RED}  (Voice synthesis failed or server unavailable){C_RESET}")
        finally:
            # Return overlay to normal
            self.overlay.set_state("idle")

    def run_voice_mode(self):
        """Hands-free microphone listener watching for wake word."""
        print(f"{C_GOLD}{C_BOLD}--- VOICE MODE ACTIVE ---{C_RESET}")
        wake_words = self.config.get("wake_words", ["hey azura", "azura"])
        print(f"Say {C_CYAN}\"{', '.join(wake_words[:3])}\"{C_RESET} followed by your question.")
        print(f"Example: {C_PURPLE}\"Hey Azura, where can I find Sunder?\"{C_RESET}")
        print(f"{C_DIM}Press Ctrl+C to exit.{C_RESET}\n")

        def on_wake_started():
            # "have it glow when it detects 'hey azura' and sit still until the query is complete"
            self.overlay.set_state("listening")

        def on_query_finished(query_text: str):
            print()  # newline after audio meter
            # "then the glow goes away when the prompt is finished, and it spins while researching and generating text"
            self.overlay.set_state("researching")
            if query_text.strip():
                self.handle_query(query_text)
            else:
                self.overlay.set_state("idle")

        def on_state(state: str, rms: float):
            # VU meter display
            meter_bars = int(min(20, rms / 1.5))
            bar_str = "▰" * meter_bars + "▱" * (20 - meter_bars)
            thresh = self.listener.energy_threshold if self.listener else 8.0

            if state == "CALIBRATING":
                print(f"\r{C_YELLOW}[Calibrating microphone ambient noise level...]{C_RESET}      ", end="", flush=True)
            elif state == "LISTENING":
                print(f"\r{C_DIM}[● Listening]{C_RESET} {C_PURPLE}[{bar_str}]{C_RESET} {C_DIM}(RMS: {rms:4.1f} / Thresh: {thresh:4.1f}){C_RESET} ", end="", flush=True)
            elif state == "HEARING_SPEECH":
                print(f"\r{C_GREEN}[● Voice Detected]{C_RESET} {C_GOLD}[{bar_str}]{C_RESET} {C_BOLD}(RMS: {rms:4.1f}){C_RESET}          ", end="", flush=True)
            elif state == "PROCESSING_AUDIO":
                print(f"\r{C_CYAN}[● Transcribing speech...]{C_RESET}                           ", end="", flush=True)

        self.listener = AudioListener(
            config=self.config,
            on_wake_started=on_wake_started,
            on_wake_detected=on_query_finished,
            on_state_change=on_state
        )
        self.listener.start()

        try:
            while self._running:
                time.sleep(0.2)
        except KeyboardInterrupt:
            print(f"\n{C_CYAN}Stopping listener...{C_RESET}")
        finally:
            if self.listener:
                self.listener.stop()

    def run_text_mode(self):
        """Interactive terminal text mode for silent play or testing."""
        print(f"{C_GOLD}{C_BOLD}--- INTERACTIVE TERMINAL TEXT MODE ---{C_RESET}")
        print("Type your questions below. Lady Azura will respond in text and voice.")
        print(f"{C_DIM}Type 'exit' or 'quit' to exit.{C_RESET}\n")

        while self._running:
            try:
                user_input = input(f"{C_BOLD}You > {C_RESET}").strip()
                if not user_input:
                    continue
                if user_input.lower() in ["exit", "quit", "q"]:
                    break
                if user_input.lower() in ["clear", "reset"]:
                    self.llm.clear_history()
                    print(f"{C_PURPLE}✦ Past inquiries cleared from Azura's memory.{C_RESET}\n")
                    continue
                self.handle_query(user_input)
            except (KeyboardInterrupt, EOFError):
                break

    def stop(self):
        self._running = False
        if self.listener:
            self.listener.stop()
        if self.player:
            self.player.stop()
        if hasattr(self, "overlay") and self.overlay:
            self.overlay.stop()
        if hasattr(self, "docker_mgr") and self.docker_mgr:
            self.docker_mgr.stop_container()

def main():
    parser = argparse.ArgumentParser(description="Morrowind Voice AI Companion ('Azura')")
    parser.add_argument("--cli", action="store_true", help="Run in headless terminal voice mode")
    parser.add_argument("--text", action="store_true", help="Run in interactive terminal text mode")
    parser.add_argument("--query", "-q", type=str, help="Run a single query and exit")
    parser.add_argument("--devices", action="store_true", help="List audio input and output devices")
    parser.add_argument("--settings", action="store_true", help="Open graphical settings & audio device setup GUI")
    parser.add_argument("--input-device", "-i", type=int, default=None, help="Input microphone device index")
    parser.add_argument("--output-device", "-o", type=int, default=None, help="Output speaker/headphones device index")
    parser.add_argument("--config", default="config.json", help="Path to configuration file")
    args = parser.parse_args()

    if args.settings:
        from ui.settings_dialog import show_settings_dialog
        show_settings_dialog(args.config)
        return

    if args.devices:
        list_devices()
        return

    if args.query or args.text or args.cli:
        print_banner()
        app = AzuraCompanionApp(config_path=args.config, input_dev=args.input_device, output_dev=args.output_device)

        def sig_handler(sig, frame):
            print(f"\n{C_PURPLE}Lady Azura returns to the twilight realm. Farewell.{C_RESET}")
            try:
                app.stop()
            except Exception:
                pass
            os._exit(0)

        signal.signal(signal.SIGINT, sig_handler)
        signal.signal(signal.SIGTERM, sig_handler)

        if args.query:
            app.handle_query(args.query)
        elif args.text:
            app.run_text_mode()
        elif args.cli:
            app.run_voice_mode()
    else:
        # Default: Launch Unified Master Control Dashboard GUI if display server is present
        has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY") or sys.platform == "win32" or sys.platform == "darwin")
        if has_display:
            try:
                print(f"{C_PURPLE}Launching Lady Azura Master Control Dashboard GUI...{C_RESET}")
                from ui.control_gui import launch_control_gui
                launch_control_gui(args.config)
                return
            except Exception as e:
                print(f"{C_YELLOW}Unable to launch GUI window ({e}). Falling back to terminal voice mode...{C_RESET}\n")
        else:
            print(f"{C_YELLOW}No graphical desktop display detected ($DISPLAY not set). Falling back to terminal voice mode...{C_RESET}\n")

        print_banner()
        app = AzuraCompanionApp(config_path=args.config, input_dev=args.input_device, output_dev=args.output_device)

        def sig_handler(sig, frame):
            print(f"\n{C_PURPLE}Lady Azura returns to the twilight realm. Farewell.{C_RESET}")
            try:
                app.stop()
            except Exception:
                pass
            os._exit(0)

        signal.signal(signal.SIGINT, sig_handler)
        signal.signal(signal.SIGTERM, sig_handler)
        app.run_voice_mode()


if __name__ == "__main__":
    main()
