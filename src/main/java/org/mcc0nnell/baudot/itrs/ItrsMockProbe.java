package org.mcc0nnell.baudot.itrs;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;

public final class ItrsMockProbe {
    private ItrsMockProbe() {
    }

    public static void main(String[] args) throws Exception {
        String base = args.length > 0 ? args[0] : "http://127.0.0.1:8799";
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .build();

        List<Case> cases = List.of(
                new Case("2025550101", 200, "sip:2025550101@vrs-a.example.invalid"),
                new Case("2025550102", 200, "sip:2025550102@vrs-b.example.invalid"),
                new Case("2025550103", 200, "sip:2025550103@primary.example.invalid"),
                new Case("2025550104", 200, "sip1.edge.example.invalid:5070"),
                new Case("2025550105", 404, "not-found"),
                new Case("2025550106", 502, "invalid-authoritative-response"),
                new Case("2025550107", 503, "authority-unavailable"),
                new Case("2025550108", 200, "sip:2025550108@slow.example.invalid")
        );

        int passed = 0;
        for (Case testCase : cases) {
            URI uri = URI.create(base + "/itrs/v1/query?number=" + testCase.number());
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(2))
                    .GET()
                    .build();
            HttpResponse<String> response = client.send(request,
                    HttpResponse.BodyHandlers.ofString());

            boolean ok = response.statusCode() == testCase.expectedStatus()
                    && response.body().contains(testCase.expectedFragment());

            System.out.printf("%-12s status=%d expected=%d %s%n",
                    testCase.number(), response.statusCode(), testCase.expectedStatus(),
                    ok ? "PASS" : "FAIL");

            if (!ok) {
                System.err.println(response.body());
                throw new IllegalStateException("iTRS mock probe failed for " + testCase.number());
            }
            passed++;
        }

        System.out.printf("iTRS mock probe: %d/%d PASS%n", passed, cases.size());
    }

    private record Case(String number, int expectedStatus, String expectedFragment) {
    }
}
