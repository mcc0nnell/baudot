package org.mcc0nnell.baudot.itrs;

import java.net.http.HttpResponse;

/** Executable contract probe for the public-evidence iTRS CTE model. */
public final class ItrsCteProbe {
    private ItrsCteProbe() { }
    public static void main(String[] args) throws Exception {
        String base = args.length > 0 ? args[0] : "http://127.0.0.1:8800";
        ItrsCteClient client = new ItrsCteClient(base);
        int passed = 0;
        int total = 8;
        ItrsCteClient.QueryResult route = client.allCallQuery("XSPID-A", "2025550101", "2025550103", "VRS", "OUTBOUND");
        passed += check("cross-provider-route", route.connectAllowed()
                && "sip:2025550103@provider-b.invalid".equals(route.routeUri()) && route.transactionId() != null);
        ItrsCteClient.QueryResult urdInvalid = client.allCallQuery("XSPID-B", "2025550103", "2025550105", "VRS", "OUTBOUND");
        passed += check("urd-invalid-fails-closed", !urdInvalid.connectAllowed() && "URD_INVALID".equals(urdInvalid.failure()));
        ItrsCteClient.QueryResult malformed = client.allCallQuery("XSPID-B", "2025550103", "2025550106", "VRS", "OUTBOUND");
        passed += check("malformed-uri-fails-closed", !malformed.connectAllowed() && "INVALID_ROUTE_URI".equals(malformed.failure()));
        HttpResponse<String> unauthorized = client.provision("XSPID-A", "2025550103", "VRS", "PUBLIC_DEVICE",
                "sip:2025550103@hijack.invalid", true, 0);
        passed += check("non-default-provider-denied", unauthorized.statusCode() == 403 && unauthorized.body().contains("NOT_DEFAULT_PROVIDER"));
        HttpResponse<String> gaining = client.provision("XSPID-B", "2025550107", "VRS", "DEAF_HARD_OF_HEARING",
                "sip:2025550107@provider-b.invalid", true, 200);
        ItrsCteClient.QueryResult beforeReplication = client.allCallQuery("XSPID-A", "2025550101", "2025550107", "VRS", "OUTBOUND");
        Thread.sleep(260);
        ItrsCteClient.QueryResult afterReplication = client.allCallQuery("XSPID-A", "2025550101", "2025550107", "VRS", "OUTBOUND");
        passed += check("gaining-provider-and-replication", gaining.statusCode() == 202
                && "sip:2025550107@provider-a.invalid".equals(beforeReplication.routeUri())
                && "sip:2025550107@provider-b.invalid".equals(afterReplication.routeUri()));
        HttpResponse<String> losingAfterGain = client.provision("XSPID-A", "2025550107", "VRS", "DEAF_HARD_OF_HEARING",
                "sip:2025550107@provider-a.invalid", true, 0);
        passed += check("losing-provider-access-revoked", losingAfterGain.statusCode() == 403
                && losingAfterGain.body().contains("NOT_DEFAULT_PROVIDER"));
        HttpResponse<String> urdStub = client.setUrdValid("2025550110", "XSPID-A", "VRS", false);
        HttpResponse<String> stubRecord = client.record("2025550110");
        passed += check("urd-can-create-inactive-stub", urdStub.statusCode() == 200 && stubRecord.statusCode() == 200
                && stubRecord.body().contains("\"active\":false") && stubRecord.body().contains("\"urdValid\":false"));
        HttpResponse<String> provisionStub = client.provision("XSPID-A", "2025550110", "VRS", "DEAF_HARD_OF_HEARING",
                "sip:2025550110@provider-a.invalid", true, 0);
        ItrsCteClient.QueryResult stillInvalid = client.allCallQuery("XSPID-A", "2025550101", "2025550110", "VRS", "OUTBOUND");
        client.setUrdValid("2025550110", "XSPID-A", "VRS", true);
        ItrsCteClient.QueryResult nowValid = client.allCallQuery("XSPID-A", "2025550101", "2025550110", "VRS", "OUTBOUND");
        passed += check("provider-cannot-self-assert-urd-valid", provisionStub.statusCode() == 202
                && "URD_INVALID".equals(stillInvalid.failure()) && nowValid.connectAllowed()
                && "sip:2025550110@provider-a.invalid".equals(nowValid.routeUri()));
        System.out.printf("iTRS CTE probe: %d/%d %s%n", passed, total, passed == total ? "PASS" : "FAIL");
        if (passed != total) System.exit(2);
    }
    private static int check(String name, boolean passed) {
        System.out.printf("%-38s %s%n", name, passed ? "PASS" : "FAIL");
        return passed ? 1 : 0;
    }
}
