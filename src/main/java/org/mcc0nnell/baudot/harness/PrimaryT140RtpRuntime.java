package org.mcc0nnell.baudot.harness;

import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

/**
 * Runtime-only parser for the narrow canonical RFC 4103 primary text/t140
 * profile. Packet construction stays in the Python reference/testkit; this
 * class independently interprets bytes observed on a live transport.
 */
final class PrimaryT140RtpRuntime {
    private static final int FIXED_HEADER_SIZE = 12;

    private PrimaryT140RtpRuntime() {
    }

    static Packet parse(byte[] packet, int expectedPayloadType) {
        if (packet.length < FIXED_HEADER_SIZE) {
            throw new IllegalArgumentException("RTP packet is shorter than the 12-octet fixed header");
        }

        int first = packet[0] & 0xff;
        int version = first >>> 6;
        boolean padding = (first & 0x20) != 0;
        boolean extension = (first & 0x10) != 0;
        int csrcCount = first & 0x0f;
        if (version != 2 || padding || extension || csrcCount != 0) {
            throw new IllegalArgumentException("packet is outside Baudot's narrow primary RTP profile");
        }

        int second = packet[1] & 0xff;
        boolean marker = (second & 0x80) != 0;
        int payloadType = second & 0x7f;
        if (payloadType != expectedPayloadType) {
            throw new IllegalArgumentException(
                    "unexpected RTP payload type " + payloadType + "; expected " + expectedPayloadType);
        }
        if (payloadType == 72 || payloadType == 73) {
            throw new IllegalArgumentException("reserved RTP payload type");
        }

        int sequenceNumber = unsignedShort(packet, 2);
        long timestamp = unsignedInt(packet, 4);
        long ssrc = unsignedInt(packet, 8);
        byte[] block = new byte[packet.length - FIXED_HEADER_SIZE];
        System.arraycopy(packet, FIXED_HEADER_SIZE, block, 0, block.length);
        validateUtf8(block);

        return new Packet(
                payloadType,
                sequenceNumber,
                timestamp,
                ssrc,
                marker,
                block,
                sha256(packet));
    }

    private static int unsignedShort(byte[] value, int offset) {
        return ((value[offset] & 0xff) << 8) | (value[offset + 1] & 0xff);
    }

    private static long unsignedInt(byte[] value, int offset) {
        return ((long) (value[offset] & 0xff) << 24)
                | ((long) (value[offset + 1] & 0xff) << 16)
                | ((long) (value[offset + 2] & 0xff) << 8)
                | (long) (value[offset + 3] & 0xff);
    }

    private static void validateUtf8(byte[] block) {
        try {
            StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(block));
        } catch (CharacterCodingException e) {
            throw new IllegalArgumentException("RTP payload is not a complete UTF-8 T140block", e);
        }
    }

    static String hex(byte[] value) {
        StringBuilder builder = new StringBuilder(value.length * 3);
        for (int i = 0; i < value.length; i++) {
            if (i > 0) {
                builder.append(' ');
            }
            builder.append(String.format("%02x", value[i] & 0xff));
        }
        return builder.toString();
    }

    static String sha256(byte[] value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(value);
            StringBuilder builder = new StringBuilder(hash.length * 2);
            for (byte b : hash) {
                builder.append(String.format("%02x", b & 0xff));
            }
            return builder.toString();
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 is unavailable", e);
        }
    }

    record Packet(
            int payloadType,
            int sequenceNumber,
            long timestamp,
            long ssrc,
            boolean marker,
            byte[] t140block,
            String sha256) {
    }
}
