# Azura Voice Samples Directory

> [!IMPORTANT]
> **Copyright Notice**: Game audio extracted from *The Elder Scrolls III: Morrowind* is copyrighted property of Bethesda Softworks / ZeniMax Media and is **not included** in this open-source repository.

## Setting Up Voice Cloning for Chatterbox TTS

To use Chatterbox TTS local voice synthesis with Lady Azura's voice:

1. **Obtain Audio Sample**:
   - Extract audio from your legally owned copy of Morrowind (e.g. from `Data Files/Video/mw_cavern.bik` or `mw_intro.bik` using `ffmpeg` or `RAD Video Tools`).
   - Alternatively, supply any custom ~10-15 second clean mono/stereo `.wav` voice file.

2. **Place Reference Audio**:
   - Save the `.wav` file into this directory (e.g. `azura_cavern_15s.wav`).
   - Alternatively, upload the file directly to Chatterbox TTS (`http://localhost:8030/upload_reference`).

3. **Configure `config.json`**:
   Ensure your `config.json` points to the filename:
   ```json
   "chatterbox": {
     "voice_mode": "clone",
     "reference_audio": "azura_cavern_15s.wav"
   }
   ```
