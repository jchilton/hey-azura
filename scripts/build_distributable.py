#!/usr/bin/env python3
"""
Hey-Azura Distributable Package Builder
Compiles the application into a standalone distribution package in dist/
including executables, data files, config, and Windows launcher scripts.
"""

import os
import sys
import shutil
import subprocess
import zipfile
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("build_distributable")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"
PACKAGE_NAME = "HeyAzura-v1.0.0"

def create_windows_launchers(target_dir: Path):
    """Generate convenient Windows PowerShell launch scripts in target directory."""
    # 1. Main Launcher (.ps1)
    start_ps1 = target_dir / "Start_HeyAzura.ps1"
    with open(start_ps1, "w", encoding="utf-8") as f:
        f.write("# PowerShell Launcher for Lady Azura Voice Companion\n")
        f.write('Write-Host "Starting Lady Azura Companion..." -ForegroundColor Cyan\n')
        f.write('if (Test-Path ".\\HeyAzura.exe") {\n')
        f.write('    .\\HeyAzura.exe\n')
        f.write('} else {\n')
        f.write('    python main.py\n')
        f.write('}\n')

    # 2. Settings Launcher (.ps1)
    settings_ps1 = target_dir / "Audio_Settings.ps1"
    with open(settings_ps1, "w", encoding="utf-8") as f:
        f.write("# PowerShell Launcher for Audio & Settings Setup\n")
        f.write('Write-Host "Opening Audio & Settings Setup..." -ForegroundColor Cyan\n')
        f.write('if (Test-Path ".\\HeyAzura.exe") {\n')
        f.write('    .\\HeyAzura.exe --settings\n')
        f.write('} else {\n')
        f.write('    python main.py --settings\n')
        f.write('}\n')

    # 3. Docker Chatterbox Pull Helper (.ps1)
    chatterbox_ps1 = target_dir / "Pull_Chatterbox_Docker.ps1"
    with open(chatterbox_ps1, "w", encoding="utf-8") as f:
        f.write("# PowerShell Helper to pull Chatterbox Docker Container\n")
        f.write('Write-Host "Pulling Chatterbox TTS Docker Image..." -ForegroundColor Cyan\n')
        f.write('docker pull custom/chatterbox-tts:latest\n')
        f.write('Write-Host "Done!" -ForegroundColor Green\n')

    # 4. README for User
    readme_txt = target_dir / "README_WINDOWS.txt"
    with open(readme_txt, "w", encoding="utf-8") as f:
        f.write("====================================================\n")
        f.write("       LADY AZURA VOICE COMPANION v1.0.0            \n")
        f.write("====================================================\n\n")
        f.write("QUICK START INSTRUCTIONS:\n")
        f.write("1. Right-click 'Audio_Settings.ps1' -> Run with PowerShell to choose your Microphone, Speakers, and enter your Gemini API Key.\n")
        f.write("2. Ensure Docker Desktop is running if you want Hey-Azura to auto-start Chatterbox TTS locally.\n")
        f.write("3. Right-click 'Start_HeyAzura.ps1' -> Run with PowerShell to launch voice mode!\n")
        f.write("4. Say 'Hey Azura, where is Sunder?' while playing Morrowind.\n\n")
        f.write("REMOTE CHATTERBOX SERVER (LAN):\n")
        f.write("If Chatterbox runs on another PC on your network, open config.json and set:\n")
        f.write('  "host": "192.168.1.XX", "port": 8030, "manage_docker": false\n')

def build_package():
    logger.info("Cleaning previous build and dist directories...")
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    pkg_dir = DIST_DIR / PACKAGE_NAME
    pkg_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Running PyInstaller to compile executable...")
    pyinstaller_cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=HeyAzura",
        "--onedir",
        "--clean",
        "--noconfirm",
        f"--add-data={PROJECT_ROOT / 'data'}:data",
        f"--add-data={PROJECT_ROOT / 'ui'}:ui",
        f"--add-data={PROJECT_ROOT / 'config.json'}:.",
        str(PROJECT_ROOT / "main.py")
    ]

    res = subprocess.run(pyinstaller_cmd, cwd=PROJECT_ROOT)
    if res.returncode != 0:
        logger.error("PyInstaller build failed!")
        sys.exit(1)

    dist_executable_dir = DIST_DIR / "HeyAzura"
    if dist_executable_dir.exists():
        # Move PyInstaller onedir contents into package directory
        for item in dist_executable_dir.iterdir():
            target_item = pkg_dir / item.name
            if item.is_dir():
                shutil.copytree(item, target_item, dirs_exist_ok=True)
            else:
                shutil.copy2(item, target_item)
        shutil.rmtree(dist_executable_dir)

    # Copy external data folders & sample voice files
    logger.info("Copying configuration & asset files...")
    shutil.copy2(PROJECT_ROOT / "config.json", pkg_dir / "config.json")
    shutil.copytree(PROJECT_ROOT / "data", pkg_dir / "data", dirs_exist_ok=True)
    shutil.copytree(PROJECT_ROOT / "ui", pkg_dir / "ui", dirs_exist_ok=True)
    if (PROJECT_ROOT / "azura_voice_samples").exists():
        shutil.copytree(PROJECT_ROOT / "azura_voice_samples", pkg_dir / "azura_voice_samples", dirs_exist_ok=True)

    # Create launch scripts
    create_windows_launchers(pkg_dir)

    # Create zip archive
    zip_path = DIST_DIR / f"{PACKAGE_NAME}.zip"
    logger.info(f"Creating zip archive at {zip_path}...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(pkg_dir):
            for file in files:
                abs_file = Path(root) / file
                rel_file = abs_file.relative_to(DIST_DIR)
                zipf.write(abs_file, rel_file)

    logger.info("====================================================")
    logger.info(f"DISTRIBUTABLE PACKAGE CREATED SUCCESSFULLY!")
    logger.info(f"Folder:  {pkg_dir}")
    logger.info(f"Zip File: {zip_path}")
    logger.info("====================================================")

if __name__ == "__main__":
    build_package()
