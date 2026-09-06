package org.mcc0nnell.baudot.itrs;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

/** Executable proof of the public ACE Connect Lite /vrsverify/ consumer contract. */
public final class AceConnectLiteVrsVerifyProbe {
    private AceConnectLiteVrsVerifyProbe() { }

    public static void main(String[] args) throws Exception {
        String base = args.length > 0 ? args[0] : "http://127.0.0.1:8801";
        HttpClient client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build();
        int passed = 0;
        int total = 3;

        HttpResponse<String> success = get(client, base + "/vrsverify/?vrsnum=2025550103");
        passed += check("ace-vrsverify-success-shape", success.statusCode() == 200
                && success.body().contains("\"message\":\"success\"")
                && success.body().contains("\"vrs\":\"2025550103\""));

        HttpResponse<String> invalid = get(client, base + "/vrsverify/?vrsnum=2025550105");
        passed += check("ace-vrsverify-fails-closed", invalid.statusCode() == 200
                && invalid.body().contains("\"message\":\"failure\"")
                && invalid.body().contains("\"data\":[]"));

        passed += check("ace-vrsverify-does-not-invent-route-field",
                !success.body().contains("logicalSipUri") && !success.body().contains("routeUri"));

        System.out.printf("ACE /vrsverify/ adapter probe: %d/%d %s%n",
                passed, total, passed == total ? "PASS" : "FAIL");
        if (passed != total) System.exit(2);
    }

    private static HttpResponse<String> get(HttpClient client, String uri) throws Exception {
        return client.send(HttpRequest.newBuilder(URI.create(uri)).timeout(Duration.ofSeconds(2)).GET().build(),
                HttpResponse.BodyHandlers.ofString());
    }

    private static int check(String name, boolean passed) {
        System.out.printf("%-46s %s%n", name, passed ? "PASS" : "FAIL");
        return passed ? 1 : 0;
    }
}
