# Hey Azura — Morrowind Voice AI Companion

A dedicated voice-activated AI companion for playing *The Elder Scrolls III: Morrowind* (Game of the Year Edition), *Tamriel Rebuilt* (including Poison Song), and *UMOPP* (Universal Morrowind Official Plugins Patch).

Azura listens continuously through your microphone, responds when addressed (*"Hey Azura"* or *"Lady Azura"*), queries UESP in real-time for lore, quests, item coordinates, and walkthroughs, and speaks back in **Azura's original Morrowind voice**, synthesized locally on your GPU via your Chatterbox TTS Server.

---

## Features

- 🎙️ **Hands-free Voice Activation**: Powered by local `faster-whisper` (`tiny.en`), filtering background game audio and triggering on *"Hey Azura"*, *"Azura"*, or *"Lady Azura"*.
- 🔊 **Authentic Cloned Voice**: Synthesizes speech locally on your GPU via Chatterbox TTS (`http://localhost:8030/tts`) using extracted original Morrowind cutscenes (~1.8 – 2.0 GB VRAM usage during synthesis).
- ⚡ **Low-VRAM Local Intelligence**: Configured for local `llama3.2:3b` on Ollama (~2.2 GB VRAM) and Whisper STT (~0.4 GB VRAM). Combined total is ~4.4 GB VRAM, leaving plenty of VRAM headroom for OpenMW / Morrowind with high-res texture packs on any 6GB+ GPU.
- 📖 **Live UESP Integration**: Automatically searches and extracts real-time articles from `https://en.uesp.net/w/api.php` across `Morrowind:`, `Bloodmoon:`, `Tribunal:`, `Tamriel Rebuilt:`, and `Lore:` namespaces.
- 💬 **Interactive Terminal UI**: Run in hands-free voice mode while playing, or in terminal text mode.

---

## Windows Installation & Setup Guide

### 1. System Requirements & Prerequisites
* **Operating System**: Windows 10 or Windows 11 (64-bit).
* **FFmpeg** (Required for extracting voice samples from game cutscenes):
  * Install via terminal: `winget install ffmpeg`
  * Or download `ffmpeg.exe` from [ffmpeg.org](https://ffmpeg.org/download.html) and place `ffmpeg.exe` directly inside the `HeyAzura` application folder.
* **LLM Engine (Pick One)**:
  * **Google Gemini (Recommended / Zero Local Hardware Required)**: Get a free API key at [Google AI Studio](https://aistudio.google.com/). *(Note: Free tier keys can hit rate limits or quota caps after just 2–3 queries. For unlimited, reliable usage, local Ollama or a paid API key is recommended).*
  * **Local Ollama (100% Offline GPU)**: Download [Ollama for Windows](https://ollama.com/) (`ollama run llama3.2:3b`).
* **Chatterbox TTS (For Lady Azura's Voice Synthesis)**:
  * **Local GPU Mode (Default)**: Requires [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/). Hey Azura automatically manages the local Chatterbox container (`docker run -d -p 8030:8030 chatterbox-tts`).
  * **Remote Server Mode**: If Chatterbox is running on another machine on your LAN, enter its IP address in Settings (no local Docker required).
* **Morrowind Game Files** (Optional, for voice cloning):
  * Any installed copy of *The Elder Scrolls III: Morrowind* (Steam, GOG, or CD).

---

### 2. Getting Started on Windows (Standalone Release)
1. Download and extract **`HeyAzura-v1.0.0.zip`**.
2. Double-click **`HeyAzura.exe`** to launch the Master Control Dashboard.
3. Click **Settings** (⚙️) in the top menu bar:
   * **LLM Settings**: Select your provider (`gemini`, `ollama`, or `openai`), select your model, and enter your API key if applicable.
   * **Voice Extraction**: Click **Browse...** to select your Morrowind installation folder (e.g., `C:\Program Files (x86)\Steam\steamapps\common\Morrowind`) and click **Extract Voice Sample**.
   * Click **Save**.
4. Speak naturally into your microphone: *"Hey Azura, where do I find Goldbrand?"*

---

## Quick Start (Linux / Source Mode)
Run from your terminal while playing Morrowind:
```bash
~/Code/hey-azura/run.sh
```
Speak naturally into your microphone:
> *"Hey Azura, where do I find the Boots of Blinding Speed?"*  
> *"Lady Azura, who gives the Siege at Firemoth quest?"*  
> *"Hey Azura, where is the Cavern of the Incarnate?"*

### 2. Interactive Terminal Text Mode
For testing silently or typing while playing:
```bash
~/Code/hey-azura/run.sh --text
```

### 3. Single Query Test
```bash
~/Code/hey-azura/run.sh -q "Where is Sunder located?"
```

### 4. OBS & Floating UI Overlay
When Azura is running, a transparent animation overlay server runs automatically at **`http://localhost:8035`**.
- **1. Idle**: Azura's Star sits still in its normal resting state.
- **2. "Hey Azura" Detected (Prompting)**: Sits still and radiates a soft **pale yellow glow** while you speak your question.
- **3. Prompt Complete (Researching)**: The glow goes away and the star **spins continuously** while consulting UESP, prompting the LLM, and generating speech.
- **4. Answering (Speaking)**: The star stops spinning and **glows pale yellow again** while Azura's voice plays.
- **5. Finished**: Returns to still, un-glowing normal state.

**Adding to OBS:**
1. In OBS, click **+** under Sources and choose **Browser**.
2. Set URL to: `http://localhost:8035`
3. Set Width: `320`, Height: `320`.
4. Leave CSS as default (the page background is 100% transparent).

**Optional Standalone Testing:**
To test the overlay in your browser or OBS without voice input:
```bash
~/Code/hey-azura/.venv/bin/python3 ~/Code/hey-azura/ui/overlay_server.py
```

---

## Configuration (`config.json`)

- `wake_words`: Trigger phrases (`["hey azura", "azura", "lady azura", "hail azura"]`).
- `chatterbox`: URL and reference audio clone file (`azura_cavern_15s.wav`).
- `llm`: Provider (`ollama` or `gemini`), model name (`llama3.2:3b`), and temperature.
- `audio`: Microphone energy thresholds and pause detection timing.

---

## License & Legal Disclaimer

This project is licensed under the [MIT License](file:///home/jchilton/Code/hey-azura/LICENSE).

> [!NOTE]
> **Trademark Disclaimer**: *The Elder Scrolls*, *Morrowind*, *Tribunal*, *Bloodmoon*, *Bethesda*, *Bethesda Softworks*, *ZeniMax*, and related logos are registered trademarks or trademarks of ZeniMax Media Inc.  
> **Hey Azura** is an independent, non-commercial open-source companion tool. It is not affiliated with, endorsed by, or sponsored by Bethesda Softworks LLC, ZeniMax Media Inc., or their affiliates. No game assets or copyrighted audio files are distributed with this software.
