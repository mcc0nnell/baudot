package org.mcc0nnell.baudot.sip;

import java.util.List;
import java.util.Optional;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

/** Collects stable semantic observations from signaling, SDP, and RTP transport. */
public final class SipTrace {
    private final CopyOnWriteArrayList<SipEvent> events = new CopyOnWriteArrayList<>();
    private final CopyOnWriteArrayList<String> sdpFacts = new CopyOnWriteArrayList<>();
    private final CopyOnWriteArrayList<String> rtpFacts = new CopyOnWriteArrayList<>();
    private final AtomicReference<SdpDescription> offeredSdp = new AtomicReference<>();
    private final AtomicReference<SdpDescription> negotiatedSdp = new AtomicReference<>();
    private final AtomicBoolean mediaTransportProven = new AtomicBoolean();

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
            SdpDescription negotiated = offer.negotiatedWith(description);
            negotiatedSdp.set(negotiated);
            sdpFacts.add("negotiated " + negotiated.semanticSummary());
        }
    }

    public Optional<SdpDescription> negotiatedSdp() {
        return Optional.ofNullable(negotiatedSdp.get());
    }

    public void rtpSocketReady(String actor, String mediaType) {
        rtpFacts.add(actor + " rtp-ready " + mediaType);
    }

    public void rtpPacketReceived(String actor, String mediaType, RtpObservation observation, int expectedPayloadType) {
        rtpFacts.add(actor + " <- RTP " + mediaType + " payload-type=" + observation.payloadType()
                + " payload-bytes=" + observation.payloadBytes());
        if (observation.payloadType() == expectedPayloadType) {
            rtpFacts.add(actor + " rtp-payload-match " + mediaType + " payload-type=" + expectedPayloadType);
            mediaTransportProven.set(true);
        } else {
            rtpFacts.add(actor + " rtp-payload-mismatch " + mediaType + " expected=" + expectedPayloadType
                    + " observed=" + observation.payloadType());
        }
    }

    public void rtpNoPacket(String actor, String mediaType, int expectedPayloadType) {
        rtpFacts.add(actor + " rtp-timeout " + mediaType + " payload-type=" + expectedPayloadType);
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

    public List<String> rtpFacts() {
        return List.copyOf(rtpFacts);
    }

    public boolean mediaTransportProven() {
        return mediaTransportProven.get();
    }
}
