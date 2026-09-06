package org.mcc0nnell.baudot.itrs;

import java.net.http.HttpResponse;
import java.util.List;

public final class ItrsCteProbe {
    private ItrsCteProbe() { }

    public static void main(String[] args) throws Exception {
        String base = args.length > 0 ? args[0] : "http://127.0.0.1:8800";
        ItrsCteClient providerA = ItrsCteClient.providerA(base);
        ItrsCteClient providerB = ItrsCteClient.providerB(base);
        ItrsCteClient urd = ItrsCteClient.urdAuthority(base);
        ItrsCteClient anonymous = ItrsCteClient.anonymous(base);

        int passed = 0;
        int total = 13;

        HttpResponse<String> aSession = providerA.session();
        HttpResponse<String> bSession = providerB.session();
        HttpResponse<String> noSession = anonymous.session();
        passed += check("provider-session-isolation", aSession.statusCode() == 200
                && aSession.body().contains("\"providerXspid\":\"XSPID-A\"")
                && bSession.statusCode() == 200
                && bSession.body().contains("\"providerXspid\":\"XSPID-B\"")
                && noSession.statusCode() == 401);

        ItrsCteClient.QueryResult route =
                providerA.allCallQuery("2025550101", "2025550103", "VRS", "OUTBOUND");
        passed += check("cross-provider-route", route.connectAllowed()
                && "sip:2025550103@provider-b.invalid".equals(route.routeUri())
                && route.transactionId() != null);

        ItrsCteClient.QueryResult urdInvalid =
                providerB.allCallQuery("2025550103", "2025550105", "VRS", "OUTBOUND");
        passed += check("urd-invalid-fails-closed", !urdInvalid.connectAllowed()
                && "URD_INVALID".equals(urdInvalid.failure()));

        ItrsCteClient.QueryResult malformed =
                providerB.allCallQuery("2025550103", "2025550106", "VRS", "OUTBOUND");
        passed += check("malformed-uri-fails-closed", !malformed.connectAllowed()
                && "INVALID_ROUTE_URI".equals(malformed.failure()));

        ItrsCteClient.QueryResult multi =
                providerA.allCallQuery("2025550101", "2025550109", "VRS", "OUTBOUND");
        passed += check("multi-uri-first-supported", multi.connectAllowed()
                && multi.candidateCount() == 3
                && "sip:2025550109@provider-b.invalid".equals(multi.routeUri()));

        ItrsCteClient.ReverseResult byUser = providerA.reverseQuery("userid", "2025550102");
        ItrsCteClient.ReverseResult byIp = providerB.reverseQuery("ip", "192.0.2.77");
        ItrsCteClient.ReverseResult missing = providerA.reverseQuery("screenname", "does-not-exist");
        passed += check("reverse-query-fixtures", byUser.registered()
                && "2025550102".equals(byUser.tn())
                && byIp.registered() && "2025550103".equals(byIp.tn())
                && !missing.registered());

        HttpResponse<String> unauthorized = providerA.provision(
                "2025550103", "VRS", "PUBLIC_DEVICE",
                "sip:2025550103@hijack.invalid", true, 0);
        passed += check("non-default-provider-denied", unauthorized.statusCode() == 403
                && unauthorized.body().contains("NOT_DEFAULT_PROVIDER"));

        HttpResponse<String> gaining = providerB.provision(
                "2025550107", "VRS", "DEAF_HARD_OF_HEARING",
                List.of("sip:2025550107@provider-b.invalid",
                        "h323:2025550107@provider-b.invalid"), true, 200);
        ItrsCteClient.QueryResult beforeReplication =
                providerA.allCallQuery("2025550101", "2025550107", "VRS", "OUTBOUND");
        Thread.sleep(260);
        ItrsCteClient.QueryResult afterReplication =
                providerA.allCallQuery("2025550101", "2025550107", "VRS", "OUTBOUND");
        passed += check("gaining-provider-and-replication", gaining.statusCode() == 202
                && "sip:2025550107@provider-a.invalid".equals(beforeReplication.routeUri())
                && "sip:2025550107@provider-b.invalid".equals(afterReplication.routeUri())
                && afterReplication.candidateCount() == 2);

        HttpResponse<String> losingAfterGain = providerA.provision(
                "2025550107", "VRS", "DEAF_HARD_OF_HEARING",
                "sip:2025550107@provider-a.invalid", true, 0);
        passed += check("losing-provider-access-revoked", losingAfterGain.statusCode() == 403
                && losingAfterGain.body().contains("NOT_DEFAULT_PROVIDER"));

        HttpResponse<String> providerPretendsUrd =
                providerA.setUrdValid("2025550110", "XSPID-A", "VRS", false);
        passed += check("provider-session-cannot-act-as-urd",
                providerPretendsUrd.statusCode() == 403
                && providerPretendsUrd.body().contains("SESSION_ROLE_DENIED"));

        HttpResponse<String> urdStub =
                urd.setUrdValid("2025550110", "XSPID-A", "VRS", false);
        HttpResponse<String> stubRecord = providerA.record("2025550110");
        passed += check("urd-can-create-inactive-stub", urdStub.statusCode() == 200
                && stubRecord.statusCode() == 200
                && stubRecord.body().contains("\"active\":false")
                && stubRecord.body().contains("\"urdValid\":false"));

        HttpResponse<String> provisionStub = providerA.provision(
                "2025550110", "VRS", "DEAF_HARD_OF_HEARING",
                "sip:2025550110@provider-a.invalid", true, 0);
        ItrsCteClient.QueryResult stillInvalid =
                providerA.allCallQuery("2025550101", "2025550110", "VRS", "OUTBOUND");
        urd.setUrdValid("2025550110", "XSPID-A", "VRS", true);
        ItrsCteClient.QueryResult nowValid =
                providerA.allCallQuery("2025550101", "2025550110", "VRS", "OUTBOUND");
        passed += check("provider-cannot-self-assert-urd-valid",
                provisionStub.statusCode() == 202
                && "URD_INVALID".equals(stillInvalid.failure())
                && nowValid.connectAllowed()
                && "sip:2025550110@provider-a.invalid".equals(nowValid.routeUri()));

        HttpResponse<String> record = providerB.record("2025550109");
        passed += check("record-exposes-uri-candidates", record.statusCode() == 200
                && record.body().contains("\"uris\":[\"tel:+12025550109\",\"sip:2025550109@provider-b.invalid\",\"h323:2025550109@h323.provider-b.invalid\"]")
                && record.body().contains("\"selectedRouteUri\":\"sip:2025550109@provider-b.invalid\""));

        System.out.printf("iTRS CTE probe: %d/%d %s%n",
                passed, total, passed == total ? "PASS" : "FAIL");
        if (passed != total) System.exit(2);
    }

    private static int check(String name, boolean passed) {
        System.out.printf("%-38s %s%n", name, passed ? "PASS" : "FAIL");
        return passed ? 1 : 0;
    }
}
