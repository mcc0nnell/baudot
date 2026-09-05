package org.mcc0nnell.baudot.provider.aceconnectlite;

import java.net.URI;
import java.util.Set;
import org.mcc0nnell.baudot.provider.ProviderFixture;

/**
 * Baudot profile for the historical MITRE/FCC ACE Connect Lite implementation.
 *
 * <p>This class records the integration surfaces Baudot may exercise. It does
 * not claim that ACE Connect Lite is representative of every production VRS
 * provider or that any exercised behavior is standards-conformant.</p>
 */
public final class AceConnectLiteFixture implements ProviderFixture {

    public static final URI SOURCE_REPOSITORY =
            URI.create("https://github.com/mitrefccace/aceconnectlite-public");

    public static final String LEGACY_VRS_VERIFY_PATH = "/vrsverify/";

    private final String id;

    public AceConnectLiteFixture(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("fixture id must not be blank");
        }
        this.id = id;
    }

    @Override
    public String id() {
        return id;
    }

    @Override
    public String implementation() {
        return "ACE Connect Lite";
    }

    @Override
    public URI sourceRepository() {
        return SOURCE_REPOSITORY;
    }

    @Override
    public Set<FixtureCapability> capabilities() {
        return Set.of(
                new FixtureCapability(
                        "sip-signaling",
                        "Asterisk-backed SIP behavior observed by Baudot"),
                new FixtureCapability(
                        "sip-websocket-video",
                        "ACE client configuration exposes SIP over WebSocket and video controls"),
                new FixtureCapability(
                        "emulated-vrs-number-lookup",
                        "Legacy /vrsverify/ lookup seam; adapter target for deterministic Baudot iTRS fixtures"),
                new FixtureCapability(
                        "agent-and-queue-state",
                        "ACE/Asterisk AMI call-agent and queue observations"));
    }
}
