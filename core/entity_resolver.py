import os
import json
import re
import logging
from typing import Dict, List, Tuple, Optional, Set, Any

logger = logging.getLogger(__name__)

def levenshtein_distance(s1: str, s2: str) -> int:
    """Compute the Levenshtein edit distance between two strings."""
    if s1 == s2:
        return 0
    if len(s1) == 0:
        return len(s2)
    if len(s2) == 0:
        return len(s1)

    v0 = list(range(len(s2) + 1))
    v1 = [0] * (len(s2) + 1)

    for i in range(len(s1)):
        v1[0] = i + 1
        for j in range(len(s2)):
            cost = 0 if s1[i] == s2[j] else 1
            v1[j + 1] = min(v1[j] + 1, v0[j + 1] + 1, v0[j] + cost)
        v0, v1 = v1, v0

    return v0[len(s2)]

def simplified_phonetic_key(s: str) -> str:
    """
    Generate a simple phonetic key for a string to aid fuzzy sound-alike matching.
    Strips non-alphanumeric, maps similar sounds (c/k/q -> k, v/w -> v, th/f -> f, etc.),
    removes vowels after the first character, and collapses duplicate letters.
    """
    clean = re.sub(r"[^a-z]", "", s.lower())
    if not clean:
        return ""
    
    # Map phonetic equivalents
    res = []
    for i, ch in enumerate(clean):
        if ch in "ckq":
            ch = "k"
        elif ch in "vw":
            ch = "v"
        elif ch in "z":
            ch = "s"
        elif ch in "aeiouy":
            # Keep leading vowel, strip subsequent vowels for skeleton comparison
            if i > 0:
                continue
            ch = "a"
        res.append(ch)

    # Collapse duplicate adjacent characters
    collapsed = []
    for ch in res:
        if not collapsed or collapsed[-1] != ch:
            collapsed.append(ch)
            
    return "".join(collapsed)

class EntityResolver:
    """
    Phonetic & Dictionary Entity Resolver for Morrowind, Bloodmoon, Tribunal, and Tamriel Rebuilt.
    Scans speech-to-text outputs for common phonetic mishearings or fuzzy matches
    and replaces them with canonical proper nouns.
    """

    def __init__(self, data_path: Optional[str] = None):
        if data_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            data_path = os.path.join(base_dir, "data", "morrowind_entities.json")

        self.data_path = data_path
        self.canonical_names: List[str] = []
        self.alias_map: Dict[str, str] = {}  # normalized alias -> canonical
        self.phonetic_map: Dict[str, str] = {}  # phonetic key -> canonical
        
        self.load_entities()

    def load_entities(self):
        """Load entity dictionary and populate search indexes."""
        if not os.path.exists(self.data_path):
            logger.warning(f"Entity data file not found at {self.data_path}")
            return

        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            entities = data.get("entities", [])
            for item in entities:
                canonical = item.get("canonical", "").strip()
                if not canonical:
                    continue
                
                self.canonical_names.append(canonical)
                norm_canonical = self._normalize_text(canonical)
                self.alias_map[norm_canonical] = canonical
                
                pkey_can = simplified_phonetic_key(canonical)
                if pkey_can and len(pkey_can) >= 3:
                    self.phonetic_map[pkey_can] = canonical

                aliases = item.get("aliases", [])
                for alias in aliases:
                    alias_clean = alias.strip()
                    if not alias_clean:
                        continue
                    norm_alias = self._normalize_text(alias_clean)
                    self.alias_map[norm_alias] = canonical
                    
                    pkey_alias = simplified_phonetic_key(alias_clean)
                    if pkey_alias and len(pkey_alias) >= 3 and pkey_alias not in self.phonetic_map:
                        self.phonetic_map[pkey_alias] = canonical

            logger.info(f"EntityResolver loaded {len(self.canonical_names)} entities with {len(self.alias_map)} aliases.")
        except Exception as e:
            logger.error(f"Failed to load entity database: {e}")

    def get_prompt_vocab_string(self) -> str:
        """Format canonical names into a comma-separated vocabulary string for STT initial_prompt."""
        return ", ".join(self.canonical_names)

    def _normalize_text(self, text: str) -> str:
        """Strip punctuation and normalize whitespace for exact n-gram matching."""
        clean = re.sub(r"[^\w\s]", " ", text.lower())
        return " ".join(clean.split())

    def resolve_entities(self, transcript: str) -> Tuple[str, List[Dict[str, str]]]:
        """
        Scan STT transcript and resolve phonetic mishearings to canonical Elder Scrolls entities.
        Returns:
            (corrected_transcript, list_of_replacements)
        """
        if not transcript or not transcript.strip():
            return transcript, []

        tokens = transcript.split()
        if not tokens:
            return transcript, []

        replacements_made = []
        i = 0
        n_tokens = len(tokens)
        result_tokens = []

        # Helper to extract leading/trailing punctuation
        def _get_punct(chunk_tokens: List[str]) -> Tuple[str, str]:
            lead_p = re.match(r"^([^\w\s]*)", chunk_tokens[0]).group(1)
            trail_p = re.search(r"([^\w\s]*)$", chunk_tokens[-1]).group(1)
            return lead_p, trail_p

        STOPWORDS = {"is", "where", "how", "what", "who", "which", "why", "in", "on", "at", "to", "for", "of", "the", "a", "an", "and", "or", "tell", "me", "about", "can", "i", "you", "do", "does", "did", "get", "find", "reach", "beat", "kill", "cure", "item", "quest", "location", "it", "with", "from"}

        # Sliding window from max n-gram length 4 down to 1
        while i < n_tokens:
            matched = False

            for ngram_size in range(min(5, n_tokens - i), 0, -1):
                raw_chunk_tokens = tokens[i : i + ngram_size]
                raw_chunk = " ".join(raw_chunk_tokens)
                norm_chunk = self._normalize_text(raw_chunk)

                if not norm_chunk:
                    continue

                lead_p, trail_p = _get_punct(raw_chunk_tokens)

                # 1. Direct Alias or Canonical Match (Highest priority)
                if norm_chunk in self.alias_map:
                    canonical = self.alias_map[norm_chunk]
                    replaced_word = f"{lead_p}{canonical}{trail_p}"
                    result_tokens.append(replaced_word)
                    replacements_made.append({
                        "original": raw_chunk,
                        "canonical": canonical,
                        "match_type": "alias_exact"
                    })
                    i += ngram_size
                    matched = True
                    break

                # Skip fuzzy/phonetic search if all words in chunk are common English conversational stopwords
                chunk_words = set(norm_chunk.split())
                if chunk_words.issubset(STOPWORDS):
                    continue

                # 2. Phonetic Key Match (for multi-character non-stopword chunks)
                pkey_chunk = simplified_phonetic_key(raw_chunk)
                if pkey_chunk and len(pkey_chunk) >= 5 and pkey_chunk in self.phonetic_map:
                    canonical = self.phonetic_map[pkey_chunk]
                    norm_can = self._normalize_text(canonical)
                    dist = levenshtein_distance(norm_chunk, norm_can)
                    max_allowed_dist = max(1, len(norm_chunk) // 4)
                    if dist <= max_allowed_dist:
                        replaced_word = f"{lead_p}{canonical}{trail_p}"
                        result_tokens.append(replaced_word)
                        replacements_made.append({
                            "original": raw_chunk,
                            "canonical": canonical,
                            "match_type": "phonetic_exact"
                        })
                        i += ngram_size
                        matched = True
                        break

                # 3. Fuzzy Levenshtein Distance Match on Normalized Aliases
                if len(norm_chunk) >= 6 and (ngram_size >= 2 or len(raw_chunk) >= 8):
                    best_match = None
                    best_dist = 99
                    
                    for alias, canonical in self.alias_map.items():
                        if abs(len(alias) - len(norm_chunk)) > 2:
                            continue
                        dist = levenshtein_distance(norm_chunk, alias)
                        max_dist = 1 if len(norm_chunk) < 8 else 2
                        if dist <= max_dist and dist < best_dist:
                            best_dist = dist
                            best_match = canonical

                    if best_match:
                        replaced_word = f"{lead_p}{best_match}{trail_p}"
                        result_tokens.append(replaced_word)
                        replacements_made.append({
                            "original": raw_chunk,
                            "canonical": best_match,
                            "match_type": "fuzzy_levenshtein"
                        })
                        i += ngram_size
                        matched = True
                        break

            if not matched:
                result_tokens.append(tokens[i])
                i += 1

        corrected_text = " ".join(result_tokens)
        
        # Clean up double punctuation if any
        corrected_text = re.sub(r"\s+([?.,!])", r"\1", corrected_text)
        
        if replacements_made:
            logger.info(f"EntityResolver corrected: '{transcript}' -> '{corrected_text}' (Replacements: {replacements_made})")

        return corrected_text, replacements_made
