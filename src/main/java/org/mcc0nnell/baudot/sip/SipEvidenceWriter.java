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

    public static void write(
            Path path,
            List<String> expectedSignals,
            List<String> observedSignals,
            List<String> expectedSdp,
            List<String> observedSdp) throws IOException {
        Files.createDirectories(path.getParent());
        String json = "{\n"
                + "  \"schema\": \"baudot.sip-dialog-evidence/v2\",\n"
                + "  \"scenario\": \"invite-sdp-ack-bye\",\n"
                + "  \"transport\": \"UDP-loopback\",\n"
                + "  \"semanticBoundary\": \"SIP-signaling-and-SDP-description\",\n"
                + "  \"signaling\": {\n"
                + "    \"expected\": " + array(expectedSignals) + ",\n"
                + "    \"observed\": " + array(observedSignals) + ",\n"
                + "    \"matched\": " + expectedSignals.equals(observedSignals) + "\n"
                + "  },\n"
                + "  \"sdp\": {\n"
                + "    \"expected\": " + array(expectedSdp) + ",\n"
                + "    \"observed\": " + array(observedSdp) + ",\n"
                + "    \"matched\": " + expectedSdp.equals(observedSdp) + "\n"
                + "  },\n"
                + "  \"mediaTransportProven\": false\n"
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
