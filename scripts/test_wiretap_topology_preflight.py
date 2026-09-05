from __future__ import annotations

import unittest

from scripts.wiretap_topology_preflight import (
    TRANSPARENT_RPORT,
    UDP_EXPOSE_LOOPBACK,
    TopologyError,
    validate_topology,
)


class WiretapTopologyPreflightTest(unittest.TestCase):
    def valid(self, **overrides):
        values = {
            "underlay_addresses": ["198.18.0.1/24", "198.18.0.2/24"],
            "signaling_network": "10.77.10.0/24",
            "media_network": "10.77.20.0/24",
            "routes": "10.77.10.0/24,10.77.20.0/24",
            "response_routing": TRANSPARENT_RPORT,
            "loopback_forwarding_shim": False,
        }
        values.update(overrides)
        return validate_topology(**values)

    def test_current_routed_topology_passes(self):
        result = self.valid()
        self.assertEqual("198.18.0.0/24", result["underlay.network"])
        self.assertEqual("not-required", result["signaling.loopbackForwardingShim"])

    def test_signaling_only_route_is_valid(self):
        result = self.valid(routes="10.77.10.0/24")
        self.assertEqual("10.77.10.0/24", result["wiretap.routes"])

    def test_wiretap_reserved_ipv4_overlap_is_rejected(self):
        with self.assertRaisesRegex(TopologyError, "Wiretap-reserved IPv4 prefix"):
            self.valid(
                underlay_addresses=["192.0.2.1/24", "192.0.2.2/24"]
            )

    def test_undeclared_route_is_rejected(self):
        with self.assertRaisesRegex(TopologyError, "not one of the declared"):
            self.valid(routes="10.77.10.0/24,10.99.0.0/24")

    def test_udp_expose_loopback_requires_explicit_shim(self):
        with self.assertRaisesRegex(TopologyError, "requires an explicit"):
            self.valid(response_routing=UDP_EXPOSE_LOOPBACK)

    def test_udp_expose_loopback_with_declared_shim_is_semantically_valid(self):
        result = self.valid(
            response_routing=UDP_EXPOSE_LOOPBACK,
            loopback_forwarding_shim=True,
        )
        self.assertEqual("declared", result["signaling.loopbackForwardingShim"])

    def test_transparent_rport_rejects_unexpected_shim(self):
        with self.assertRaisesRegex(TopologyError, "incompatible with transparent rport"):
            self.valid(loopback_forwarding_shim=True)

    def test_role_network_overlap_is_rejected(self):
        with self.assertRaisesRegex(TopologyError, "overlaps"):
            self.valid(media_network="10.77.10.128/25")


if __name__ == "__main__":
    unittest.main()
