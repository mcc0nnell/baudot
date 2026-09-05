package org.mcc0nnell.baudot.sip;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

/** Writes a canonical, timestamp-free artifact suitable for later assurance tooling. */
public final class SipEvidenceWriter {
    private SipEvidenceWriter() {
    }

    public static void write(Path path, List<String> expected, List<String> observed) throws IOException {
        Files.createDirectories(path.getParent());
        String json = "{\n"
                + "  \"schema\": \"baudot.sip-dialog-evidence/v1\",\n"
                + "  \"scenario\": \"invite-ack-bye\",\n"
                + "  \"transport\": \"UDP-loopback\",\n"
                + "  \"semanticBoundary\": \"SIP-signaling-only\",\n"
                + "  \"expected\": " + array(expected) + ",\n"
                + "  \"observed\": " + array(observed) + ",\n"
                + "  \"matched\": " + expected.equals(observed) + "\n"
                + "}\n";
        Files.writeString(path, json, StandardCharsets.UTF_8);
    }

    private static String array(List<String> values) {
        return values.stream()
                .map(SipEvidenceWriter::quote)
                .collect(java.util.stream.Collectors.joining(", ", "[", "]"));
    }

    private static String quote(String value) {
        return "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
    }
}
