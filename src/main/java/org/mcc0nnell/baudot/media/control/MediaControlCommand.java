package org.mcc0nnell.baudot.media.control;

import java.util.Map;
import java.util.Objects;

/**
 * Metadata-only control intent sent to a media implementation.
 *
 * <p>This type intentionally has no raw media field. RTP packets, decoded
 * audio/video frames, T.140 payloads, and other media bytes belong on an
 * execution or observation seam, not this control contract.</p>
 */
public record MediaControlCommand(
        MediaSessionRef session,
        Action action,
        String capability,
        Map<String, String> parameters) {

    public MediaControlCommand {
        Objects.requireNonNull(session, "session");
        Objects.requireNonNull(action, "action");
        if (capability != null && capability.isBlank()) {
            capability = null;
        }
        parameters = parameters == null ? Map.of() : Map.copyOf(parameters);
    }

    public enum Action {
        ATTACH,
        DETACH,
        START,
        STOP,
        BRIDGE,
        SELECT
    }
}