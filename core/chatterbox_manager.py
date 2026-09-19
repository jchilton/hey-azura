import os
import time
import logging
import subprocess
import requests
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ChatterboxDockerManager:
    """
    Manages local Docker container lifecycle for Chatterbox TTS.
    If Chatterbox is configured for localhost and is not running, auto-starts the container
    and shuts it down on application exit.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        chatterbox_cfg = cfg.get("chatterbox", {})
        
        self.host = chatterbox_cfg.get("host")
        if not self.host:
            # Fallback parsing from full URL
            raw_url = chatterbox_cfg.get("url", "http://localhost:8030")
            from urllib.parse import urlparse
            parsed = urlparse(raw_url)
            self.host = parsed.hostname or "localhost"
            self.port = parsed.port or 8030
        else:
            self.port = chatterbox_cfg.get("port", 8030)

        self.manage_docker = chatterbox_cfg.get("manage_docker", True)
        self.container_name = chatterbox_cfg.get("docker_container_name", "chatterbox-tts")
        self.docker_image = chatterbox_cfg.get("docker_image", "custom/chatterbox-tts:latest")
        self.base_url = f"http://{self.host}:{self.port}"
        
        self._started_by_us = False

    def is_local(self) -> bool:
        """Check if target host is local machine."""
        return self.host in ["localhost", "127.0.0.1", "0.0.0.0", "::1"]

    def is_server_healthy(self) -> bool:
        """Check if Chatterbox HTTP server is responding."""
        try:
            r = requests.get(f"{self.base_url}/get_reference_files", timeout=2)
            return r.status_code == 200
        except Exception:
            return False

    def is_docker_available(self) -> bool:
        """Check if Docker CLI is installed and responsive."""
        try:
            res = subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=4)
            return res.returncode == 0
        except Exception:
            return False

    def ensure_started(self) -> bool:
        """Ensure Chatterbox TTS server is online, launching Docker container if local and offline."""
        if self.is_server_healthy():
            logger.info(f"Chatterbox TTS server is online at {self.base_url}")
            return True

        if not self.is_local() or not self.manage_docker:
            logger.warning(f"Chatterbox TTS server at {self.base_url} is offline (remote/docker management disabled).")
            return False

        if not self.is_docker_available():
            logger.warning("Docker Desktop is not running or available to start Chatterbox TTS container.")
            return False

        logger.info(f"Chatterbox server offline. Attempting to start Docker container '{self.container_name}'...")

        # 1. Try starting existing container
        try:
            res = subprocess.run(["docker", "start", self.container_name], capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                self._started_by_us = True
                logger.info(f"Started existing container '{self.container_name}'. Waiting for TTS server...")
                return self._wait_for_health()
        except Exception as e:
            logger.debug(f"Docker start failed: {e}")

        # 2. Try creating & running container if start failed
        try:
            cmd = [
                "docker", "run", "-d",
                "-p", f"{self.port}:8030",
                "--name", self.container_name,
                self.docker_image
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if res.returncode == 0:
                self._started_by_us = True
                logger.info(f"Created & started container '{self.container_name}'. Waiting for TTS server...")
                return self._wait_for_health()
            else:
                logger.error(f"Failed to run Docker container: {res.stderr}")
        except Exception as e:
            logger.error(f"Error launching Docker container: {e}")

        return False

    def _wait_for_health(self, timeout_sec: int = 20) -> bool:
        """Wait for TTS server to pass health check."""
        start_t = time.time()
        while time.time() - start_t < timeout_sec:
            if self.is_server_healthy():
                logger.info("Chatterbox TTS server started successfully!")
                return True
            time.sleep(1.0)
        logger.error("Timed out waiting for Chatterbox TTS server to start.")
        return False

    def stop_container(self):
        """Stop container on exit if it was launched by us."""
        if self._started_by_us and self.is_local():
            logger.info(f"Stopping Chatterbox TTS container '{self.container_name}'...")
            try:
                subprocess.run(["docker", "stop", self.container_name], capture_output=True, timeout=8)
                logger.info("Chatterbox container stopped.")
            except Exception as e:
                logger.warning(f"Failed to stop container: {e}")
