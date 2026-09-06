package org.mcc0nnell.baudot.itrs;

import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

/** Typed client for the Baudot-owned iTRS CTE mock surface. */
public final class ItrsCteClient {
    private final String base;
    private final HttpClient client;
    public ItrsCteClient(String base) {
        this.base = base.endsWith("/") ? base.substring(0, base.length() - 1) : base;
        this.client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build();
    }
    public QueryResult allCallQuery(String providerXspid, String fromTn, String toTn,
            String service, String direction) throws Exception {
        String path = "/itrs/v2/all-call-query?providerXspid=" + enc(providerXspid)
                + "&from=" + enc(fromTn) + "&to=" + enc(toTn) + "&service=" + enc(service)
                + "&direction=" + enc(direction);
        HttpResponse<String> response = send("GET", path);
        String body = response.body();
        if (response.statusCode() != 200) throw new IllegalStateException("CTE query returned " + response.statusCode() + ": " + body);
        return new QueryResult(jsonString(body, "transactionId"), "true".equals(jsonLiteral(body, "valid")),
                "true".equals(jsonLiteral(body, "connectAllowed")), jsonStringOrNull(body, "routeUri"),
                jsonStringOrNull(body, "failure"), body);
    }
    public HttpResponse<String> provision(String actorXspid, String tn, String service, String userType,
            String uri, boolean active, long replicationDelayMs) throws Exception {
        return send("PUT", "/itrs/v2/provision?actorXspid=" + enc(actorXspid) + "&tn=" + enc(tn)
                + "&service=" + enc(service) + "&userType=" + enc(userType) + "&uri=" + enc(uri)
                + "&active=" + active + "&replicationDelayMs=" + replicationDelayMs);
    }
    public HttpResponse<String> setUrdValid(String tn, String providerXspid, String service, boolean urdValid) throws Exception {
        return send("PUT", "/itrs/v2/urd-valid?tn=" + enc(tn) + "&providerXspid=" + enc(providerXspid)
                + "&service=" + enc(service) + "&urdValid=" + urdValid);
    }
    public HttpResponse<String> record(String tn) throws Exception { return send("GET", "/itrs/v2/record?tn=" + enc(tn)); }
    private HttpResponse<String> send(String method, String path) throws Exception {
        HttpRequest.Builder builder = HttpRequest.newBuilder(URI.create(base + path)).timeout(Duration.ofSeconds(3));
        if ("PUT".equals(method)) builder.PUT(HttpRequest.BodyPublishers.noBody()); else builder.GET();
        return client.send(builder.build(), HttpResponse.BodyHandlers.ofString());
    }
    private static String enc(String value) { return URLEncoder.encode(value, StandardCharsets.UTF_8); }
    private static String jsonString(String json, String field) {
        String value = jsonStringOrNull(json, field);
        if (value == null) throw new IllegalArgumentException("Missing JSON field: " + field);
        return value;
    }
    private static String jsonStringOrNull(String json, String field) {
        String marker = "\"" + field + "\":\"";
        int start = json.indexOf(marker);
        if (start < 0) return null;
        start += marker.length();
        int end = json.indexOf('"', start);
        if (end < 0) throw new IllegalArgumentException("Unterminated JSON field: " + field);
        return json.substring(start, end);
    }
    private static String jsonLiteral(String json, String field) {
        String marker = "\"" + field + "\":";
        int start = json.indexOf(marker);
        if (start < 0) return null;
        start += marker.length();
        int end = start;
        while (end < json.length() && "truefalsenull0123456789-".indexOf(json.charAt(end)) >= 0) end++;
        return json.substring(start, end);
    }
    public record QueryResult(String transactionId, boolean valid, boolean connectAllowed,
            String routeUri, String failure, String rawBody) { }
}
