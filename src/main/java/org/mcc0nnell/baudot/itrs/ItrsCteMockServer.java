package org.mcc0nnell.baudot.itrs;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;

/** Local-only Customer Test Environment style mock. */
public final class ItrsCteMockServer {
    private static final int DEFAULT_PORT = 8800;
    private final ItrsDirectoryRepository repository = new ItrsDirectoryRepository();

    public static void main(String[] args) throws Exception {
        int port = args.length > 0 ? Integer.parseInt(args[0]) : DEFAULT_PORT;
        new ItrsCteMockServer().start(port);
    }

    private void start(int port) throws IOException {
        InetSocketAddress bind = new InetSocketAddress(InetAddress.getLoopbackAddress(), port);
        HttpServer server = HttpServer.create(bind, 0);
        server.createContext("/health", exchange -> respond(exchange, 200,
                "{\"status\":\"ok\",\"service\":\"baudot-itrs-cte-mock\"}"));
        server.createContext("/itrs/v2/all-call-query", this::handleAllCallQuery);
        server.createContext("/itrs/v1/query", this::handleLegacyQuery);
        server.createContext("/itrs/v2/provision", this::handleProvision);
        server.createContext("/itrs/v2/urd-valid", this::handleUrdValidity);
        server.createContext("/itrs/v2/record", this::handleRecord);
        server.setExecutor(null);
        server.start();
        System.out.printf("Baudot iTRS CTE mock listening on http://%s:%d%n",
                bind.getAddress().getHostAddress(), port);
    }

    private void handleLegacyQuery(HttpExchange exchange) throws IOException {
        if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) { methodNotAllowed(exchange, "GET"); return; }
        String number = query(exchange).get("number");
        ItrsDirectoryRepository.QueryDecision result = repository.allCallQuery(
                "XSPID-A", "2025550101", number, "VRS", "OUTBOUND");
        if (!result.connectAllowed()) {
            respond(exchange, 404, "{\"status\":\"error\",\"source\":\"mock-itrs-cte\",\"number\":\""
                    + escape(number) + "\",\"error\":\"" + escape(result.failure()) + "\"}");
            return;
        }
        respond(exchange, 200, "{\"status\":\"route\",\"source\":\"mock-itrs-cte\",\"number\":\""
                + escape(number) + "\",\"logicalSipUri\":\"" + escape(result.routeUri())
                + "\",\"transactionId\":\"" + escape(result.transactionId()) + "\"}");
    }

    private void handleAllCallQuery(HttpExchange exchange) throws IOException {
        if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) { methodNotAllowed(exchange, "GET"); return; }
        Map<String, String> q = query(exchange);
        ItrsDirectoryRepository.QueryDecision result = repository.allCallQuery(q.get("providerXspid"),
                q.get("from"), q.get("to"), q.get("service"), q.get("direction"));
        StringBuilder json = new StringBuilder().append("{\"status\":\"query-result\"")
                .append(",\"transactionId\":\"").append(escape(result.transactionId())).append("\"")
                .append(",\"valid\":").append(result.valid())
                .append(",\"connectAllowed\":").append(result.connectAllowed());
        if (result.routeUri() != null) json.append(",\"routeUri\":\"").append(escape(result.routeUri())).append("\"");
        if (result.destinationProviderXspid() != null) json.append(",\"destinationProviderXspid\":\"").append(escape(result.destinationProviderXspid())).append("\"");
        if (result.failure() != null) json.append(",\"failure\":\"").append(escape(result.failure())).append("\"");
        json.append('}');
        respond(exchange, 200, json.toString());
    }

    private void handleProvision(HttpExchange exchange) throws IOException {
        if (!"PUT".equalsIgnoreCase(exchange.getRequestMethod())) { methodNotAllowed(exchange, "PUT"); return; }
        Map<String, String> q = query(exchange);
        long delayMs;
        try { delayMs = Long.parseLong(q.getOrDefault("replicationDelayMs", "0")); }
        catch (NumberFormatException e) { respond(exchange, 400, error("INVALID_REPLICATION_DELAY")); return; }
        ItrsDirectoryRepository.ProvisionDecision result = repository.provision(
                new ItrsDirectoryRepository.ProvisionRequest(q.get("actorXspid"), q.get("tn"), q.get("service"),
                        q.get("userType"), q.get("uri"), Boolean.parseBoolean(q.getOrDefault("active", "true")),
                        Math.max(0, delayMs)));
        if (!result.accepted()) { respond(exchange, 403, error(result.failure())); return; }
        respond(exchange, 202, "{\"status\":\"accepted\",\"providerXspid\":\"" + escape(result.providerXspid())
                + "\",\"replicationDelayMs\":" + result.replicationDelayMs() + "}");
    }

    private void handleUrdValidity(HttpExchange exchange) throws IOException {
        if (!"PUT".equalsIgnoreCase(exchange.getRequestMethod())) { methodNotAllowed(exchange, "PUT"); return; }
        Map<String, String> q = query(exchange);
        ItrsDirectoryRepository.UrdDecision result = repository.applyUrdValidity(q.get("tn"), q.get("providerXspid"),
                q.get("service"), Boolean.parseBoolean(q.getOrDefault("urdValid", "false")));
        if (!result.accepted()) { respond(exchange, 400, error(result.failure())); return; }
        respond(exchange, 200, "{\"status\":\"accepted\",\"operation\":\"urd-valid\"}");
    }

    private void handleRecord(HttpExchange exchange) throws IOException {
        if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) { methodNotAllowed(exchange, "GET"); return; }
        ItrsDirectoryRepository.DirectoryRecord record = repository.queryRecord(query(exchange).get("tn"));
        if (record == null) { respond(exchange, 404, error("NOT_FOUND")); return; }
        StringBuilder json = new StringBuilder().append("{\"status\":\"record\"")
                .append(",\"tn\":\"").append(escape(record.tn())).append("\"")
                .append(",\"service\":\"").append(escape(record.service())).append("\"")
                .append(",\"userType\":\"").append(escape(record.userType())).append("\"")
                .append(",\"providerXspid\":\"").append(escape(record.providerXspid())).append("\"")
                .append(",\"urdValid\":").append(record.urdValid()).append(",\"active\":").append(record.active());
        if (record.uri() != null) json.append(",\"uri\":\"").append(escape(record.uri())).append("\"");
        if (record.porting() != null) json.append(",\"porting\":{\"spid\":\"").append(escape(record.porting().spid()))
                .append("\",\"altSpid\":\"").append(escape(record.porting().altSpid()))
                .append("\",\"lastAltSpid\":\"").append(escape(record.porting().lastAltSpid())).append("\"}");
        json.append('}');
        respond(exchange, 200, json.toString());
    }

    private static Map<String, String> query(HttpExchange exchange) {
        Map<String, String> values = new LinkedHashMap<>();
        String rawQuery = exchange.getRequestURI().getRawQuery();
        if (rawQuery == null || rawQuery.isBlank()) return values;
        for (String part : rawQuery.split("&")) {
            int equals = part.indexOf('=');
            String key = equals >= 0 ? part.substring(0, equals) : part;
            String value = equals >= 0 ? part.substring(equals + 1) : "";
            values.put(URLDecoder.decode(key, StandardCharsets.UTF_8), URLDecoder.decode(value, StandardCharsets.UTF_8));
        }
        return values;
    }

    private static void methodNotAllowed(HttpExchange exchange, String allow) throws IOException {
        exchange.getResponseHeaders().set("Allow", allow); respond(exchange, 405, error("METHOD_NOT_ALLOWED"));
    }
    private static String error(String code) { return "{\"status\":\"error\",\"failure\":\"" + escape(code) + "\"}"; }
    private static void respond(HttpExchange exchange, int status, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8");
        exchange.getResponseHeaders().set("Cache-Control", "no-store");
        exchange.getResponseHeaders().set("X-Baudot-Mock", "itrs-cte-v2");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) { out.write(bytes); }
    }
    private static String escape(String value) {
        return value == null ? "" : value.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n").replace("\r", "\\r");
    }
}
