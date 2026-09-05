package org.mcc0nnell.baudot.harness;

import java.io.IOException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketTimeoutException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Map;
import java.util.Properties;

/**
 * Replays one canonical primary text/t140 RTP vector and independently parses
 * the bytes observed by the receiver. This is a runtime adapter proof, not a
 * complete RFC 4103 sender/receiver or a conformance claim.
 */
public final class Rfc4103RuntimeProbe {
    private Rfc4103RuntimeProbe() {
    }

    public static void main(String[] args) throws Exception {
        Config config = Config.fromEnvironment();
        int exit = switch (config.role()) {
            case SENDER -> runSender(config);
            case RECEIVER -> runReceiver(config);
        };
        System.exit(exit);
    }

    private static int runSender(Config config) throws Exception {
        Vector vector = Vector.load(config.vectorProperties());
        byte[] packet = Files.readAllBytes(config.packetFile());
        String packetSha = PrimaryT140RtpRuntime.sha256(packet);

        try (EvidenceRecorder evidence = new EvidenceRecorder(
                config.evidenceRoot(), config.scenarioId(), config.correlationId(), "rtt-sender")) {
            evidence.event("rtt.vector.loaded", Map.of(
                    "suite", vector.suiteId(),
                    "vector", vector.vectorId(),
                    "packetSha256", packetSha));

            if (!packetSha.equals(vector.packetSha256())) {
                evidence.event("rtt.vector.hash_mismatch", Map.of(
                        "expected", vector.packetSha256(),
                        "actual", packetSha));
                evidence.result(resultFields(config, vector, false, "PACKET_HASH_MISMATCH"));
                return 2;
            }

            PrimaryT140RtpRuntime.Packet parsed = PrimaryT140RtpRuntime.parse(packet, vector.payloadType());
            vector.requireMatch(parsed);

            try (DatagramSocket socket = new DatagramSocket()) {
                DatagramPacket datagram = new DatagramPacket(
                        packet,
                        packet.length,
                        InetAddress.getByName(config.targetIp()),
                        config.targetPort());
                socket.send(datagram);
            }

            evidence.event("rtt.packet.sent", Map.of(
                    "target", config.targetIp() + ":" + config.targetPort(),
                    "bytes", Integer.toString(packet.length),
                    "vector", vector.vectorId(),
                    "packetSha256", packetSha));
            evidence.result(resultFields(config, vector, true, "RTT_SENT"));
            return 0;
        }
    }

    private static int runReceiver(Config config) throws Exception {
        Vector vector = Vector.load(config.vectorProperties());
        try (EvidenceRecorder evidence = new EvidenceRecorder(
                config.evidenceRoot(), config.scenarioId(), config.correlationId(), "rtt-receiver");
             DatagramSocket socket = new DatagramSocket(new InetSocketAddress(
                     InetAddress.getByName(config.bindIp()), config.bindPort()))) {

            socket.setSoTimeout((int) config.timeout().toMillis());
            evidence.event("rtt.receiver.ready", Map.of(
                    "bind", config.bindIp() + ":" + config.bindPort(),
                    "suite", vector.suiteId(),
                    "vector", vector.vectorId()));

            byte[] buffer = new byte[65535];
            DatagramPacket datagram = new DatagramPacket(buffer, buffer.length);
            try {
                socket.receive(datagram);
            } catch (SocketTimeoutException e) {
                evidence.event("rtt.receive.timeout", Map.of(
                        "vector", vector.vectorId(),
                        "timeoutMs", Long.toString(config.timeout().toMillis())));
                evidence.result(resultFields(config, vector, false, "RTT_FAILED"));
                return config.expectRtt() ? 3 : 0;
            }

            byte[] packet = new byte[datagram.getLength()];
            System.arraycopy(datagram.getData(), datagram.getOffset(), packet, 0, packet.length);
            String packetSha = PrimaryT140RtpRuntime.sha256(packet);

            try {
                PrimaryT140RtpRuntime.Packet parsed = PrimaryT140RtpRuntime.parse(packet, vector.payloadType());
                vector.requireMatch(parsed);
                if (!packetSha.equals(vector.packetSha256())) {
                    throw new IllegalArgumentException(
                            "received packet SHA-256 diverged from canonical vector");
                }

                evidence.event("rtt.packet.received", Map.ofEntries(
                        Map.entry("source", datagram.getAddress().getHostAddress() + ":" + datagram.getPort()),
                        Map.entry("vector", vector.vectorId()),
                        Map.entry("packetSha256", packetSha),
                        Map.entry("payloadType", Integer.toString(parsed.payloadType())),
                        Map.entry("sequenceNumber", Integer.toString(parsed.sequenceNumber())),
                        Map.entry("timestamp", Long.toString(parsed.timestamp())),
                        Map.entry("ssrc", Long.toString(parsed.ssrc())),
                        Map.entry("marker", Boolean.toString(parsed.marker())),
                        Map.entry("t140blockHex", PrimaryT140RtpRuntime.hex(parsed.t140block()))));
                evidence.result(resultFields(config, vector, true, "RTT_RECEIVED"));
                return config.expectRtt() ? 0 : 4;
            } catch (IllegalArgumentException e) {
                evidence.event("rtt.packet.invalid", Map.of(
                        "vector", vector.vectorId(),
                        "packetSha256", packetSha,
                        "error", e.toString()));
                evidence.result(resultFields(config, vector, false, "RTT_INVALID"));
                return 5;
            }
        }
    }

    private static Map<String, String> resultFields(
            Config config, Vector vector, boolean observed, String state) {
        return Map.ofEntries(
                Map.entry("correlation.id", config.correlationId()),
                Map.entry("scenario.id", config.scenarioId()),
                Map.entry("scenario.expectRtt", Boolean.toString(config.expectRtt())),
                Map.entry("rtt.observed", Boolean.toString(observed)),
                Map.entry("rtt.state", state),
                Map.entry("rtt.suite", vector.suiteId()),
                Map.entry("rtt.suite.version", vector.suiteVersion()),
                Map.entry("rtt.vector", vector.vectorId()),
                Map.entry("rtt.packet.sha256", vector.packetSha256()),
                Map.entry("rtt.t140block.hex", vector.t140blockHex()));
    }

    enum Role {
        SENDER,
        RECEIVER
    }

    record Config(
            Role role,
            String scenarioId,
            String correlationId,
            Path packetFile,
            Path vectorProperties,
            String bindIp,
            int bindPort,
            String targetIp,
            int targetPort,
            boolean expectRtt,
            Duration timeout,
            Path evidenceRoot) {

        static Config fromEnvironment() {
            return new Config(
                    Role.valueOf(env("BAUDOT_RTT_ROLE", "sender").trim().toUpperCase()),
                    env("BAUDOT_SCENARIO", "003-rfc4103-primary"),
                    env("BAUDOT_CORRELATION", "runtime"),
                    Path.of(required("BAUDOT_RTT_PACKET_FILE")),
                    Path.of(required("BAUDOT_RTT_VECTOR_PROPERTIES")),
                    env("BAUDOT_RTT_BIND_IP", "127.0.0.1"),
                    envInt("BAUDOT_RTT_BIND_PORT", 41030),
                    env("BAUDOT_RTT_TARGET_IP", "127.0.0.1"),
                    envInt("BAUDOT_RTT_TARGET_PORT", 41030),
                    Boolean.parseBoolean(env("BAUDOT_EXPECT_RTT", "true")),
                    Duration.ofMillis(envInt("BAUDOT_RTT_TIMEOUT_MS", 5000)),
                    Path.of(env("BAUDOT_EVIDENCE_DIR", "target/evidence")));
        }

        private static String required(String name) {
            String value = System.getenv(name);
            if (value == null || value.isBlank()) {
                throw new IllegalArgumentException(name + " is required");
            }
            return value;
        }

        private static String env(String name, String fallback) {
            String value = System.getenv(name);
            return value == null || value.isBlank() ? fallback : value;
        }

        private static int envInt(String name, int fallback) {
            return Integer.parseInt(env(name, Integer.toString(fallback)));
        }
    }

    record Vector(
            String suiteId,
            String suiteVersion,
            String vectorId,
            String packetSha256,
            int payloadType,
            int sequenceNumber,
            long timestamp,
            long ssrc,
            boolean marker,
            String t140blockHex) {

        static Vector load(Path path) throws IOException {
            Properties p = new Properties();
            try (var reader = Files.newBufferedReader(path)) {
                p.load(reader);
            }
            return new Vector(
                    required(p, "suite.id"),
                    required(p, "suite.version"),
                    required(p, "vector.id"),
                    required(p, "packet.sha256"),
                    Integer.parseInt(required(p, "rtp.payloadType")),
                    Integer.parseInt(required(p, "rtp.sequenceNumber")),
                    Long.parseLong(required(p, "rtp.timestamp")),
                    Long.parseLong(required(p, "rtp.ssrc")),
                    Boolean.parseBoolean(required(p, "rtp.marker")),
                    required(p, "t140block.hex"));
        }

        void requireMatch(PrimaryT140RtpRuntime.Packet packet) {
            if (packet.payloadType() != payloadType
                    || packet.sequenceNumber() != sequenceNumber
                    || packet.timestamp() != timestamp
                    || packet.ssrc() != ssrc
                    || packet.marker() != marker
                    || !PrimaryT140RtpRuntime.hex(packet.t140block()).equals(t140blockHex)) {
                throw new IllegalArgumentException("runtime RTP interpretation diverged from canonical vector");
            }
        }

        private static String required(Properties p, String name) {
            String value = p.getProperty(name);
            if (value == null) {
                throw new IllegalArgumentException("missing vector property " + name);
            }
            return value;
        }
    }
}
