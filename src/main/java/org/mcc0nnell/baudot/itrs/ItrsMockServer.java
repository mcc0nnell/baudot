package org.mcc0nnell.baudot.itrs;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

public final class ItrsMockServer {
    private static final int DEFAULT_PORT = 8799;

    private ItrsMockServer() {
    }

    public static void main(String[] args) throws Exception {
        int port = args.length > 0 ? Integer.parseInt(args[0]) : DEFAULT_PORT;
        InetSocketAddress bind = new InetSocketAddress(InetAddress.getLoopbackAddress(), port);
        HttpServer server = HttpServer.create(bind, 0);
        server.createContext("/health", exchange -> respond(exchange, 200,
                "{\"status\":\"ok\",\"service\":\"baudot-itrs-mock\"}"));
        server.createContext("/itrs/v1/query", ItrsMockServer::handleQuery);
        server.setExecutor(null);
        server.start();
        System.out.printf("Baudot iTRS mock listening on http://%s:%d%n",
                bind.getAddress().getHostAddress(), port);
    }

    private static void handleQuery(HttpExchange exchange) throws IOException {
        if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) {
            exchange.getResponseHeaders().set("Allow", "GET");
            respond(exchange, 405, error("method-not-allowed", "GET required"));
            return;
        }

        String number = query(exchange.getRequestURI().getRawQuery()).get("number");
        if (number == null || !number.matches("\\d{10}")) {
            respond(exchange, 400, error("invalid-number", "number must contain exactly 10 digits"));
            return;
        }

        MockResult result = fixture(number);
        if (result.delayMs > 0) {
            try {
                Thread.sleep(result.delayMs);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                respond(exchange, 503, error("mock-interrupted", "mock latency interrupted"));
                return;
            }
        }
        respond(exchange, result.status, result.body);
    }

    private static MockResult fixture(String number) {
        return switch (number) {
            case "2025550101" -> route(number, "direct-e2u-sip",
                    "sip:2025550101@vrs-a.example.invalid", null, 0);
            case "2025550102" -> route(number, "alias-then-e2u-sip",
                    "sip:2025550102@vrs-b.example.invalid", null, 0);
            case "2025550103" -> route(number, "naptr-priority-selection",
                    "sip:2025550103@primary.example.invalid", null, 0);
            case "2025550104" -> route(number, "sip-service-discovery",
                    "sip:2025550104@edge.example.invalid", "sip1.edge.example.invalid:5070", 0);
            case "2025550105" -> new MockResult(404, errorBody(number,
                    "not-found", "no authoritative iTRS route"), 0);
            case "2025550106" -> new MockResult(502, errorBody(number,
                    "invalid-authoritative-response", "authoritative E2U+sip target is malformed"), 0);
            case "2025550107" -> new MockResult(503, errorBody(number,
                    "authority-unavailable", "mock authoritative directory unavailable"), 0);
            case "2025550108" -> route(number, "slow-authority",
                    "sip:2025550108@slow.example.invalid", null, 250);
            default -> new MockResult(404, errorBody(number,
                    "fixture-not-found", "no mock fixture exists for number"), 0);
        };
    }

    private static MockResult route(String number, String fixture, String logicalSipUri,
                                    String connectTarget, long delayMs) {
        StringBuilder json = new StringBuilder();
        json.append('{')
                .append("\"status\":\"route\",")
                .append("\"source\":\"mock-itrs\",")
                .append("\"fixture\":\"").append(escape(fixture)).append("\",")
                .append("\"number\":\"").append(number).append("\",")
                .append("\"logicalSipUri\":\"").append(escape(logicalSipUri)).append("\",")
                .append("\"resolvedAt\":\"").append(Instant.EPOCH).append("\"");
        if (connectTarget != null) {
            json.append(',').append("\"connectTarget\":\"")
                    .append(escape(connectTarget)).append("\"");
        }
        json.append('}');
        return new MockResult(200, json.toString(), delayMs);
    }

    private static String error(String code, String message) {
        return "{\"status\":\"error\",\"error\":\"" + escape(code)
                + "\",\"message\":\"" + escape(message) + "\"}";
    }

    private static String errorBody(String number, String code, String message) {
        return "{\"status\":\"error\",\"source\":\"mock-itrs\",\"number\":\""
                + number + "\",\"error\":\"" + escape(code)
                + "\",\"message\":\"" + escape(message) + "\"}";
    }

    private static void respond(HttpExchange exchange, int status, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8");
        exchange.getResponseHeaders().set("Cache-Control", "no-store");
        exchange.getResponseHeaders().set("X-Baudot-Mock", "itrs-v1");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    private static Map<String, String> query(String rawQuery) {
        Map<String, String> values = new LinkedHashMap<>();
        if (rawQuery == null || rawQuery.isBlank()) {
            return values;
        }
        for (String part : rawQuery.split("&")) {
            int equals = part.indexOf('=');
            String key = equals >= 0 ? part.substring(0, equals) : part;
            String value = equals >= 0 ? part.substring(equals + 1) : "";
            values.put(URLDecoder.decode(key, StandardCharsets.UTF_8),
                    URLDecoder.decode(value, StandardCharsets.UTF_8));
        }
        return values;
    }

    private static String escape(String value) {
        return value.replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "\\r");
    }

    private record MockResult(int status, String body, long delayMs) {
    }
}
