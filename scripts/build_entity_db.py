#!/usr/bin/env python3
"""
UESP Article Title Extractor & Entity Database Builder
Queries UESP MediaWiki API to fetch all places, NPCs, items, factions, quests, and lore entries
for Morrowind, Bloodmoon, Tribunal, and Tamriel Rebuilt, dumping canonical names into data/morrowind_entities.json.
"""

import os
import sys
import json
import time
import re
import logging
import requests
from typing import Set, Dict, List, Any, Optional

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("build_entity_db")

API_URL = "https://en.uesp.net/w/api.php"
HEADERS = {
    "User-Agent": "MorrowindAzuraCompanionEntityBuilder/1.0 (https://github.com/hey-azura)"
}

# Core curated seed entities with explicit phonetic aliases
SEED_ENTITIES = [
    {
      "canonical": "Ald'ruhn",
      "aliases": ["old rune", "aldrun", "ald ruhn", "all drawn", "old ruin", "ald ruun"]
    },
    {
      "canonical": "Balmora",
      "aliases": ["ball mora", "bel mora", "bell mora", "bal mora", "ballmora"]
    },
    {
      "canonical": "Solstheim",
      "aliases": ["soul steam", "solstime", "solsthiem", "soul stheim", "solstein", "soul stein"]
    },
    {
      "canonical": "Sadrith Mora",
      "aliases": ["sawed rich mora", "sawd rich mora", "sad rich mora", "sadrith more a", "sadrith morah"]
    },
    {
      "canonical": "Vvardenfell",
      "aliases": ["varden fell", "vardenfell", "barren fell", "warden fell", "varden fel"]
    },
    {
      "canonical": "Dagoth Ur",
      "aliases": ["da goth ur", "day goth er", "daygoth err", "da goth er", "day goth ur"]
    },
    {
      "canonical": "Dagoth Vemyn",
      "aliases": ["the goth vermin", "da goth vemyn", "daygoth vemyn", "dagoth vermin"]
    },
    {
      "canonical": "Dagoth Odros",
      "aliases": ["da goth odros", "daygoth odros", "dagoth address"]
    },
    {
      "canonical": "Dagoth Endus",
      "aliases": ["da goth endus", "dagoth endis"]
    },
    {
      "canonical": "Dagoth Tureynul",
      "aliases": ["da goth tureynul", "dagoth trainul"]
    },
    {
      "canonical": "Dagoth Gilvoth",
      "aliases": ["da goth gilvoth", "dagoth kill voth"]
    },
    {
      "canonical": "Dagoth Gares",
      "aliases": ["da goth gares", "dagoth garris"]
    },
    {
      "canonical": "Vivec",
      "aliases": ["viva", "viveck", "veevic", "vi vec"]
    },
    {
      "canonical": "Almalexia",
      "aliases": ["alma alexia", "elma lexia", "alma lexia"]
    },
    {
      "canonical": "Sotha Sil",
      "aliases": ["so tha sil", "south a sil", "sotha sill", "southa sil"]
    },
    {
      "canonical": "Nerevarine",
      "aliases": ["near a va reen", "nevarine", "neverin", "near a varine", "nerevarin"]
    },
    {
      "canonical": "Telvanni",
      "aliases": ["tell vanni", "tell vonny", "tel vanni", "tel vanny"]
    },
    {
      "canonical": "Redoran",
      "aliases": ["red oran", "red auron", "redoran", "red orin"]
    },
    {
      "canonical": "Hlaalu",
      "aliases": ["ha lu", "lah lu", "huh luh", "halu", "hla lu"]
    },
    {
      "canonical": "Mournhold",
      "aliases": ["mourn hold", "morning hold", "mourn old"]
    },
    {
      "canonical": "Firewatch",
      "aliases": ["fire watch", "fire-watch"]
    },
    {
      "canonical": "Necrom",
      "aliases": ["knee crom", "neck rom", "necro m"]
    },
    {
      "canonical": "Old Ebonheart",
      "aliases": ["old ebon heart", "old ebon-heart"]
    },
    {
      "canonical": "Andothren",
      "aliases": ["an dothren", "ann dothren", "and o thren"]
    },
    {
      "canonical": "Almas Thirr",
      "aliases": ["almost clear", "almas thir", "almas fear"]
    },
    {
      "canonical": "Roa Dyr",
      "aliases": ["roa dear", "row a dear", "roa deer", "row deer"]
    },
    {
      "canonical": "Baan Malur",
      "aliases": ["bahn malur", "ban malur", "baal malur"]
    },
    {
      "canonical": "Port Telvannis",
      "aliases": ["port tel vanis", "port tell vanni", "port telvanni"]
    },
    {
      "canonical": "Tamriel Rebuilt",
      "aliases": ["tam reel rebuilt", "tamriel re-built", "tamriel re built"]
    },
    {
      "canonical": "Seyda Neen",
      "aliases": ["say da neen", "sayda neen", "cedar neen", "cedar nene"]
    },
    {
      "canonical": "Pelagiad",
      "aliases": ["pela giad", "pelagied", "plagiad"]
    },
    {
      "canonical": "Ebonheart",
      "aliases": ["ebon heart", "evan heart"]
    },
    {
      "canonical": "Suran",
      "aliases": ["su ran", "siran"]
    },
    {
      "canonical": "Gnisis",
      "aliases": ["nee sis", "gni sis", "nisis"]
    },
    {
      "canonical": "Maar Gan",
      "aliases": ["mar gan", "mar gone"]
    },
    {
      "canonical": "Tel Aruhn",
      "aliases": ["tell aruhn", "tel arun", "tell arun"]
    },
    {
      "canonical": "Tel Mora",
      "aliases": ["tell mora", "tel more a"]
    },
    {
      "canonical": "Tel Branora",
      "aliases": ["tell branora", "tel branora"]
    },
    {
      "canonical": "Tel Vos",
      "aliases": ["tell vos", "tel foss"]
    },
    {
      "canonical": "Gnaar Mok",
      "aliases": ["nar mok", "gnaar mock", "gnar mok"]
    },
    {
      "canonical": "Hla Oad",
      "aliases": ["hla ode", "lah oad", "hla old"]
    },
    {
      "canonical": "Dagon Fel",
      "aliases": ["day gon fell", "dagon fell"]
    },
    {
      "canonical": "Khuul",
      "aliases": ["cool", "khool"]
    },
    {
      "canonical": "Kogoruhn",
      "aliases": ["kogorun", "kogo ruhn", "co go run"]
    },
    {
      "canonical": "Vemynal",
      "aliases": ["feminal", "veminal", "vemy nal"]
    },
    {
      "canonical": "Odrosal",
      "aliases": ["address al", "odro sal"]
    },
    {
      "canonical": "Ghostfence",
      "aliases": ["ghost fence", "ghost-fence"]
    },
    {
      "canonical": "Red Mountain",
      "aliases": ["red mountain"]
    },
    {
      "canonical": "Cavern of the Incarnate",
      "aliases": ["cavern of incarnate", "cavern of the incarnat"]
    },
    {
      "canonical": "Moon-and-Star",
      "aliases": ["moon and star", "moon & star"]
    },
    {
      "canonical": "Boots of Blinding Speed",
      "aliases": ["boots of blinding speed"]
    },
    {
      "canonical": "Wraithguard",
      "aliases": ["wraith guard", "rayth guard"]
    },
    {
      "canonical": "Keening",
      "aliases": ["key ning", "keen ing"]
    },
    {
      "canonical": "Sunder",
      "aliases": ["sun der", "son der"]
    },
    {
      "canonical": "Caius Cosades",
      "aliases": ["khios cosades", "kayus cosades", "caius casades"]
    },
    {
      "canonical": "Divayth Fyr",
      "aliases": ["divine fir", "divaith fear", "divayth fear", "di vaith fear"]
    },
    {
      "canonical": "Yagrum Bagarn",
      "aliases": ["yagrum bagarn", "yagrum bargan"]
    },
    {
      "canonical": "Nelgirion the Venerable",
      "aliases": ["nel girion the venerable", "knel girion"]
    },
    {
      "canonical": "Saint Aralor",
      "aliases": ["saint ehrlauer", "saint air laur", "st aralor", "st. aralor"]
    },
    {
      "canonical": "Saint Nerevar",
      "aliases": ["st nerevar", "st. nerevar", "saint nevar"]
    },
    {
      "canonical": "Saint Olms",
      "aliases": ["st olms", "st. olms", "saint holms"]
    },
    {
      "canonical": "Saint Delyn",
      "aliases": ["st delyn", "st. delyn", "saint delin"]
    },
    {
      "canonical": "Saint Felms",
      "aliases": ["st felms", "st. felms", "saint phelms"]
    },
    {
      "canonical": "Saint Roris",
      "aliases": ["st roris", "st. roris"]
    },
    {
      "canonical": "Saint Meris",
      "aliases": ["st meris", "st. meris"]
    },
    {
      "canonical": "Saint Rilms",
      "aliases": ["st rilms", "st. rilms"]
    },
    {
      "canonical": "Saint Seryn",
      "aliases": ["st seryn", "st. seryn"]
    },
    {
      "canonical": "Saint Veloth",
      "aliases": ["st veloth", "st. veloth"]
    },
    {
      "canonical": "Urshilaku",
      "aliases": ["earth she locku", "ur shi la ku", "urshilaku camp"]
    },
    {
      "canonical": "Ahemmusa",
      "aliases": ["ah hem musa", "a hem musa"]
    },
    {
      "canonical": "Zainab",
      "aliases": ["zay nab", "zy nab"]
    },
    {
      "canonical": "Erabenimsun",
      "aliases": ["era ben im sun", "erabenim sun"]
    },
    {
      "canonical": "Poison Song",
      "aliases": ["poison song"]
    },
    {
      "canonical": "UMOPP",
      "aliases": ["you mop", "u mop", "u m o p p"]
    },
    {
      "canonical": "Firemoth",
      "aliases": ["fire moth"]
    },
    {
      "canonical": "Raven Rock",
      "aliases": ["raven rock"]
    },
    {
      "canonical": "Skaal Village",
      "aliases": ["skaal village", "skall village"]
    }
]

CATEGORIES_TO_HARVEST = [
    # Morrowind
    "Category:Morrowind-Places",
    "Category:Morrowind-NPCs",
    "Category:Morrowind-Quests",
    "Category:Morrowind-Items",
    "Category:Morrowind-Factions",
    "Category:Morrowind-Creatures",
    "Category:Morrowind-Deities",
    # Bloodmoon & Tribunal
    "Category:Bloodmoon-Places",
    "Category:Bloodmoon-NPCs",
    "Category:Bloodmoon-Quests",
    "Category:Tribunal-Places",
    "Category:Tribunal-NPCs",
    "Category:Tribunal-Quests",
    # Tamriel Rebuilt
    "Category:Tamriel_Rebuilt-Places",
    "Category:Tamriel_Rebuilt-NPCs",
    "Category:Tamriel_Rebuilt-Quests",
    "Category:Tamriel_Rebuilt-Items",
    "Category:Tamriel_Rebuilt-Factions",
]

PREFIXES_TO_HARVEST = [
    "Morrowind:",
    "Tamriel Rebuilt:",
    "Bloodmoon:",
    "Tribunal:",
]

def fetch_category_members(category_name: str, max_items: int = 1500) -> Set[str]:
    """Fetch all page titles in a UESP category."""
    titles = set()
    cmcontinue = None
    logger.info(f"Harvesting category '{category_name}'...")

    while len(titles) < max_items:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": category_name,
            "cmlimit": "500",
            "format": "json"
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue

        try:
            r = requests.get(API_URL, params=params, headers=HEADERS, timeout=10)
            if r.status_code != 200:
                break
            data = r.json()
            members = data.get("query", {}).get("categorymembers", [])
            for m in members:
                title = m.get("title", "")
                if title:
                    titles.add(title)
            if "continue" in data and "cmcontinue" in data["continue"]:
                cmcontinue = data["continue"]["cmcontinue"]
                time.sleep(0.05)
            else:
                break
        except Exception as e:
            logger.error(f"Error fetching category {category_name}: {e}")
            break

    logger.info(f"Retrieved {len(titles)} titles from '{category_name}'.")
    return titles

def fetch_allpages_prefix(prefix: str, max_items: int = 2500) -> Set[str]:
    """Fetch all page titles under a UESP prefix (e.g. Morrowind: or Tamriel Rebuilt:)."""
    titles = set()
    apcontinue = None
    logger.info(f"Harvesting all pages with prefix '{prefix}'...")

    while len(titles) < max_items:
        params = {
            "action": "query",
            "list": "allpages",
            "apprefix": prefix,
            "aplimit": "500",
            "format": "json"
        }
        if apcontinue:
            params["apcontinue"] = apcontinue

        try:
            r = requests.get(API_URL, params=params, headers=HEADERS, timeout=10)
            if r.status_code != 200:
                break
            data = r.json()
            pages = data.get("query", {}).get("allpages", [])
            for p in pages:
                title = p.get("title", "")
                if title:
                    titles.add(title)
            if "continue" in data and "apcontinue" in data["continue"]:
                apcontinue = data["continue"]["apcontinue"]
                time.sleep(0.05)
            else:
                break
        except Exception as e:
            logger.error(f"Error fetching prefix {prefix}: {e}")
            break

    logger.info(f"Retrieved {len(titles)} titles for prefix '{prefix}'.")
    return titles

def clean_entity_title(raw_title: str) -> Optional[str]:
    """Clean UESP title into a canonical proper noun."""
    title = raw_title.strip()
    
    # Ignore Category:, User:, Template:, Talk:, File: pages
    if any(title.startswith(p) for p in ["Category:", "User:", "Template:", "Talk:", "File:", "UESPWiki:"]):
        return None

    # Strip namespace prefixes
    for ns in ["Morrowind:", "Tamriel Rebuilt:", "TR:", "Bloodmoon:", "Tribunal:", "Lore:"]:
        if title.startswith(ns):
            title = title[len(ns):].strip()

    # Ignore subpage walkthroughs or meta pages like "Quests/Main Quest"
    if "/" in title and any(kw in title for kw in ["Quests", "Walkthrough", "Map"]):
        return None

    # Strip disambiguation brackets like "Balmora (city)" or "Dagoth Vemyn (NPC)"
    title = re.sub(r"\s*\([^)]*\)", "", title).strip()

    # Ignore numbers only or very short general words
    if len(title) < 2 or title.isdigit():
        return None

    return title

def update_entity_database():
    """Harvest titles from UESP categories & prefixes and dump into data/morrowind_entities.json."""
    existing_entities_path = os.path.join(PROJECT_ROOT, "data", "morrowind_entities.json")
    
    # Seed entity dictionary
    seed_map: Dict[str, List[str]] = {}
    for seed in SEED_ENTITIES:
        seed_map[seed["canonical"].lower()] = seed.get("aliases", [])

    all_raw_titles = set()
    for cat in CATEGORIES_TO_HARVEST:
        all_raw_titles.update(fetch_category_members(cat))

    for pfx in PREFIXES_TO_HARVEST:
        all_raw_titles.update(fetch_allpages_prefix(pfx))

    canonical_names = set()
    for raw in all_raw_titles:
        cleaned = clean_entity_title(raw)
        if cleaned:
            canonical_names.add(cleaned)

    # Always preserve seed entities
    for seed in SEED_ENTITIES:
        canonical_names.add(seed["canonical"])

    logger.info(f"Total cleaned canonical entity titles gathered: {len(canonical_names)}")

    sorted_canonicals = sorted(list(canonical_names), key=lambda s: s.lower())

    entity_objects = []
    for can in sorted_canonicals:
        aliases = list(seed_map.get(can.lower(), []))
        
        # Auto-generate apostrophe/hyphen variant if applicable
        clean_alias = re.sub(r"[^\w\s]", " ", can).strip()
        clean_alias = " ".join(clean_alias.split())
        if clean_alias and clean_alias.lower() != can.lower() and clean_alias.lower() not in [a.lower() for a in aliases]:
            aliases.append(clean_alias)

        obj = {"canonical": can}
        if aliases:
            obj["aliases"] = aliases
        entity_objects.append(obj)

    out_data = {"entities": entity_objects}
    with open(existing_entities_path, "w", encoding="utf-8") as f:
        json.dump(out_data, f, indent=2, ensure_ascii=False)

    logger.info(f"Successfully saved {len(entity_objects)} entities to {existing_entities_path}!")

if __name__ == "__main__":
    update_entity_database()
