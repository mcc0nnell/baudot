from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.elixip_oracle_admission import (
    AdmissionError,
    EXPECTED_COMMIT,
    EXPECTED_REPOSITORY,
    build_command,
    build_manifest,
    normalize_github_repository,
    validate_identity,
)


class ElixipOracleAdmissionTests(unittest.TestCase):
    def test_normalizes_https_and_ssh_origins(self) -> None:
        self.assertEqual(
            EXPECTED_REPOSITORY,
            normalize_github_repository("https://github.com/neutrino38/elixip.git"),
        )
        self.assertEqual(
            EXPECTED_REPOSITORY,
            normalize_github_repository("git@github.com:neutrino38/elixip.git"),
        )

    def test_rejects_fork_wrong_commit_and_dirty_checkout(self) -> None:
        cases = [
            dict(repository="example/elixip", commit=EXPECTED_COMMIT, dirty=False),
            dict(repository=EXPECTED_REPOSITORY, commit="0" * 40, dirty=False),
            dict(repository=EXPECTED_REPOSITORY, commit=EXPECTED_COMMIT, dirty=True),
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(AdmissionError):
                validate_identity(**case)

    def test_manifest_hashes_inputs_without_preserving_config_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scenario = root / "interop004.exs"
            config = root / "accounts.json"
            scenario.write_text("defmodule Demo do\nend\n", encoding="utf-8")
            config.write_text('{"password":"do-not-copy"}\n', encoding="utf-8")

            manifest = build_manifest(
                checkout={
                    "repository": EXPECTED_REPOSITORY,
                    "commit": EXPECTED_COMMIT,
                    "clean": True,
                    "scenarioRunnerSha256": "a" * 64,
                },
                scenario=scenario,
                config=config,
            )
            encoded = json.dumps(manifest)
            self.assertEqual("observation-only", manifest["authority"])
            self.assertFalse(manifest["execution"]["terminalVerdictAuthority"])
            self.assertTrue(manifest["scenario"]["contentPreserved"])
            self.assertFalse(manifest["config"]["contentPreserved"])
            self.assertNotIn("do-not-copy", encoded)

    def test_runner_command_keeps_external_config_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scenario = root / "s.exs"
            config = root / "c.json"
            command = build_command(scenario, config)
            self.assertEqual("mix", command[0])
            self.assertEqual("scenario", command[1])
            self.assertEqual("--config", command[2])
            self.assertEqual(str(config.resolve()), command[3])
            self.assertEqual(str(scenario.resolve()), command[4])


if __name__ == "__main__":
    unittest.main()
