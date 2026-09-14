package org.mcc0nnell.baudot.media.control;

import java.util.function.Consumer;

/**
 * Control-plane seam between Baudot orchestration and a media implementation.
 *
 * <p>Implementations may translate these commands into engine-native APIs such
 * as an event socket, WebRTC control channel, or native media API. They must not
 * widen this interface into a raw-media transport.</p>
 */
public interface MediaControlAdapter {

    /** Stable adapter identity for evidence and diagnostics. */
    String adapterId();

    /** Dispatch one bounded control-plane command. */
    void dispatch(MediaControlCommand command);

    /**
     * Subscribe to implementation-reported lifecycle and capability events.
     * The returned subscription must be idempotently closeable.
     */
    Subscription subscribe(Consumer<MediaControlEvent> consumer);

    @FunctionalInterface
    interface Subscription extends AutoCloseable {
        @Override
        void close();
    }
}