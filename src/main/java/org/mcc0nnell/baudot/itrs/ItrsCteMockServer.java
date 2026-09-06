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
import java.util.List;
import java.util.Map;

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
        server.createContext("/itrs/v2/session", this::handleSession);
        server.createContext("/itrs/v2/all-call-query", this::handleAllCallQuery);
        server.createContext("/itrs/v2/reverse-query", this::handleReverseQuery);
        server.createContext("/itrs/v1/query", this::handleLegacyQuery);
        server.createContext("/itrs/v2/provision", this::handleProvision);
        server.createContext("/itrs/v2/urd-valid", this::handleUrdValidity);
        server.createContext("/itrs/v2/record", this::handleRecord);
        server.setExecutor(null);
        server.start();
        System.out.printf("Baudot iTRS CTE mock listening on http://%s:%d%n",
                bind.getAddress().getHostAddress(), port);
    }

    private void handleSession(HttpExchange exchange) throws IOException {
        if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) { methodNotAllowed(exchange, "GET"); return; }
        ItrsCteSessions.Session session = requireSession(exchange, null);
        if (session == null) return;
        StringBuilder json = new StringBuilder("{\"status\":\"session\"")
                .append(",\"sessionId\":\"").append(escape(session.id())).append("\"")
                .append(",\"role\":\"").append(session.role()).append("\"");
        if (session.xspid() != null) json.append(",\"providerXspid\":\"").append(escape(session.xspid())).append("\"");
        json.append('}');
        respond(exchange, 200, json.toString());
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
        ItrsCteSessions.Session session = requireSession(exchange, ItrsCteSessions.Role.PROVIDER);
        if (session == null) return;
        Map<String, String> q = query(exchange);
        ItrsDirectoryRepository.QueryDecision result = repository.allCallQuery(session.xspid(),
                q.get("from"), q.get("to"), q.get("service"), q.get("direction"));
        StringBuilder json = new StringBuilder("{\"status\":\"query-result\"")
                .append(",\"transactionId\":\"").append(escape(result.transactionId())).append("\"")
                .append(",\"requesterXspid\":\"").append(escape(session.xspid())).append("\"")
                .append(",\"valid\":").append(result.valid())
                .append(",\"connectAllowed\":").append(result.connectAllowed())
                .append(",\"candidateCount\":").append(result.candidateCount());
        if (result.routeUri() != null) json.append(",\"routeUri\":\"").append(escape(result.routeUri())).append("\"");
        if (result.destinationProviderXspid() != null) json.append(",\"destinationProviderXspid\":\"")
                .append(escape(result.destinationProviderXspid())).append("\"");
        if (result.failure() != null) json.append(",\"failure\":\"").append(escape(result.failure())).append("\"");
        json.append('}');
        respond(exchange, 200, json.toString());
    }

    private void handleReverseQuery(HttpExchange exchange) throws IOException {
        if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) { methodNotAllowed(exchange, "GET"); return; }
        ItrsCteSessions.Session session = requireSession(exchange, ItrsCteSessions.Role.PROVIDER);
        if (session == null) return;
        Map<String, String> q = query(exchange);
        ItrsDirectoryRepository.ReverseDecision result = repository.reverseQuery(q.get("type"), q.get("value"));
        StringBuilder json = new StringBuilder("{\"status\":\"reverse-query-result\"")
                .append(",\"transactionId\":\"").append(escape(result.transactionId())).append("\"")
                .append(",\"requesterXspid\":\"").append(escape(session.xspid())).append("\"")
                .append(",\"registered\":").append(result.registered());
        if (result.tn() != null) json.append(",\"tn\":\"").append(escape(result.tn())).append("\"");
        if (result.providerXspid() != null) json.append(",\"providerXspid\":\"").append(escape(result.providerXspid())).append("\"");
        if (result.service() != null) json.append(",\"service\":\"").append(escape(result.service())).append("\"");
        if (!result.uris().isEmpty()) json.append(",\"uris\":").append(jsonArray(result.uris()));
        if (result.failure() != null) json.append(",\"failure\":\"").append(escape(result.failure())).append("\"");
        json.append('}');
        respond(exchange, 200, json.toString());
    }

    private void handleProvision(HttpExchange exchange) throws IOException {
        if (!"PUT".equalsIgnoreCase(exchange.getRequestMethod())) { methodNotAllowed(exchange, "PUT"); return; }
        ItrsCteSessions.Session session = requireSession(exchange, ItrsCteSessions.Role.PROVIDER);
        if (session == null) return;
        Map<String, String> q = query(exchange);
        long delayMs;
        try { delayMs = Long.parseLong(q.getOrDefault("replicationDelayMs", "0")); }
        catch (NumberFormatException e) { respond(exchange, 400, error("INVALID_REPLICATION_DELAY")); return; }
        List<String> uris = splitUris(q.get("uris"));
        if (uris.isEmpty() && q.get("uri") != null) uris = List.of(q.get("uri"));
        ItrsDirectoryRepository.ProvisionDecision result = repository.provision(
                new ItrsDirectoryRepository.ProvisionRequest(session.xspid(), q.get("tn"), q.get("service"),
                        q.get("userType"), uris, Boolean.parseBoolean(q.getOrDefault("active", "true")),
                        Math.max(0, delayMs)));
        if (!result.accepted()) { respond(exchange, 403, error(result.failure())); return; }
        respond(exchange, 202, "{\"status\":\"accepted\",\"providerXspid\":\"" + escape(result.providerXspid())
                + "\",\"replicationDelayMs\":" + result.replicationDelayMs() + "}");
    }

    private void handleUrdValidity(HttpExchange exchange) throws IOException {
        if (!"PUT".equalsIgnoreCase(exchange.getRequestMethod())) { methodNotAllowed(exchange, "PUT"); return; }
        ItrsCteSessions.Session session = requireSession(exchange, ItrsCteSessions.Role.URD_AUTHORITY);
        if (session == null) return;
        Map<String, String> q = query(exchange);
        ItrsDirectoryRepository.UrdDecision result = repository.applyUrdValidity(q.get("tn"), q.get("providerXspid"),
                q.get("service"), Boolean.parseBoolean(q.getOrDefault("urdValid", "false")));
        if (!result.accepted()) { respond(exchange, 400, error(result.failure())); return; }
        respond(exchange, 200, "{\"status\":\"accepted\",\"operation\":\"urd-valid\"}");
    }

    private void handleRecord(HttpExchange exchange) throws IOException {
        if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) { methodNotAllowed(exchange, "GET"); return; }
        ItrsCteSessions.Session session = requireSession(exchange, ItrsCteSessions.Role.PROVIDER);
        if (session == null) return;
        ItrsDirectoryRepository.DirectoryRecord record = repository.queryRecord(query(exchange).get("tn"));
        if (record == null) { respond(exchange, 404, error("NOT_FOUND")); return; }
        StringBuilder json = new StringBuilder("{\"status\":\"record\"")
                .append(",\"tn\":\"").append(escape(record.tn())).append("\"")
                .append(",\"service\":\"").append(escape(record.service())).append("\"")
                .append(",\"userType\":\"").append(escape(record.userType())).append("\"")
                .append(",\"providerXspid\":\"").append(escape(record.providerXspid())).append("\"")
                .append(",\"urdValid\":").append(record.urdValid()).append(",\"active\":").append(record.active())
                .append(",\"uris\":").append(jsonArray(record.uris()));
        if (record.primaryUri() != null) json.append(",\"selectedRouteUri\":\"").append(escape(record.primaryUri())).append("\"");
        if (record.porting() != null) json.append(",\"porting\":{\"spid\":\"").append(escape(record.porting().spid()))
                .append("\",\"altSpid\":\"").append(escape(record.porting().altSpid()))
                .append("\",\"lastAltSpid\":\"").append(escape(record.porting().lastAltSpid())).append("\"}");
        json.append('}');
        respond(exchange, 200, json.toString());
    }

    private static ItrsCteSessions.Session requireSession(HttpExchange exchange,
            ItrsCteSessions.Role requiredRole) throws IOException {
        ItrsCteSessions.Session session = ItrsCteSessions.authenticate(exchange.getRequestHeaders().getFirst("Authorization"));
        if (session == null) {
            exchange.getResponseHeaders().set("WWW-Authenticate", "Bearer realm=\"baudot-itrs-cte\"");
            respond(exchange, 401, error("UNAUTHENTICATED"));
            return null;
        }
        if (requiredRole != null && session.role() != requiredRole) {
            respond(exchange, 403, error("SESSION_ROLE_DENIED"));
            return null;
        }
        return session;
    }

    private static List<String> splitUris(String raw) {
        if (raw == null || raw.isBlank()) return List.of();
        return java.util.Arrays.stream(raw.split("\\|", -1))
                .map(String::trim).filter(v -> !v.isEmpty()).toList();
    }

    private static String jsonArray(List<String> values) {
        StringBuilder json = new StringBuilder("[");
        for (int i = 0; i < values.size(); i++) {
            if (i > 0) json.append(',');
            json.append('"').append(escape(values.get(i))).append('"');
        }
        return json.append(']').toString();
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

    private static void methodNotAllowed(HttpExchange exchange, String allow) throws IOException {
        exchange.getResponseHeaders().set("Allow", allow);
        respond(exchange, 405, error("METHOD_NOT_ALLOWED"));
    }

    private static String error(String code) {
        return "{\"status\":\"error\",\"failure\":\"" + escape(code) + "\"}";
    }

    private static void respond(HttpExchange exchange, int status, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8");
        exchange.getResponseHeaders().set("Cache-Control", "no-store");
        exchange.getResponseHeaders().set("X-Baudot-Mock", "itrs-cte-v3");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) { out.write(bytes); }
    }

    private static String escape(String value) {
        return value == null ? "" : value.replace("\\", "\\\\").replace("\"", "\\\"")
                .replace("\n", "\\n").replace("\r", "\\r");
    }
}
