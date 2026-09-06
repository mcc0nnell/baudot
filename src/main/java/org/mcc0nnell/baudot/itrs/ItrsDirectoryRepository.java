package org.mcc0nnell.baudot.itrs;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicLong;

public final class ItrsDirectoryRepository {
    private final Map<String, DirectoryRecord> provisioning = new LinkedHashMap<>();
    private final Map<String, DirectoryRecord> queryReplica = new LinkedHashMap<>();
    private final Map<String, PendingReplica> pendingReplica = new LinkedHashMap<>();
    private final Map<String, String> reverseBindings = new LinkedHashMap<>();
    private final AtomicLong transactionSequence = new AtomicLong();
    private final AtomicLong reverseSequence = new AtomicLong();

    public ItrsDirectoryRepository() { seed(); }

    public synchronized QueryDecision allCallQuery(String requesterXspid, String fromTn,
            String toTn, String service, String direction) {
        materializeReplica();
        String transactionId = "ACQ-RUN-%06d".formatted(transactionSequence.incrementAndGet());
        if (blank(requesterXspid) || blank(fromTn) || blank(toTn) || blank(service) || blank(direction)) {
            return QueryDecision.failure(transactionId, "INVALID_QUERY");
        }
        DirectoryRecord source = queryReplica.get(fromTn);
        if (source == null) return QueryDecision.failure(transactionId, "SOURCE_NOT_FOUND");
        if (!source.urdValid()) return QueryDecision.failure(transactionId, "SOURCE_URD_INVALID");
        if (!source.active()) return QueryDecision.failure(transactionId, "SOURCE_INACTIVE");
        if (!source.service().equals(service)) return QueryDecision.failure(transactionId, "SOURCE_SERVICE_MISMATCH");

        DirectoryRecord destination = queryReplica.get(toTn);
        if (destination == null) return QueryDecision.failure(transactionId, "DESTINATION_NOT_FOUND");
        if (!destination.urdValid()) return QueryDecision.failure(transactionId, "URD_INVALID");
        if (!destination.active()) return QueryDecision.failure(transactionId, "DESTINATION_INACTIVE");
        if (!destination.service().equals(service)) return QueryDecision.failure(transactionId, "SERVICE_MISMATCH");
        String routeUri = firstSupportedUri(destination.service(), destination.uris());
        if (routeUri == null) return QueryDecision.failure(transactionId, "INVALID_ROUTE_URI");
        return QueryDecision.route(transactionId, routeUri, destination.providerXspid(), destination.uris().size());
    }

    public synchronized ReverseDecision reverseQuery(String type, String value) {
        materializeReplica();
        String transactionId = "RQ-RUN-%06d".formatted(reverseSequence.incrementAndGet());
        if (blank(type) || blank(value)) return ReverseDecision.failure(transactionId, "INVALID_REVERSE_QUERY");
        String tn = reverseBindings.get(reverseKey(type, value));
        if (tn == null) return ReverseDecision.notRegistered(transactionId);
        DirectoryRecord record = queryReplica.get(tn);
        if (record == null || !record.urdValid()) return ReverseDecision.notRegistered(transactionId);
        return ReverseDecision.registered(transactionId, record);
    }

    public synchronized ProvisionDecision provision(ProvisionRequest request) {
        Objects.requireNonNull(request, "request");
        materializeReplica();
        if (blank(request.actorXspid()) || blank(request.tn()) || blank(request.service())
                || blank(request.userType()) || request.uris() == null || request.uris().isEmpty()) {
            return ProvisionDecision.denied("INVALID_PROVISION");
        }
        if (request.uris().stream().anyMatch(ItrsDirectoryRepository::blank)) {
            return ProvisionDecision.denied("INVALID_PROVISION");
        }
        DirectoryRecord existing = provisioning.get(request.tn());
        if (!mayProvision(request.actorXspid(), existing)) {
            return ProvisionDecision.denied("NOT_DEFAULT_PROVIDER");
        }
        boolean urdValid = existing != null && existing.urdValid();
        boolean gainingProvider = existing != null && !request.actorXspid().equals(existing.providerXspid());
        PortingObservation porting = gainingProvider || existing == null ? null : existing.porting();
        DirectoryRecord updated = new DirectoryRecord(request.tn(), request.service(), request.userType(),
                request.actorXspid(), urdValid, request.active(), request.uris(), porting);
        provisioning.put(request.tn(), updated);
        replicate(updated, request.replicationDelayMs());
        return ProvisionDecision.accepted(updated.providerXspid(), request.replicationDelayMs());
    }

    public synchronized UrdDecision applyUrdValidity(String tn, String providerXspid,
            String service, boolean urdValid) {
        materializeReplica();
        if (blank(tn) || blank(providerXspid) || blank(service)) {
            return new UrdDecision(false, "INVALID_URD_OPERATION");
        }
        DirectoryRecord existing = provisioning.get(tn);
        DirectoryRecord updated;
        if (existing == null) {
            updated = new DirectoryRecord(tn, service, "UNSPECIFIED", providerXspid,
                    urdValid, false, List.of(), null);
        } else {
            updated = new DirectoryRecord(existing.tn(), service, existing.userType(), providerXspid,
                    urdValid, existing.active(), existing.uris(), existing.porting());
        }
        provisioning.put(tn, updated);
        queryReplica.put(tn, updated);
        pendingReplica.remove(tn);
        return new UrdDecision(true, null);
    }

    public synchronized DirectoryRecord queryRecord(String tn) {
        materializeReplica();
        return queryReplica.get(tn);
    }

    private boolean mayProvision(String actorXspid, DirectoryRecord existing) {
        if (existing == null) return true;
        if (actorXspid.equals(existing.providerXspid())) return true;
        PortingObservation porting = existing.porting();
        if (porting == null) return false;
        return actorXspid.equals(porting.altSpid()) || actorXspid.equals(porting.lastAltSpid());
    }

    private void replicate(DirectoryRecord record, long delayMs) {
        if (delayMs <= 0) {
            queryReplica.put(record.tn(), record);
            pendingReplica.remove(record.tn());
            return;
        }
        pendingReplica.put(record.tn(), new PendingReplica(record, System.currentTimeMillis() + delayMs));
    }

    private void materializeReplica() {
        long now = System.currentTimeMillis();
        pendingReplica.entrySet().removeIf(entry -> {
            if (entry.getValue().visibleAtMillis() <= now) {
                queryReplica.put(entry.getKey(), entry.getValue().record());
                return true;
            }
            return false;
        });
    }

    private static String firstSupportedUri(String service, List<String> uris) {
        if (uris == null) return null;
        for (String uri : uris) if (validRouteUri(service, uri)) return uri;
        return null;
    }

    private static boolean validRouteUri(String service, String uri) {
        if (blank(uri)) return false;
        return switch (service) {
            case "VRS" -> uri.startsWith("sip:") || uri.startsWith("h323:");
            case "IP_RELAY" -> uri.startsWith("im:") || uri.startsWith("sip:");
            default -> false;
        };
    }

    private void seed() {
        add(new DirectoryRecord("2025550101", "VRS", "DEAF_HARD_OF_HEARING", "XSPID-A", true, true,
                List.of("sip:2025550101@vrs-a.example.invalid"), null));
        add(new DirectoryRecord("2025550102", "VRS", "HEARING", "XSPID-A", true, true,
                List.of("sip:2025550102@gateway.provider-a.invalid"), null));
        add(new DirectoryRecord("2025550103", "VRS", "PUBLIC_DEVICE", "XSPID-B", true, true,
                List.of("sip:2025550103@provider-b.invalid"), null));
        add(new DirectoryRecord("2025550104", "IP_RELAY", "DEAF_HARD_OF_HEARING", "XSPID-B", true, true,
                List.of("im:relay0104@provider-b.invalid"), null));
        add(new DirectoryRecord("2025550105", "VRS", "PRIVATE_DEVICE", "XSPID-A", false, false, List.of(), null));
        add(new DirectoryRecord("2025550106", "VRS", "DEAF_HARD_OF_HEARING", "XSPID-A", true, true,
                List.of("not-a-valid-uri"), null));
        add(new DirectoryRecord("2025550107", "VRS", "DEAF_HARD_OF_HEARING", "XSPID-A", true, true,
                List.of("sip:2025550107@provider-a.invalid"),
                new PortingObservation("CARRIER-1", "XSPID-B", "XSPID-A")));
        add(new DirectoryRecord("2025550108", "VRS", "DEAF_HARD_OF_HEARING", "XSPID-B", true, true,
                List.of("sip:2025550108@provider-b.invalid"), null));
        add(new DirectoryRecord("2025550109", "VRS", "DEAF_HARD_OF_HEARING", "XSPID-B", true, true,
                List.of("tel:+12025550109", "sip:2025550109@provider-b.invalid",
                        "h323:2025550109@h323.provider-b.invalid"), null));

        bindReverse("userid", "2025550102", "2025550102");
        bindReverse("ip", "192.0.2.77", "2025550103");
        bindReverse("screenname", "public-vrs-b", "2025550103");
    }

    private void add(DirectoryRecord record) {
        provisioning.put(record.tn(), record);
        queryReplica.put(record.tn(), record);
    }

    private void bindReverse(String type, String value, String tn) {
        reverseBindings.put(reverseKey(type, value), tn);
    }

    private static String reverseKey(String type, String value) {
        return type.trim().toLowerCase() + ":" + value.trim().toLowerCase();
    }

    private static boolean blank(String value) { return value == null || value.isBlank(); }

    public record DirectoryRecord(String tn, String service, String userType, String providerXspid,
            boolean urdValid, boolean active, List<String> uris, PortingObservation porting) {
        public DirectoryRecord {
            uris = uris == null ? List.of() : List.copyOf(uris);
        }
        public String primaryUri() { return firstSupportedUri(service, uris); }
    }
    public record PortingObservation(String spid, String altSpid, String lastAltSpid) { }
    public record ProvisionRequest(String actorXspid, String tn, String service, String userType,
            List<String> uris, boolean active, long replicationDelayMs) {
        public ProvisionRequest {
            uris = uris == null ? List.of() : List.copyOf(uris);
        }
    }
    public record QueryDecision(String transactionId, boolean valid, boolean connectAllowed,
            String routeUri, String destinationProviderXspid, int candidateCount, String failure) {
        static QueryDecision route(String id, String uri, String providerXspid, int candidateCount) {
            return new QueryDecision(id, true, true, uri, providerXspid, candidateCount, null);
        }
        static QueryDecision failure(String id, String failure) {
            return new QueryDecision(id, false, false, null, null, 0, failure);
        }
    }
    public record ReverseDecision(String transactionId, boolean registered, String tn,
            String providerXspid, String service, List<String> uris, String failure) {
        static ReverseDecision registered(String id, DirectoryRecord record) {
            return new ReverseDecision(id, true, record.tn(), record.providerXspid(),
                    record.service(), record.uris(), null);
        }
        static ReverseDecision notRegistered(String id) {
            return new ReverseDecision(id, false, null, null, null, List.of(), null);
        }
        static ReverseDecision failure(String id, String failure) {
            return new ReverseDecision(id, false, null, null, null, List.of(), failure);
        }
    }
    public record ProvisionDecision(boolean accepted, String failure, String providerXspid,
            long replicationDelayMs) {
        static ProvisionDecision accepted(String providerXspid, long delayMs) {
            return new ProvisionDecision(true, null, providerXspid, delayMs);
        }
        static ProvisionDecision denied(String failure) {
            return new ProvisionDecision(false, failure, null, 0);
        }
    }
    public record UrdDecision(boolean accepted, String failure) { }
    private record PendingReplica(DirectoryRecord record, long visibleAtMillis) { }
}
