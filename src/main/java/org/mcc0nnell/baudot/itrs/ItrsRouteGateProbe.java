package org.mcc0nnell.baudot.itrs;

import java.util.List;

/**
 * Proves that negative iTRS outcomes fail closed before SIP signaling.
 */
public final class ItrsRouteGateProbe {
    private ItrsRouteGateProbe() {
    }

    public static void main(String[] args) throws Exception {
        String base = args.length > 0 ? args[0] : "http://127.0.0.1:8799";
        ItrsResolutionClient client = new ItrsResolutionClient(base);

        List<Case> cases = List.of(
                new Case("2025550105", ItrsResolutionClient.Outcome.NOT_FOUND),
                new Case("2025550106", ItrsResolutionClient.Outcome.INVALID_AUTHORITY),
                new Case("2025550107", ItrsResolutionClient.Outcome.AUTHORITY_UNAVAILABLE)
        );

        int passed = 0;
        for (Case testCase : cases) {
            ItrsResolutionClient.ResolutionResult result = client.resolve(testCase.number());
            boolean sipAttempted = result.connectAllowed();
            boolean ok = result.outcome() == testCase.expectedOutcome() && !sipAttempted;

            System.out.printf(
                    "%s outcome=%s expected=%s sipAttempted=%s %s%n",
                    testCase.number(),
                    result.outcome(),
                    testCase.expectedOutcome(),
                    sipAttempted,
                    ok ? "PASS" : "FAIL");

            if (!ok) {
                throw new IllegalStateException(
                        "Route gate failed for " + testCase.number() + ": " + result.rawBody());
            }
            passed++;
        }

        System.out.printf("iTRS fail-closed route gate: %d/%d PASS%n", passed, cases.size());
    }

    private record Case(String number, ItrsResolutionClient.Outcome expectedOutcome) {
    }
}
