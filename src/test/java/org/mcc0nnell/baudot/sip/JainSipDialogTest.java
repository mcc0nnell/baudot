package org.mcc0nnell.baudot.sip;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.DatagramSocket;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.Test;

class JainSipDialogTest {
    @Test
    void provesInviteAckByeAndPreservesCanonicalEvidence() throws Exception {
        SipTrace trace = new SipTrace();
        int[] ports = reserveTwoUdpPorts();

        try (JainSipEndpoint alice = new JainSipEndpoint("alice", "alice", ports[0], trace);
             JainSipEndpoint bob = new JainSipEndpoint("bob", "bob", ports[1], trace)) {

            alice.invite("bob", ports[1]);
            assertTrue(alice.awaitCompletion(Duration.ofSeconds(5)), "SIP dialog did not complete");
        }

        List<String> expected = List.of(
                "alice -> INVITE",
                "bob -> 100 INVITE",
                "bob -> 180 INVITE",
                "bob -> 200 INVITE",
                "alice -> ACK",
                "alice -> BYE",
                "bob -> 200 BYE"
        );
        List<String> observed = trace.sentSignals();
        assertEquals(expected, observed);

        Path evidence = Path.of("target", "baudot-evidence", "sip-dialog.json");
        SipEvidenceWriter.write(evidence, expected, observed);
        assertTrue(java.nio.file.Files.isRegularFile(evidence));
    }

    private static int[] reserveTwoUdpPorts() throws Exception {
        try (DatagramSocket first = new DatagramSocket(0);
             DatagramSocket second = new DatagramSocket(0)) {
            return new int[] {first.getLocalPort(), second.getLocalPort()};
        }
    }
}
