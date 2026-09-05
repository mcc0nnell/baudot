package org.mcc0nnell.baudot.sip;

/** Stable facts extracted from one RTP packet without retaining dynamic identifiers. */
public record RtpObservation(int version, int payloadType, int payloadBytes) {
    public static RtpObservation parse(byte[] packet, int length) {
        if (packet == null || length < 12 || length > packet.length) {
            throw new IllegalArgumentException("RTP packet is shorter than the fixed header");
        }

        int version = (packet[0] >>> 6) & 0x03;
        if (version != 2) {
            throw new IllegalArgumentException("Unsupported RTP version: " + version);
        }

        int csrcCount = packet[0] & 0x0f;
        boolean extension = (packet[0] & 0x10) != 0;
        boolean padding = (packet[0] & 0x20) != 0;
        int headerLength = 12 + (csrcCount * 4);
        if (length < headerLength) {
            throw new IllegalArgumentException("RTP packet is truncated in the CSRC list");
        }

        if (extension) {
            if (length < headerLength + 4) {
                throw new IllegalArgumentException("RTP packet is truncated in the extension header");
            }
            int extensionWords = ((packet[headerLength + 2] & 0xff) << 8)
                    | (packet[headerLength + 3] & 0xff);
            headerLength += 4 + (extensionWords * 4);
            if (length < headerLength) {
                throw new IllegalArgumentException("RTP packet is truncated in extension data");
            }
        }

        int payloadBytes = length - headerLength;
        if (padding) {
            int paddingBytes = packet[length - 1] & 0xff;
            if (paddingBytes == 0 || paddingBytes > payloadBytes) {
                throw new IllegalArgumentException("Invalid RTP padding length: " + paddingBytes);
            }
            payloadBytes -= paddingBytes;
        }

        int payloadType = packet[1] & 0x7f;
        return new RtpObservation(version, payloadType, payloadBytes);
    }
}
