package org.mcc0nnell.baudot.media.control;

import java.time.Instant;
import java.util.Map;
import java.util.Objects;

/**
 * Implementation-reported lifecycle or capability fact.
 *
 * <p>These events are evidence inputs, not terminal accessibility verdicts.
 * Raw media belongs on an independent observation seam.</p>
 */
public record MediaControlEvent(
        MediaSessionRef session,
        Type type,
        Instant observedAt,
        String capability,
        String evidenceRef,
        Map<String, String> attributes) {

    public MediaControlEvent {
        Objects.requireNonNull(session, "session");
        Objects.requireNonNull(type, "type");
        observedAt = observedAt == null ? Instant.now() : observedAt;
        if (capability != null && capability.isBlank()) {
            capability = null;
        }
        if (evidenceRef != null && evidenceRef.isBlank()) {
            evidenceRef = null;
        }
        attributes = attributes == null ? Map.of() : Map.copyOf(attributes);
    }

    public enum Type {
        SESSION_CREATED,
        SESSION_READY,
        CAPABILITY_ATTACHED,
        CAPABILITY_DETACHED,
        MEDIA_STATE,
        SESSION_ENDED,
        ERROR
    }
}