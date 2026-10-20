import json
import tempfile
import unittest
from pathlib import Path

from scripts.select_rue_provider import load_provider_list, select_provider


class RueProviderSelectionTest(unittest.TestCase):
    def fixture(self, payload: dict) -> Path:
        handle = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json", delete=False)
        with handle:
            json.dump(payload, handle)
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        return Path(handle.name)

    def test_selects_exact_normative_provider_entry_point(self):
        providers = load_provider_list(
            Path("testkit/vrs/fixtures/provider-list-v1.json")
        )
        selected = select_provider(providers, "Provider B")
        self.assertEqual("provider-b.example", selected["providerEntryPoint"])

    def test_unknown_provider_fails_closed(self):
        providers = load_provider_list(
            Path("testkit/vrs/fixtures/provider-list-v1.json")
        )
        with self.assertRaisesRegex(ValueError, "matched 0"):
            select_provider(providers, "Provider Z")

    def test_duplicate_provider_name_is_rejected(self):
        path = self.fixture(
            {
                "providers": [
                    {"name": "Provider B", "providerEntryPoint": "provider-b.example"},
                    {"name": "Provider B", "providerEntryPoint": "other-b.example"},
                ]
            }
        )
        with self.assertRaisesRegex(ValueError, "duplicate provider name"):
            load_provider_list(path)

    def test_duplicate_provider_entry_point_is_rejected(self):
        path = self.fixture(
            {
                "providers": [
                    {"name": "Provider A", "providerEntryPoint": "same.example"},
                    {"name": "Provider B", "providerEntryPoint": "same.example"},
                ]
            }
        )
        with self.assertRaisesRegex(ValueError, "duplicate providerEntryPoint"):
            load_provider_list(path)

    def test_non_normative_entry_point_field_is_rejected(self):
        path = self.fixture(
            {"providers": [{"name": "Provider A", "entryPoint": "provider-a.example"}]}
        )
        with self.assertRaisesRegex(ValueError, "normative providerEntryPoint"):
            load_provider_list(path)


if __name__ == "__main__":
    unittest.main()
