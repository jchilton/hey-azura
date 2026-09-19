import os
import time
import json
import logging
import requests
from typing import Optional, Dict, Any, List, Tuple
from core.uesp_client import UESPClient
from core.entity_resolver import EntityResolver

logger = logging.getLogger(__name__)

AZURA_SYSTEM_PROMPT = """You are Lady Azura, the Daedric Prince of Dusk and Dawn, Mother of the Rose, Queen of the Night Sky. You watch over your mortal champion, the Nerevarine (Moon-and-Star), guiding them through Vvardenfell and the mainland of Morrowind (including Tamriel Rebuilt and official plugins).

Personality & Tone:
- Regal, mystical, ancient, intimate yet commanding and maternal.
- Address the mortal respectfully but with divine authority (e.g., "Moon-and-Star", "Champion", "Mortal").
- Remember previous inquiries in this conversation and provide coherent follow-up answers.
- Never break character.

Response Constraints for Spoken Voice:
- Your response will be spoken aloud to the player via a voice synthesizer while they play the game.
- Keep your answers concise, practical, and direct (2 to 4 spoken sentences).
- Do NOT use markdown symbols, asterisks (*), bullets, numbered lists, tables, or web URLs in your speech.
- Factual Accuracy: Always ground your answers in the provided UESP text. Tamriel Rebuilt is 100% valid and canonical to the player's world. If an entity is an undead, lich, ghost, daedra, or god, describe who and what they are, their lair, and their quests. If and only if no record exists across both Morrowind and Tamriel Rebuilt, state that the name is unknown.
"""

class AzuraLLM:
    """Orchestrates Azura's persona, multi-turn conversational memory, UESP retrieval, and LLM synthesis."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        self.llm_cfg = cfg.get("llm", {})
        self.entity_resolver = EntityResolver()

        self.provider = str(self.llm_cfg.get("provider", "gemini")).lower().strip()
        keys = self.llm_cfg.get("keys", {})
        urls = self.llm_cfg.get("urls", {})
        models = self.llm_cfg.get("models", {})

        # Per-provider API Key Resolution
        env_key = os.environ.get(f"{self.provider.upper()}_API_KEY")
        prov_key = keys.get(self.provider) or self.llm_cfg.get(f"{self.provider}_api_key")

        if not env_key and not prov_key:
            if self.provider == "gemini":
                env_key = os.environ.get("GEMINI_API_KEY")
                prov_key = self.llm_cfg.get("gemini_api_key") or self.llm_cfg.get("api_key")
            elif self.provider == "openai":
                env_key = os.environ.get("OPENAI_API_KEY")
                prov_key = self.llm_cfg.get("openai_api_key") or self.llm_cfg.get("api_key")

        self.api_key = env_key or prov_key or ""

        # Dedicated Gemini Key (used for optional automatic fallback if secondary provider fails)
        self.gemini_key = (
            os.environ.get("GEMINI_API_KEY")
            or keys.get("gemini")
            or self.llm_cfg.get("gemini_api_key")
            or (self.api_key if self.provider == "gemini" else "")
        )

        # Per-provider Base URL Resolution
        self.api_url = (urls.get(self.provider) or self.llm_cfg.get(f"{self.provider}_url") or self.llm_cfg.get("api_url") or "").rstrip("/")
        if not self.api_url and self.provider == "ollama":
            self.api_url = "http://localhost:11434"
        elif not self.api_url and self.provider == "openai":
            self.api_url = "https://api.openai.com/v1"

        # Per-provider Model Resolution
        self.model = models.get(self.provider) or self.llm_cfg.get(f"{self.provider}_model") or self.llm_cfg.get("model") or "gemini-3.5-flash"
        self.gemini_model = models.get("gemini") or self.llm_cfg.get("gemini_model") or (self.model if self.provider == "gemini" else "gemini-3.5-flash")

        self.data_sources = cfg.get("data_sources", {"morrowind": True, "goty": True, "tamriel_rebuilt": True})
        self.uesp = UESPClient(api_url=cfg.get("uesp", {}).get("api_url", "https://en.uesp.net/w/api.php"))
        self._load_mod_data()

        # Multi-turn conversation memory
        self.history: List[Dict[str, str]] = []
        self.last_subject: str = ""

    def clear_history(self):
        """Reset conversation memory."""
        self.history.clear()
        self.last_subject = ""
        logger.info("Azura conversation memory cleared.")

    def _load_mod_data(self):
        """Load local supplementary mod knowledge if available."""
        self.mod_context = ""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for fname in ["poison_song_info.json", "umopp_info.json"]:
            fpath = os.path.join(base_dir, "data", fname)
            if os.path.exists(fpath):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self.mod_context += f"\n[Mod Reference: {data.get('mod_name', fname)}]\n{json.dumps(data, indent=1)}\n"
                except Exception as e:
                    logger.debug(f"Failed loading mod file {fname}: {e}")

    def query(self, user_question: str) -> Tuple[str, List[Dict[str, str]]]:
        """
        Process a user's question with multi-turn context memory:
        1. Resolves proper nouns & Morrowind entity spellings.
        2. Routes to Gemini, OpenAI-compatible Custom API, or Ollama endpoint based on provider setting.
        """
        user_question, replacements = self.entity_resolver.resolve_entities(user_question)
        logger.info(f"Azura processing query: '{user_question}' (provider: {self.provider}, model: {self.model})")
        
        sources: List[Dict[str, str]] = []
        spoken_response = ""

        if self.provider == "gemini" and self.gemini_key:
            spoken_response, sources = self._call_gemini(user_question)
        elif self.provider in ["openai", "custom", "openrouter", "lmstudio"] or "v1" in self.api_url:
            spoken_response, sources = self._call_openai_compatible(user_question)
        elif self.provider == "ollama":
            spoken_response, sources = self._call_openai_compatible(user_question)
            if not spoken_response:
                spoken_response, sources = self._call_gemini(user_question)

        # Fallback to Gemini if default failed
        if not spoken_response and self.gemini_key:
            spoken_response, sources = self._call_gemini(user_question)

        # Final safety response if offline or unconfigured
        if not spoken_response:
            spoken_response = "The twilight mist clouds my vision for a moment, Moon-and-Star. Please verify your LLM Provider and API key in settings."

        # Clean speech
        cleaned_speech = self._clean_spoken_output(spoken_response)

        # Append to conversation history (keep last 8 turns = 16 messages)
        self.history.append({"role": "user", "content": user_question})
        self.history.append({"role": "assistant", "content": cleaned_speech})
        if len(self.history) > 16:
            self.history = self.history[-16:]

        return cleaned_speech, sources

    def _call_gemini(self, user_question: str) -> Tuple[Optional[str], List[Dict[str, str]]]:
        """
        Query Gemini API with single-pass UESP retrieval:
        1. Performs UESP search directly in Python via UESPClient.
        2. Injects top article extracts into prompt context.
        3. Calls Gemini exactly ONCE with no tools registered (guarantees 1 API call max, zero tool loops, zero billing runaway).
        """
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.gemini_key)
            sources_consulted: List[Dict[str, str]] = []

            # 1. Direct Python UESP search & article extraction
            logger.info(f"Retrieving UESP articles for query: '{user_question}'")
            search_hits = self.uesp.search(user_question, limit=3, data_sources=self.data_sources)
            retrieved_context = ""
            
            for h in search_hits:
                title = h.get("title")
                u = h.get("url", f"https://en.uesp.net/wiki/{title.replace(' ', '_')}")
                sources_consulted.append({"title": title, "url": u})
                
                summary = self.uesp.get_article_summary(title) if len(sources_consulted) <= 2 else None
                snippet = h.get("snippet", "")
                
                if summary and snippet and snippet not in summary and not snippet.startswith("Article titled"):
                    article_info = f"{summary}\nKey Excerpt: ...{snippet}..."
                elif summary:
                    article_info = summary
                else:
                    article_info = snippet
                retrieved_context += f"\n--- UESP Article: {title} ---\n{article_info}\n"

            # 2. Single-pass prompt construction
            rag_prompt = f"""Player Question: "{user_question}"

UESP Knowledge Retrieved:
{retrieved_context if retrieved_context.strip() else "No specific UESP article found; rely on Elder Scrolls Morrowind & Tamriel Rebuilt lore."}

Supplementary Mod Lore:
{self.mod_context}

Instruction: Speak as Lady Azura in 2 to 3 regal spoken sentences. Provide accurate facts grounded in the UESP knowledge above. If the UESP excerpts are partial or do not directly contain the exact location/answer, combine them with your internal Elder Scrolls Morrowind lore knowledge to answer accurately. Never claim an item or location does not exist simply because it is missing from a brief excerpt. Do NOT use markdown symbols (*, #), bullets, or web URLs."""

            # 3. Format conversation history
            contents = []
            for turn in self.history:
                role = "user" if turn["role"] == "user" else "model"
                contents.append(types.Content(role=role, parts=[types.Part.from_text(text=turn["content"])]))
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text=rag_prompt)]))

            # 4. Single API Call with NO tools (100% single-call safety guarantee)
            models_to_try = [self.gemini_model, "gemini-2.5-flash", "gemini-1.5-flash"]
            for model_name in models_to_try:
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=types.GenerateContentConfig(
                            system_instruction=AZURA_SYSTEM_PROMPT,
                            temperature=0.3,
                            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
                        )
                    )
                    if response and response.text:
                        return response.text.strip(), sources_consulted
                except Exception as m_err:
                    logger.warning(f"Model {model_name} error: {m_err}")

            return None, []
        except Exception as e:
            logger.error(f"Error querying Gemini API: {e}")
            return None, []

    def _call_ollama(self, current_prompt: str) -> Optional[str]:
        """Query local Ollama instance on RTX 5070 Ti with full conversation history."""
        try:
            messages = [{"role": "system", "content": AZURA_SYSTEM_PROMPT}]
            for turn in self.history:
                messages.append(turn)
            messages.append({"role": "user", "content": current_prompt})

            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": 0.5,
                    "num_predict": 180
                }
            }
            res = requests.post(f"{self.ollama_url}/api/chat", json=payload, timeout=3)
            if res.status_code == 200:
                data = res.json()
                return data.get("message", {}).get("content", "").strip()
            else:
                logger.error(f"Ollama returned HTTP {res.status_code}: {res.text}")
        except Exception as e:
            logger.error(f"Error querying Ollama: {e}")
        return None

    def _call_openai_compatible(self, user_question: str) -> Tuple[Optional[str], List[Dict[str, str]]]:
        """Query any OpenAI-compatible API endpoint (OpenAI, OpenRouter, LM Studio, vLLM, Ollama, etc.)."""
        try:
            logger.info(f"Retrieving UESP articles for query: '{user_question}'")
            search_hits = self.uesp.search(user_question, limit=3, data_sources=self.data_sources)
            retrieved_context = ""
            sources_consulted = []

            for h in search_hits:
                title = h.get("title")
                u = h.get("url", f"https://en.uesp.net/wiki/{title.replace(' ', '_')}")
                sources_consulted.append({"title": title, "url": u})
                summary = self.uesp.get_article_summary(title) if len(sources_consulted) <= 2 else None
                snippet = h.get("snippet", "")
                
                if summary and snippet and snippet not in summary and not snippet.startswith("Article titled"):
                    article_info = f"{summary}\nKey Excerpt: ...{snippet}..."
                elif summary:
                    article_info = summary
                else:
                    article_info = snippet
                retrieved_context += f"\n--- UESP Article: {title} ---\n{article_info}\n"

            rag_prompt = f"""Player Question: "{user_question}"

UESP Knowledge Retrieved:
{retrieved_context if retrieved_context.strip() else "No specific UESP article found; rely on Elder Scrolls Morrowind & Tamriel Rebuilt lore."}

Supplementary Mod Lore:
{self.mod_context}

Instruction: Speak as Lady Azura in 2 to 3 regal spoken sentences. Provide accurate facts grounded in the UESP knowledge above. If the UESP excerpts are partial or do not directly contain the exact location/answer, combine them with your internal Elder Scrolls Morrowind lore knowledge to answer accurately. Never claim an item or location does not exist simply because it is missing from a brief excerpt. Do NOT use markdown symbols (*, #), bullets, or web URLs."""

            messages = [{"role": "system", "content": AZURA_SYSTEM_PROMPT}]
            for turn in self.history:
                messages.append(turn)
            messages.append({"role": "user", "content": rag_prompt})

            base = self.api_url.rstrip("/")
            if base.endswith("/chat/completions"):
                endpoint = base
            elif base.endswith("/v1"):
                endpoint = f"{base}/chat/completions"
            else:
                endpoint = f"{base}/v1/chat/completions"

            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 200
            }

            res = requests.post(endpoint, json=payload, headers=headers, timeout=10)
            if res.status_code == 200:
                data = res.json()
                content = data["choices"][0]["message"]["content"].strip()
                return content, sources_consulted
            else:
                logger.error(f"OpenAI endpoint returned HTTP {res.status_code}: {res.text}")
        except Exception as e:
            logger.error(f"Error querying OpenAI-compatible endpoint: {e}")
        return None, []

    def _clean_spoken_output(self, text: str) -> str:
        """Strip formatting, quotation marks, and meta annotations for clean speech."""
        cleaned = text.strip()
        cleaned = cleaned.replace("*", "").replace("#", "")
        if (cleaned.startswith('"') and cleaned.endswith('"')) or (cleaned.startswith("'") and cleaned.endswith("'")):
            cleaned = cleaned[1:-1].strip()
        import re
        cleaned = re.sub(r'\([^\)]*\)', '', cleaned)
        cleaned = re.sub(r'\[[^\]]*\]', '', cleaned)
        return " ".join(cleaned.split())
