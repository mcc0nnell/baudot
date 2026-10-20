package org.mcc0nnell.baudot.provider.aceconnectlite;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class AceConnectLiteFixtureTest {

    @Test
    void exposesLegacyVrsLookupAsAnAdapterBoundary() {
        var fixture = new AceConnectLiteFixture("provider-a");

        assertEquals("provider-a", fixture.id());
        assertEquals("ACE Connect Lite", fixture.implementation());
        assertEquals("/vrsverify/", AceConnectLiteFixture.LEGACY_VRS_VERIFY_PATH);
        assertTrue(fixture.capabilities().stream()
                .anyMatch(capability -> capability.name().equals("emulated-vrs-number-lookup")));
    }

    @Test
    void fixtureDoesNotPretendToBeAProductionProviderIdentity() {
        var providerA = new AceConnectLiteFixture("provider-a");
        var providerB = new AceConnectLiteFixture("provider-b");

        assertEquals(providerA.implementation(), providerB.implementation());
        assertTrue(!providerA.id().equals(providerB.id()));
    }
}
