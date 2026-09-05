package org.mcc0nnell.baudot.sip;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Small semantic view of SDP for evidence generation.
 *
 * <p>This is intentionally not a general SDP implementation. The SIP stack still
 * carries the wire representation unchanged; this class extracts only stable
 * media/protocol/codec facts that the first Baudot slice needs to assert.</p>
 */
public record SdpDescription(List<Media> media) {
    public SdpDescription {
        media = List.copyOf(media);
    }

    public static SdpDescription parse(byte[] rawContent) {
        if (rawContent == null || rawContent.length == 0) {
            throw new IllegalArgumentException("SDP content is empty");
        }

        List<MutableMedia> sections = new ArrayList<>();
        MutableMedia current = null;
        String text = new String(rawContent, StandardCharsets.UTF_8);
        for (String rawLine : text.split("\\r?\\n")) {
            String line = rawLine.trim();
            if (line.startsWith("m=")) {
                String[] parts = line.substring(2).trim().split("\\s+");
                if (parts.length < 4) {
                    throw new IllegalArgumentException("Malformed SDP media line: " + line);
                }
                current = new MutableMedia(parts[0], parts[2]);
                for (int i = 3; i < parts.length; i++) {
                    current.formats.add(parts[i]);
                }
                sections.add(current);
            } else if (line.startsWith("a=rtpmap:") && current != null) {
                String mapping = line.substring("a=rtpmap:".length()).trim();
                int separator = mapping.indexOf(' ');
                if (separator <= 0 || separator == mapping.length() - 1) {
                    throw new IllegalArgumentException("Malformed SDP rtpmap line: " + line);
                }
                String payloadType = mapping.substring(0, separator);
                String[] encoding = mapping.substring(separator + 1).split("/");
                if (encoding.length < 2) {
                    throw new IllegalArgumentException("Malformed SDP codec mapping: " + line);
                }
                current.codecs.put(payloadType,
                        new Codec(payloadType, encoding[0], parseClockRate(encoding[1], line)));
            }
        }

        if (sections.isEmpty()) {
            throw new IllegalArgumentException("SDP contains no media sections");
        }

        return new SdpDescription(sections.stream().map(MutableMedia::freeze).toList());
    }

    public String semanticSummary() {
        return media.stream().map(Media::semanticSummary).reduce((left, right) -> left + "; " + right).orElse("");
    }

    public SdpDescription negotiatedWith(SdpDescription answer) {
        List<Media> negotiated = new ArrayList<>();
        for (Media answeredMedia : answer.media()) {
            Media offeredMedia = media.stream()
                    .filter(candidate -> candidate.type().equals(answeredMedia.type()))
                    .filter(candidate -> candidate.protocol().equals(answeredMedia.protocol()))
                    .findFirst()
                    .orElse(null);
            if (offeredMedia == null) {
                continue;
            }

            List<Codec> codecs = answeredMedia.codecs().stream()
                    .filter(answeredCodec -> offeredMedia.codecs().stream().anyMatch(
                            offeredCodec -> offeredCodec.equivalentTo(answeredCodec)))
                    .toList();
            if (!codecs.isEmpty()) {
                negotiated.add(new Media(answeredMedia.type(), answeredMedia.protocol(), codecs));
            }
        }
        return new SdpDescription(negotiated);
    }

    private static int parseClockRate(String value, String line) {
        try {
            return Integer.parseInt(value);
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException("Malformed SDP clock rate: " + line, e);
        }
    }

    public record Media(String type, String protocol, List<Codec> codecs) {
        public Media {
            codecs = List.copyOf(codecs);
        }

        String semanticSummary() {
            String codecSummary = codecs.stream()
                    .map(Codec::semanticSummary)
                    .reduce((left, right) -> left + "," + right)
                    .orElse("none");
            return type + " " + protocol + " [" + codecSummary + "]";
        }
    }

    public record Codec(String payloadType, String encoding, int clockRate) {
        String semanticSummary() {
            return encoding + "/" + clockRate;
        }

        boolean equivalentTo(Codec other) {
            return payloadType.equals(other.payloadType)
                    && encoding.equalsIgnoreCase(other.encoding)
                    && clockRate == other.clockRate;
        }
    }

    private static final class MutableMedia {
        private final String type;
        private final String protocol;
        private final List<String> formats = new ArrayList<>();
        private final Map<String, Codec> codecs = new LinkedHashMap<>();

        private MutableMedia(String type, String protocol) {
            this.type = type;
            this.protocol = protocol;
        }

        private Media freeze() {
            List<Codec> ordered = new ArrayList<>();
            for (String format : formats) {
                Codec codec = codecs.get(format);
                ordered.add(codec != null ? codec : new Codec(format, "unmapped", 0));
            }
            return new Media(type, protocol, ordered);
        }
    }
}
