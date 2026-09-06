package org.mcc0nnell.baudot.harness;

/**
 * Process boundary for the Tilden-selected native RTT lane.
 *
 * <p>The JAIN SIP stack can leave implementation worker threads alive briefly after the
 * evidence-producing call main has completed and stopped the stack. This wrapper makes process
 * completion explicit only after {@link TildenPjsipRttCallMain} has returned successfully. It has
 * no signaling, media, readiness, or verdict authority.</p>
 */
public final class TildenPjsipRttProcessMain {
    private TildenPjsipRttProcessMain() {
    }

    public static void main(String[] args) throws Exception {
        TildenPjsipRttCallMain.main(args);
        System.exit(0);
    }
}
