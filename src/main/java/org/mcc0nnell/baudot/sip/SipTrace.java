package org.mcc0nnell.baudot.sip;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicReference;

/** Collects stable semantic observations from signaling and SDP negotiation. */
public final class SipTrace {
    private final CopyOnWriteArrayList<SipEvent> events = new CopyOnWriteArrayList<>();
    private final CopyOnWriteArrayList<String> sdpFacts = new CopyOnWriteArrayList<>();
    private final AtomicReference<SdpDescription> offeredSdp = new AtomicReference<>();

    public void sent(String actor, String signal) {
        events.add(new SipEvent(actor, SipEvent.Direction.SENT, signal));
    }

    public void received(String actor, String signal) {
        events.add(new SipEvent(actor, SipEvent.Direction.RECEIVED, signal));
    }

    public void sdpOfferReceived(String actor, SdpDescription description) {
        offeredSdp.set(description);
        sdpFacts.add(actor + " <- offer " + description.semanticSummary());
    }

    public void sdpAnswerReceived(String actor, SdpDescription description) {
        sdpFacts.add(actor + " <- answer " + description.semanticSummary());
        SdpDescription offer = offeredSdp.get();
        if (offer != null) {
            sdpFacts.add("negotiated " + offer.negotiatedWith(description).semanticSummary());
        }
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

    public List<String> sdpFacts() {
        return List.copyOf(sdpFacts);
    }
}
