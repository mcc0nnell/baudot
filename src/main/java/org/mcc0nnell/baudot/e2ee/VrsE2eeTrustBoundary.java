package org.mcc0nnell.baudot.e2ee;

import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

/**
 * Executable authorization contract for the current VRS media epoch.
 *
 * <p>This class models who can decrypt. It deliberately performs no cryptography and
 * makes no E2EE-conformance claim.</p>
 */
public final class VrsE2eeTrustBoundary {
    private VrsE2eeTrustBoundary() {
    }

    public enum Role {
        CALLER,
        CALLEE,
        ACTIVE_CA,
        FORMER_CA,
        SFU,
        TURN,
        WIRETAP,
        SIP_PROXY,
        OBSERVABILITY
    }

    public record Actor(String id, Role role, boolean canDecryptCurrentEpoch) {
        public Actor {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("actor id must not be blank");
            }
            Objects.requireNonNull(role, "role");
        }
    }

    public record Evaluation(
            boolean callerCanDecrypt,
            boolean calleeCanDecrypt,
            boolean activeCaCanDecrypt,
            boolean formerCaCanDecrypt,
            boolean infrastructureCanDecrypt,
            boolean authorizedDecryptorSetMatched) {

        public List<String> facts() {
            return List.of(
                    "caller decryptable=" + callerCanDecrypt,
                    "callee decryptable=" + calleeCanDecrypt,
                    "active-ca decryptable=" + activeCaCanDecrypt,
                    "former-ca decryptable=" + formerCaCanDecrypt,
                    "infrastructure decryptable=" + infrastructureCanDecrypt,
                    "authorized-decryptor-set matched=" + authorizedDecryptorSetMatched);
        }

        public String canonicalJson() {
            return "{\n"
                    + "  \"schema\": \"baudot.vrs-e2ee-trust-boundary/v1\",\n"
                    + "  \"semanticBoundary\": \"current-media-epoch-decryption-authorization\",\n"
                    + "  \"callerCanDecrypt\": " + callerCanDecrypt + ",\n"
                    + "  \"calleeCanDecrypt\": " + calleeCanDecrypt + ",\n"
                    + "  \"activeCaCanDecrypt\": " + activeCaCanDecrypt + ",\n"
                    + "  \"formerCaCanDecrypt\": " + formerCaCanDecrypt + ",\n"
                    + "  \"infrastructureCanDecrypt\": " + infrastructureCanDecrypt + ",\n"
                    + "  \"authorizedDecryptorSetMatched\": " + authorizedDecryptorSetMatched + ",\n"
                    + "  \"cryptographicE2eeProven\": false\n"
                    + "}\n";
        }
    }

    public static Evaluation evaluate(List<Actor> actors) {
        Objects.requireNonNull(actors, "actors");
        Set<String> ids = new HashSet<>();
        for (Actor actor : actors) {
            Objects.requireNonNull(actor, "actor");
            if (!ids.add(actor.id())) {
                throw new IllegalArgumentException("duplicate actor id: " + actor.id());
            }
        }

        boolean caller = canDecrypt(actors, Role.CALLER);
        boolean callee = canDecrypt(actors, Role.CALLEE);
        boolean activeCa = canDecrypt(actors, Role.ACTIVE_CA);
        boolean formerCa = canDecrypt(actors, Role.FORMER_CA);
        boolean infrastructure = actors.stream()
                .anyMatch(actor -> isInfrastructure(actor.role()) && actor.canDecryptCurrentEpoch());

        boolean matched = caller && callee && activeCa && !formerCa && !infrastructure;
        return new Evaluation(caller, callee, activeCa, formerCa, infrastructure, matched);
    }

    private static boolean canDecrypt(List<Actor> actors, Role role) {
        return actors.stream()
                .anyMatch(actor -> actor.role() == role && actor.canDecryptCurrentEpoch());
    }

    private static boolean isInfrastructure(Role role) {
        return switch (role) {
            case SFU, TURN, WIRETAP, SIP_PROXY, OBSERVABILITY -> true;
            case CALLER, CALLEE, ACTIVE_CA, FORMER_CA -> false;
        };
    }
}
