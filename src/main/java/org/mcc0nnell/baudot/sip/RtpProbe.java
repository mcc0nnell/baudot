package org.mcc0nnell.baudot.sip;

import java.io.IOException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketTimeoutException;
import java.time.Duration;
import java.util.Optional;

/**
 * Minimal RTP transport probe for deterministic interoperability evidence.
 *
 * <p>It proves UDP/RTP packet observability only. It does not validate codec payload
 * syntax, decode media, render video, or establish SRTP/ICE/DTLS behavior.</p>
 */
public final class RtpProbe implements AutoCloseable {
    private final String actor;
    private final String mediaType;
    private final SipTrace trace;
    private final DatagramSocket socket;

    public RtpProbe(String actor, String mediaType, SipTrace trace) throws IOException {
        this.actor = actor;
        this.mediaType = mediaType;
        this.trace = trace;
        this.socket = new DatagramSocket(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
        trace.rtpSocketReady(actor, mediaType);
    }

    public int port() {
        return socket.getLocalPort();
    }

    public void sendTo(int destinationPort, int payloadType, byte[] payload) throws IOException {
        if (payloadType < 0 || payloadType > 127) {
            throw new IllegalArgumentException("RTP payload type must be between 0 and 127");
        }
        if (payload == null) {
            throw new IllegalArgumentException("RTP payload must not be null");
        }

        byte[] packet = new byte[12 + payload.length];
        packet[0] = (byte) 0x80; // RTP v2, no padding/extension/CSRCs.
        packet[1] = (byte) payloadType;
        packet[2] = 0;
        packet[3] = 1; // deterministic sequence number; intentionally not evidence.
        packet[7] = 1; // deterministic timestamp; intentionally not evidence.
        packet[8] = 0x42; // synthetic SSRC "BAUD"; intentionally not evidence.
        packet[9] = 0x41;
        packet[10] = 0x55;
        packet[11] = 0x44;
        System.arraycopy(payload, 0, packet, 12, payload.length);

        DatagramPacket datagram = new DatagramPacket(
                packet, packet.length, InetAddress.getLoopbackAddress(), destinationPort);
        socket.send(datagram);
    }

    public Optional<RtpObservation> awaitFirstPacket(Duration timeout, int expectedPayloadType) throws IOException {
        long timeoutMillis = timeout.toMillis();
        if (timeoutMillis <= 0 || timeoutMillis > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("RTP timeout must fit a positive socket timeout");
        }
        socket.setSoTimeout((int) timeoutMillis);

        byte[] buffer = new byte[2048];
        DatagramPacket datagram = new DatagramPacket(buffer, buffer.length);
        try {
            socket.receive(datagram);
            RtpObservation observation = RtpObservation.parse(datagram.getData(), datagram.getLength());
            trace.rtpPacketReceived(actor, mediaType, observation, expectedPayloadType);
            return Optional.of(observation);
        } catch (SocketTimeoutException timeoutException) {
            trace.rtpNoPacket(actor, mediaType, expectedPayloadType);
            return Optional.empty();
        }
    }

    @Override
    public void close() {
        socket.close();
    }
}
