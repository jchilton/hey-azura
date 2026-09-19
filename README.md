# Hey Azura — Morrowind Voice AI Companion

A dedicated voice-activated AI companion for playing *The Elder Scrolls III: Morrowind* (Game of the Year Edition), *Tamriel Rebuilt* (including Poison Song), and *UMOPP* (Universal Morrowind Official Plugins Patch).

Azura listens continuously through your microphone, responds when addressed (*"Hey Azura"* or *"Lady Azura"*), queries UESP in real-time for lore, quests, item coordinates, and walkthroughs, and speaks back in **Azura's original Morrowind voice**, synthesized locally on your GPU via your Chatterbox TTS Server.

---

## Features

- 🎙️ **Hands-free Voice Activation**: Powered by local `faster-whisper` (`tiny.en`), filtering background game audio and triggering on *"Hey Azura"*, *"Azura"*, or *"Lady Azura"*.
- 🔊 **Authentic Cloned Voice**: Synthesizes speech locally on your GPU via Chatterbox TTS (`http://localhost:8030/tts`) using extracted original Morrowind cinematics (`azura_cavern_15s.wav` / `azura_intro_12s.wav`).
- ⚡ **Low-VRAM Local Intelligence**: Configured for local `llama3.2:3b` on Ollama (`http://localhost:11434`), using only ~2.2 GB VRAM and generating >250 tokens/sec, leaving plenty of VRAM for Morrowind / OpenMW with high-res textures.
- 📖 **Live UESP Integration**: Automatically searches and extracts real-time articles from `https://en.uesp.net/w/api.php` across `Morrowind:`, `Tamriel Rebuilt:`, and `Lore:` namespaces.
- 💬 **Interactive Terminal UI**: Run in hands-free voice mode while playing, or in terminal text mode.

---

## Quick Start

### 1. Hands-Free Voice Mode (Default)
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
