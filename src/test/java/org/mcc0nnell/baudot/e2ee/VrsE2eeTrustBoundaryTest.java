package org.mcc0nnell.baudot.e2ee;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;

class VrsE2eeTrustBoundaryTest {
    @Test
    void provesBaselineAuthorizedDecryptorContractAndPreservesEvidence() throws Exception {
        VrsE2eeTrustBoundary.Evaluation evaluation = VrsE2eeTrustBoundary.evaluate(List.of(
                actor("caller", VrsE2eeTrustBoundary.Role.CALLER, true),
                actor("callee", VrsE2eeTrustBoundary.Role.CALLEE, true),
                actor("ca-current", VrsE2eeTrustBoundary.Role.ACTIVE_CA, true),
                actor("ca-previous", VrsE2eeTrustBoundary.Role.FORMER_CA, false),
                actor("sfu", VrsE2eeTrustBoundary.Role.SFU, false),
                actor("turn", VrsE2eeTrustBoundary.Role.TURN, false),
                actor("wiretap", VrsE2eeTrustBoundary.Role.WIRETAP, false),
                actor("sip-proxy", VrsE2eeTrustBoundary.Role.SIP_PROXY, false),
                actor("evidence", VrsE2eeTrustBoundary.Role.OBSERVABILITY, false)
        ));

        assertTrue(evaluation.callerCanDecrypt());
        assertTrue(evaluation.calleeCanDecrypt());
        assertTrue(evaluation.activeCaCanDecrypt());
        assertFalse(evaluation.formerCaCanDecrypt());
        assertFalse(evaluation.infrastructureCanDecrypt());
        assertTrue(evaluation.authorizedDecryptorSetMatched());
        assertFalse(evaluation.canonicalJson().contains("\"cryptographicE2eeProven\": true"));

        Path evidence = Path.of("target", "baudot-evidence", "vrs-e2ee-trust-boundary.json");
        Files.createDirectories(evidence.getParent());
        Files.writeString(evidence, evaluation.canonicalJson(), StandardCharsets.UTF_8);
        assertTrue(Files.isRegularFile(evidence));
    }

    @Test
    void rejectsInfrastructurePlaintextAccess() {
        VrsE2eeTrustBoundary.Evaluation evaluation = VrsE2eeTrustBoundary.evaluate(List.of(
                actor("caller", VrsE2eeTrustBoundary.Role.CALLER, true),
                actor("callee", VrsE2eeTrustBoundary.Role.CALLEE, true),
                actor("ca-current", VrsE2eeTrustBoundary.Role.ACTIVE_CA, true),
                actor("sfu", VrsE2eeTrustBoundary.Role.SFU, true)
        ));

        assertTrue(evaluation.infrastructureCanDecrypt());
        assertFalse(evaluation.authorizedDecryptorSetMatched());
    }

    @Test
    void rejectsStaleFormerCaAccessAfterHandoff() {
        VrsE2eeTrustBoundary.Evaluation evaluation = VrsE2eeTrustBoundary.evaluate(List.of(
                actor("caller", VrsE2eeTrustBoundary.Role.CALLER, true),
                actor("callee", VrsE2eeTrustBoundary.Role.CALLEE, true),
                actor("ca-current", VrsE2eeTrustBoundary.Role.ACTIVE_CA, true),
                actor("ca-previous", VrsE2eeTrustBoundary.Role.FORMER_CA, true)
        ));

        assertTrue(evaluation.formerCaCanDecrypt());
        assertFalse(evaluation.authorizedDecryptorSetMatched());
    }

    @Test
    void rejectsAProtectedSessionThatTheActiveCaCannotRelay() {
        VrsE2eeTrustBoundary.Evaluation evaluation = VrsE2eeTrustBoundary.evaluate(List.of(
                actor("caller", VrsE2eeTrustBoundary.Role.CALLER, true),
                actor("callee", VrsE2eeTrustBoundary.Role.CALLEE, true),
                actor("ca-current", VrsE2eeTrustBoundary.Role.ACTIVE_CA, false)
        ));

        assertFalse(evaluation.activeCaCanDecrypt());
        assertFalse(evaluation.authorizedDecryptorSetMatched());
    }

    private static VrsE2eeTrustBoundary.Actor actor(
            String id, VrsE2eeTrustBoundary.Role role, boolean canDecryptCurrentEpoch) {
        return new VrsE2eeTrustBoundary.Actor(id, role, canDecryptCurrentEpoch);
    }
}
