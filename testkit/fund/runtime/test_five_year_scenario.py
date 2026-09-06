from decimal import Decimal
from pathlib import Path
import unittest

from scenario import replay_scenario


class FiveYearSyntheticScenarioTests(unittest.TestCase):
    def test_five_year_fixture_replays_to_declared_reconciled_state(self):
        fixture = Path(__file__).with_name("five-year-synthetic.json")
        payload, state = replay_scenario(fixture)
        expected = payload["expectedFinalState"]

        self.assertEqual(state.program_year, expected["programYear"])
        self.assertEqual(state.cash, Decimal(expected["cash"]))
        self.assertEqual(state.contributor_receivable, Decimal(expected["contributorReceivable"]))
        self.assertEqual(state.provider_payable, Decimal(expected["providerPayable"]))
        self.assertEqual(state.contribution_revenue, Decimal(expected["contributionRevenue"]))
        self.assertEqual(state.provider_compensation_expense, Decimal(expected["providerCompensationExpense"]))
        self.assertEqual(state.closed_through, expected["closedThrough"])
        self.assertEqual(state.last_seq, expected["lastSeq"])

        self.assertEqual(state.contributor_receivable, Decimal("0"))
        self.assertEqual(state.provider_payable, Decimal("0"))

    def test_scenario_is_explicitly_synthetic(self):
        fixture = Path(__file__).with_name("five-year-synthetic.json")
        payload, _ = replay_scenario(fixture)
        boundary = payload["claimBoundary"]

        self.assertTrue(boundary["allEntityLevelTransactionsSynthetic"])
        self.assertFalse(boundary["productionRolkaLoubeDataUsed"])
        self.assertFalse(boundary["productionProviderDataUsed"])
        self.assertFalse(boundary["productionContributorDataUsed"])
        self.assertFalse(boundary["productionCompatibilityClaimed"])


if __name__ == "__main__":
    unittest.main()
