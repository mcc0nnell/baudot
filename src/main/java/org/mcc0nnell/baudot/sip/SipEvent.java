package org.mcc0nnell.baudot.sip;

/** A deliberately small, stable observation vocabulary for the signaling slice. */
public record SipEvent(String actor, Direction direction, String signal) {
    public enum Direction {
        SENT,
        RECEIVED
    }
}
