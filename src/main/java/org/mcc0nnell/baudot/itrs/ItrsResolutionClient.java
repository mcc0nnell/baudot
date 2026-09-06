package org.mcc0nnell.baudot.itrs;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

/**
 * Minimal typed client for the deterministic iTRS mock boundary.
 *
 * <p>This is a testkit client for Baudot-owned mock responses. It is not an
 * implementation of a production TRS Numbering Administrator interface.</p>
 */
public final class ItrsResolutionClient {
    private final String base;
    private final HttpClient client;

    public ItrsResolutionClient(String base) {
        this.base = base.endsWith("/") ? base.substring(0, base.length() - 1) : base;
        this.client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .build();
    }

    public ResolutionResult resolve(String number) throws Exception {
        URI uri = URI.create(base + "/itrs/v1/query?number=" + number);
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(2))
                .GET()
                .build();
        HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
        String body = response.body();

        if (response.statusCode() == 200) {
            return new ResolutionResult(
                    Outcome.ROUTE,
                    response.statusCode(),
                    jsonString(body, "logicalSipUri"),
                    null,
                    body);
        }

        String error = jsonStringOrNull(body, "error");
        Outcome outcome = switch (error == null ? "" : error) {
            case "not-found", "fixture-not-found" -> Outcome.NOT_FOUND;
            case "invalid-authoritative-response" -> Outcome.INVALID_AUTHORITY;
            case "authority-unavailable" -> Outcome.AUTHORITY_UNAVAILABLE;
            default -> Outcome.OTHER_ERROR;
        };

        return new ResolutionResult(outcome, response.statusCode(), null, error, body);
    }

    public enum Outcome {
        ROUTE,
        NOT_FOUND,
        INVALID_AUTHORITY,
        AUTHORITY_UNAVAILABLE,
        OTHER_ERROR
    }

    public record ResolutionResult(
            Outcome outcome,
            int httpStatus,
            String logicalSipUri,
            String errorCode,
            String rawBody) {

        public boolean connectAllowed() {
            return outcome == Outcome.ROUTE && logicalSipUri != null && !logicalSipUri.isBlank();
        }
    }

    static String jsonString(String json, String field) {
        String value = jsonStringOrNull(json, field);
        if (value == null) {
            throw new IllegalArgumentException("Missing JSON field: " + field);
        }
        return value;
    }

    static String jsonStringOrNull(String json, String field) {
        String marker = "\"" + field + "\":\"";
        int start = json.indexOf(marker);
        if (start < 0) {
            return null;
        }
        start += marker.length();
        int end = json.indexOf('"', start);
        if (end < 0) {
            throw new IllegalArgumentException("Unterminated JSON field: " + field);
        }
        return json.substring(start, end);
    }
}
