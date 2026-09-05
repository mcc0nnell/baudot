package org.mcc0nnell.baudot.harness;

/** Process boundary for the live JAIN SIP overlap probe. */
public final class LiveReinviteOverlapMain {
    private LiveReinviteOverlapMain() {
    }

    public static void main(String[] args) throws Exception {
        LiveReinviteOverlapProbe.main(args);
        System.exit(0);
    }
}
