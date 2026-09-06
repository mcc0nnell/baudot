package org.mcc0nnell.baudot.tilden;

/**
 * Runtime-relevant subset of a validated TildenSelection.
 *
 * <p>This object is intentionally smaller than the Tilden evidence record. It carries only the
 * selected route and correlation fields Baudot needs to start and explain a session attempt.</p>
 */
public record BaudotRoute(
        String selectionId,
        String target,
        String selectedEndpoint,
        String resolutionDigest,
        String requestDigest) {
}
