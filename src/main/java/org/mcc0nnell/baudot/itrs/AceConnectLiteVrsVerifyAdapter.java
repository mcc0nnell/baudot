package org.mcc0nnell.baudot.itrs;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.URLDecoder;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Minimal compatibility facade for the /vrsverify/ lookup consumed by
 * the historical ACE Connect Lite server.js implementation.
 *
 * <p>This translates the Baudot-owned CTE route decision into only the JSON
 * fields the public ACE consumer is observed reading. It is not an
 * implementation of the original verifier service.</p>
 */
public final class AceConnectLiteVrsVerifyAdapter {
    private static final int DEFAULT_PORT = 8801;
    private final String cteBase;
    private final HttpClient client;
    private final AtomicLong requests = new AtomicLong();
    private final AtomicLong successes = new AtomicLong();
    private final AtomicLong failures = new AtomicLong();
    private volatile String lastNumber;
    private volatile boolean lastRoutable;

    private AceConnectLiteVrsVerifyAdapter(String cteBase) {
        this.cteBase = cteBase.endsWith("/") ? cteBase.substring(0, cteBase.length() - 1) : cteBase;
        this.client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build();
    }

    public static void main(String[] args) throws Exception {
        int port = args.length > 0 ? Integer.parseInt(args[0]) : DEFAULT_PORT;
        String cteBase = args.length > 1 ? args[1] : "http://127.0.0.1:8800";
        new AceConnectLiteVrsVerifyAdapter(cteBase).start(port);
    }

    private void start(int port) throws IOException {
        InetSocketAddress bind = new InetSocketAddress(InetAddress.getLoopbackAddress(), port);
        HttpServer server = HttpServer.create(bind, 0);
        server.createContext("/health", exchange -> respond(exchange, 200,
                "{\"status\":\"ok\",\"service\":\"baudot-ace-vrsverify-adapter\"}"));
        server.createContext("/stats", this::handleStats);
        server.createContext("/vrsverify/", this::handleVrsVerify);
        server.setExecutor(null);
        server.start();
        System.out.printf("Baudot ACE /vrsverify/ adapter listening on http://%s:%d -> %s%n",
                bind.getAddress().getHostAddress(), port, cteBase);
    }

    private void handleStats(HttpExchange exchange) throws IOException {
        if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) {
            exchange.getResponseHeaders().set("Allow", "GET");
            respond(exchange, 405, "{\"status\":\"error\",\"failure\":\"METHOD_NOT_ALLOWED\"}");
            return;
        }
        String number = lastNumber;
        StringBuilder json = new StringBuilder("{\"status\":\"stats\"")
                .append(",\"requests\":").append(requests.get())
                .append(",\"successes\":").append(successes.get())
                .append(",\"failures\":").append(failures.get())
                .append(",\"lastRoutable\":").append(lastRoutable);
        if (number != null) {
            json.append(",\"lastNumber\":\"").append(escape(number)).append("\"");
        }
        json.append('}');
        respond(exchange, 200, json.toString());
    }

    private void handleVrsVerify(HttpExchange exchange) throws IOException {
        if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) {
            exchange.getResponseHeaders().set("Allow", "GET");
            respond(exchange, 405, failure());
            return;
        }
        String number = query(exchange).get("vrsnum");
        requests.incrementAndGet();
        lastNumber = number;
        if (number == null || !number.matches("\\d{10}")) {
            failures.incrementAndGet();
            lastRoutable = false;
            respond(exchange, 200, failure());
            return;
        }

        boolean routable = false;
        try {
            URI uri = URI.create(cteBase + "/itrs/v1/query?number="
                    + URLEncoder.encode(number, StandardCharsets.UTF_8));
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(2)).GET().build();
            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
            routable = response.statusCode() == 200;
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        } catch (Exception ignored) {
            // The compatibility contract is fail-closed: a failed CTE lookup is not a VRS success.
        }

        lastRoutable = routable;
        if (routable) {
            successes.incrementAndGet();
            respond(exchange, 200, "{\"message\":\"success\",\"data\":[{\"vrs\":\""
                    + escape(number) + "\"}]}");
        } else {
            failures.incrementAndGet();
            respond(exchange, 200, failure());
        }
    }

    private static String failure() {
        return "{\"message\":\"failure\",\"data\":[]}";
    }

    private static Map<String, String> query(HttpExchange exchange) {
        Map<String, String> values = new LinkedHashMap<>();
        String rawQuery = exchange.getRequestURI().getRawQuery();
        if (rawQuery == null || rawQuery.isBlank()) return values;
        for (String part : rawQuery.split("&")) {
            int equals = part.indexOf('=');
            String key = equals >= 0 ? part.substring(0, equals) : part;
            String value = equals >= 0 ? part.substring(equals + 1) : "";
            values.put(URLDecoder.decode(key, StandardCharsets.UTF_8),
                    URLDecoder.decode(value, StandardCharsets.UTF_8));
        }
        return values;
    }

    private static void respond(HttpExchange exchange, int status, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8");
        exchange.getResponseHeaders().set("Cache-Control", "no-store");
        exchange.getResponseHeaders().set("X-Baudot-Adapter", "ace-connect-lite-vrsverify-v1");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) { out.write(bytes); }
    }

    private static String escape(String value) {
        return value.replace("\\", "\\\\").replace("\"", "\\\"");
    }
}
