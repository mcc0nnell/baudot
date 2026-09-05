package org.mcc0nnell.baudot.provider;

import java.net.URI;
import java.util.Set;

/**
 * Provider-neutral description of an external communications implementation
 * used as a Baudot interoperability fixture.
 *
 * <p>The fixture describes observable integration surfaces. It does not imply
 * standards conformance or production-provider equivalence.</p>
 */
public interface ProviderFixture {

    String id();

    String implementation();

    URI sourceRepository();

    Set<FixtureCapability> capabilities();

    record FixtureCapability(String name, String evidenceBoundary) {
        public FixtureCapability {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("capability name must not be blank");
            }
            if (evidenceBoundary == null || evidenceBoundary.isBlank()) {
                throw new IllegalArgumentException("evidence boundary must not be blank");
            }
        }
    }
}
