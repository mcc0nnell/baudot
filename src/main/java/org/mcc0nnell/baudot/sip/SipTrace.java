package org.mcc0nnell.baudot.sip;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

/**
 * Collects semantic signaling observations rather than raw implementation logs.
 * This keeps evidence stable across ports, Call-IDs, branches, timestamps, and
 * other values that are intentionally nondeterministic.
 */
public final class SipTrace {
    private final CopyOnWriteArrayList<SipEvent> events = new CopyOnWriteArrayList<>();

    public void sent(String actor, String signal) {
        events.add(new SipEvent(actor, SipEvent.Direction.SENT, signal));
    }

    public void received(String actor, String signal) {
        events.add(new SipEvent(actor, SipEvent.Direction.RECEIVED, signal));
    }

    public List<SipEvent> snapshot() {
        return List.copyOf(events);
    }

    public List<String> sentSignals() {
        return events.stream()
                .filter(event -> event.direction() == SipEvent.Direction.SENT)
                .map(event -> event.actor() + " -> " + event.signal())
                .toList();
    }
}
