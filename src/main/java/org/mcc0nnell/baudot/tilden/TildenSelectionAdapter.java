package org.mcc0nnell.baudot.tilden;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.nio.file.Path;

/** Converts a successful TildenSelection evidence object into Baudot runtime input. */
public final class TildenSelectionAdapter {
    private static final String SUPPORTED_VERSION = "0.1";

    private final ObjectMapper mapper;

    public TildenSelectionAdapter() {
        this(new ObjectMapper());
    }

    TildenSelectionAdapter(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public BaudotRoute read(Path selectionPath) throws IOException {
        JsonNode root = mapper.readTree(selectionPath.toFile());
        return adapt(root);
    }

    BaudotRoute adapt(JsonNode root) {
        if (root == null || !root.isObject()) {
            throw invalid("selection must be a JSON object");
        }

        String version = requiredText(root, "version");
        if (!SUPPORTED_VERSION.equals(version)) {
            throw invalid("unsupported TildenSelection version: " + version);
        }

        String terminal = requiredText(root, "terminal");
        if (!"selected".equals(terminal)) {
            throw invalid("TildenSelection terminal is not selected: " + terminal);
        }

        String selectionId = requiredText(root, "selectionId");
        String target = requiredText(root, "target");
        String selectedEndpoint = requiredText(root, "selectedEndpoint");
        String resolutionDigest = requiredText(root, "resolutionDigest");
        String requestDigest = requiredText(root, "requestDigest");

        JsonNode candidates = root.get("candidates");
        if (candidates == null || !candidates.isArray()) {
            throw invalid("candidates must be an array");
        }

        int selectedCount = 0;
        for (JsonNode candidate : candidates) {
            if (!candidate.isObject()) {
                throw invalid("candidate must be a JSON object");
            }
            JsonNode outcome = candidate.get("outcome");
            if (outcome != null && outcome.isTextual() && "selected".equals(outcome.asText())) {
                selectedCount++;
                String candidateUri = requiredText(candidate, "uri");
                if (!selectedEndpoint.equals(candidateUri)) {
                    throw invalid("selected candidate URI does not match selectedEndpoint");
                }
            }
        }

        if (selectedCount != 1) {
            throw invalid("selected terminal requires exactly one selected candidate");
        }

        return new BaudotRoute(
                selectionId,
                target,
                selectedEndpoint,
                resolutionDigest,
                requestDigest);
    }

    private static String requiredText(JsonNode object, String field) {
        JsonNode node = object.get(field);
        if (node == null || !node.isTextual() || node.asText().isBlank()) {
            throw invalid(field + " must be a non-blank string");
        }
        return node.asText();
    }

    private static IllegalArgumentException invalid(String message) {
        return new IllegalArgumentException("invalid TildenSelection: " + message);
    }
}
