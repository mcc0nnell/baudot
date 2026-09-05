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
            List<String> observedSdp,
            List<String> expectedRtp,
            List<String> observedRtp,
            boolean mediaTransportProven) throws IOException {
        Files.createDirectories(path.getParent());
        String json = "{\n"
                + "  \"schema\": \"baudot.sip-dialog-evidence/v3\",\n"
                + "  \"scenario\": \"invite-sdp-rtp-ack-bye\",\n"
                + "  \"transport\": \"UDP-loopback\",\n"
                + "  \"semanticBoundary\": \"SIP-signaling-SDP-and-RTP-observation\",\n"
                + section("signaling", expectedSignals, observedSignals) + ",\n"
                + section("sdp", expectedSdp, observedSdp) + ",\n"
                + section("rtp", expectedRtp, observedRtp) + ",\n"
                + "  \"mediaTransportProven\": " + mediaTransportProven + ",\n"
                + "  \"decoderInputProven\": false,\n"
                + "  \"renderingProven\": false\n"
                + "}\n";
        Files.writeString(path, json, StandardCharsets.UTF_8);
    }

    private static String section(String name, List<String> expected, List<String> observed) {
        return "  \"" + name + "\": {\n"
                + "    \"expected\": " + array(expected) + ",\n"
                + "    \"observed\": " + array(observed) + ",\n"
                + "    \"matched\": " + expected.equals(observed) + "\n"
                + "  }";
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
