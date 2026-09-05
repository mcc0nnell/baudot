package org.mcc0nnell.baudot.harness;

import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.TreeMap;
import java.util.TreeSet;

final class EvidenceRecorder implements AutoCloseable {
    private final Path directory;
    private final Path eventsPath;
    private final Path resultPath;
    private final BufferedWriter events;
    private final TreeSet<String> supplementalFiles = new TreeSet<>();
    private boolean resultWritten;

    EvidenceRecorder(Path root, String scenarioId, String correlationId, String role) throws IOException {
        this.directory = root.resolve(scenarioId).resolve(correlationId).resolve(role);
        Files.createDirectories(directory);
        this.eventsPath = directory.resolve("events.jsonl");
        this.resultPath = directory.resolve("result.properties");
        this.events = Files.newBufferedWriter(eventsPath, StandardCharsets.UTF_8);
    }

    Path directory() {
        return directory;
    }

    synchronized void event(String type, Map<String, String> fields) {
        try {
            Map<String, String> event = new LinkedHashMap<>();
            event.put("at", Instant.now().toString());
            event.put("type", type);
            event.putAll(fields);
            events.write(toJson(event));
            events.newLine();
            events.flush();
        } catch (IOException e) {
            throw new IllegalStateException("Unable to write Baudot evidence event", e);
        }
    }

    synchronized void writeBytes(String filename, byte[] content) throws IOException {
        Path relative = Path.of(filename);
        if (filename.isBlank() || relative.isAbsolute() || relative.getNameCount() != 1
                || filename.equals("events.jsonl") || filename.equals("result.properties")
                || filename.equals("manifest.sha256")) {
            throw new IOException("Unsafe supplemental evidence filename: " + filename);
        }
        Files.write(directory.resolve(relative), content);
        supplementalFiles.add(filename);
    }

    synchronized void result(Map<String, String> fields) throws IOException {
        TreeMap<String, String> sorted = new TreeMap<>(fields);
        try (BufferedWriter writer = Files.newBufferedWriter(resultPath, StandardCharsets.UTF_8)) {
            for (Map.Entry<String, String> entry : sorted.entrySet()) {
                writer.write(entry.getKey());
                writer.write('=');
                writer.write(entry.getValue());
                writer.newLine();
            }
        }
        resultWritten = true;
    }

    private void writeManifest() throws IOException {
        TreeMap<String, Path> artifacts = new TreeMap<>();
        artifacts.put("events.jsonl", eventsPath);
        artifacts.put("result.properties", resultPath);
        for (String filename : supplementalFiles) {
            artifacts.put(filename, directory.resolve(filename));
        }

        Path manifest = directory.resolve("manifest.sha256");
        try (BufferedWriter writer = Files.newBufferedWriter(manifest, StandardCharsets.UTF_8)) {
            for (Map.Entry<String, Path> artifact : artifacts.entrySet()) {
                writer.write(sha256(artifact.getValue()) + "  " + artifact.getKey());
                writer.newLine();
            }
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

    static String toJson(Map<String, String> fields) {
        StringBuilder builder = new StringBuilder("{");
        boolean first = true;
        for (Map.Entry<String, String> entry : fields.entrySet()) {
            if (!first) {
                builder.append(',');
            }
            first = false;
            builder.append('"').append(escape(entry.getKey())).append("\":\"")
                    .append(escape(entry.getValue())).append('"');
        }
        return builder.append('}').toString();
    }

    private static String escape(String value) {
        return value.replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "\\r");
    }

    @Override
    public synchronized void close() throws IOException {
        events.close();
        if (resultWritten) {
            writeManifest();
        }
    }
}
