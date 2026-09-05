package org.mcc0nnell.baudot.harness;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.TreeMap;

/**
 * Joins caller and callee role evidence after a distributed run. The aggregate
 * result distinguishes scenario success from observed call/media state.
 */
public final class EvidenceAggregator {
    private EvidenceAggregator() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("usage: EvidenceAggregator <caller-dir> <callee-dir>");
            System.exit(64);
        }
        Path callerDir = Path.of(args[0]);
        Path calleeDir = Path.of(args[1]);
        Path output = callerDir.getParent().resolve("aggregate");
        Result result = aggregate(callerDir, calleeDir, output);
        System.out.println(result.resultJson());
        if (!result.scenarioPass()) {
            System.exit(1);
        }
    }

    static Result aggregate(Path callerDir, Path calleeDir, Path output) throws IOException {
        Map<String, String> caller = readProperties(callerDir.resolve("result.properties"));
        Map<String, String> callee = readProperties(calleeDir.resolve("result.properties"));

        requireSame(caller, callee, "correlation.id");
        requireSame(caller, callee, "scenario.id");
        requireSame(caller, callee, "scenario.expectMedia");

        boolean callerEstablished = Boolean.parseBoolean(caller.getOrDefault("signaling.established", "false"));
        boolean calleeReceivedInvite = Boolean.parseBoolean(callee.getOrDefault("signaling.invite.received", "false"));
        boolean signalingPass = callerEstablished && calleeReceivedInvite;
        boolean mediaReceived = Boolean.parseBoolean(callee.getOrDefault("media.probe.received", "false"));
        boolean expectMedia = Boolean.parseBoolean(caller.getOrDefault("scenario.expectMedia", "true"));
        boolean scenarioPass = signalingPass && mediaReceived == expectMedia;

        String callState = signalingPass ? "CALL_ESTABLISHED" : "SIGNALING_FAILED";
        String mediaState = mediaReceived ? "MEDIA_RECEIVED" : "MEDIA_FAILED";

        Map<String, String> fields = new LinkedHashMap<>();
        fields.put("scenario", caller.get("scenario.id"));
        fields.put("correlation", caller.get("correlation.id"));
        fields.put("scenarioResult", scenarioPass ? "PASS" : "FAIL");
        fields.put("callState", callState);
        fields.put("mediaState", mediaState);
        fields.put("expectedMedia", Boolean.toString(expectMedia));

        Files.createDirectories(output);
        String json = EvidenceRecorder.toJson(fields);
        Files.writeString(output.resolve("result.json"), json + System.lineSeparator(), StandardCharsets.UTF_8);

        TreeMap<String, String> manifestEntries = new TreeMap<>();
        manifestEntries.put("../caller/events.jsonl", sha256(callerDir.resolve("events.jsonl")));
        manifestEntries.put("../caller/result.properties", sha256(callerDir.resolve("result.properties")));
        manifestEntries.put("../callee/events.jsonl", sha256(calleeDir.resolve("events.jsonl")));
        manifestEntries.put("../callee/result.properties", sha256(calleeDir.resolve("result.properties")));
        manifestEntries.put("result.json", sha256(output.resolve("result.json")));

        try (BufferedWriter writer = Files.newBufferedWriter(output.resolve("manifest.sha256"), StandardCharsets.UTF_8)) {
            for (Map.Entry<String, String> entry : manifestEntries.entrySet()) {
                writer.write(entry.getValue() + "  " + entry.getKey());
                writer.newLine();
            }
        }

        return new Result(scenarioPass, json);
    }

    private static Map<String, String> readProperties(Path path) throws IOException {
        Map<String, String> values = new LinkedHashMap<>();
        try (BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
            for (String line; (line = reader.readLine()) != null;) {
                if (line.isBlank() || line.startsWith("#")) {
                    continue;
                }
                int split = line.indexOf('=');
                if (split < 1) {
                    throw new IOException("Malformed evidence property in " + path + ": " + line);
                }
                values.put(line.substring(0, split), line.substring(split + 1));
            }
        }
        return values;
    }

    private static void requireSame(Map<String, String> a, Map<String, String> b, String key) throws IOException {
        String av = a.get(key);
        String bv = b.get(key);
        if (av == null || !av.equals(bv)) {
            throw new IOException("Evidence mismatch for " + key + ": " + av + " vs " + bv);
        }
    }

    private static String sha256(Path path) throws IOException {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(Files.readAllBytes(path));
            StringBuilder builder = new StringBuilder(hash.length * 2);
            for (byte b : hash) {
                builder.append(String.format("%02x", b));
            }
            return builder.toString();
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 is unavailable", e);
        }
    }

    record Result(boolean scenarioPass, String resultJson) {
    }
}
