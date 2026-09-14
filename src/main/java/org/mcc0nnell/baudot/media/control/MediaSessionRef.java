package org.mcc0nnell.baudot.media.control;

import java.util.Objects;

/**
 * Stable join key between Baudot orchestration and one implementation-owned
 * media session.
 *
 * <p>The Baudot correlation id is canonical. The implementation session id is
 * optional implementation evidence and must not replace it.</p>
 */
public record MediaSessionRef(String correlationId, String implementationSessionId) {

    public MediaSessionRef {
        Objects.requireNonNull(correlationId, "correlationId");
        if (correlationId.isBlank()) {
            throw new IllegalArgumentException("correlationId must not be blank");
        }
        if (implementationSessionId != null && implementationSessionId.isBlank()) {
            implementationSessionId = null;
        }
    }

    public static MediaSessionRef unbound(String correlationId) {
        return new MediaSessionRef(correlationId, null);
    }
}