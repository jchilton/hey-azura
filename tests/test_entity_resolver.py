import sys
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.entity_resolver import EntityResolver

class TestEntityResolver(unittest.TestCase):
    def setUp(self):
        self.resolver = EntityResolver()

    def test_exact_alias_replacements(self):
        cases = [
            ("where is old rune located in varden fell?", "where is Ald'ruhn located in Vvardenfell?"),
            ("tell me about ball mora", "tell me about Balmora"),
            ("how do I get to soul steam", "how do I get to Solstheim"),
            ("tell me about the goth vermin", "tell me about Dagoth Vemyn"),
            ("where is sawed rich mora", "where is Sadrith Mora"),
            ("who rules morning hold", "who rules Mournhold"),
            ("where is fire watch in tam reel rebuilt", "where is Firewatch in Tamriel Rebuilt"),
            ("how do I reach old ebon heart", "how do I reach Old Ebonheart"),
            ("what is tell vanni house", "what is Telvanni house"),
            ("tell me about near a va reen", "tell me about Nerevarine"),
            ("who is viva", "who is Vivec"),
            ("where is saint ehrlauer", "where is Saint Aralor"),
            ("how to get to feminal", "how to get to Vemynal"),
            ("where is kogorun", "where is Kogoruhn"),
            ("tell me about roa dear in almost clear", "tell me about Roa Dyr in Almas Thirr"),
            ("where is bahn malur", "where is Baan Malur"),
            ("how to reach port tel vanis", "how to reach Port Telvannis"),
            ("who is divine fir", "who is Divayth Fyr"),
            ("where can i find khios cosades", "where can i find Caius Cosades"),
            ("tell me about you mop", "tell me about UMOPP"),
        ]

        for input_text, expected_output in cases:
            corrected, replacements = self.resolver.resolve_entities(input_text)
            self.assertEqual(corrected, expected_output, f"Failed for input: '{input_text}'")
            self.assertTrue(len(replacements) > 0, f"Expected replacements for '{input_text}'")

    def test_fuzzy_matching(self):
        cases = [
            ("where is aldrun", "where is Ald'ruhn"),
            ("how to find solstime", "how to find Solstheim"),
            ("tell me about vardenfell", "tell me about Vvardenfell"),
        ]
        for input_text, expected_output in cases:
            corrected, replacements = self.resolver.resolve_entities(input_text)
            self.assertEqual(corrected, expected_output, f"Failed fuzzy match for input: '{input_text}'")

    def test_unaffected_sentence(self):
        text = "Hello world how are you today"
        corrected, replacements = self.resolver.resolve_entities(text)
        self.assertEqual(corrected, text)
        self.assertEqual(len(replacements), 0)

if __name__ == "__main__":
    unittest.main()
