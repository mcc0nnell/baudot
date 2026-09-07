#include "BaudotCapabilities.h"

#include <celix/BundleActivator.h>

#include <memory>
#include <string>
#include <string_view>

namespace baudot::celixlab {
namespace {

constexpr std::string_view PART64_SEMANTIC_SOURCE =
    "Part 64 registration/numbering/per-call validation contract PR-126";

class TrsBusinessAuthority final : public ITrsBusinessAuthority {
public:
    CapabilityDecision evaluateOrdinaryCallPlacement(
        const ActorContext& actor,
        const CapabilityDecision& authorization,
        const TrsCallFacts& facts) override {
        if (!actor.authenticated) {
            return {
                false,
                "TRS_BUSINESS_NOT_EVALUATED_AUTHENTICATION_REQUIRED",
                "ordinary-call business authority was not evaluated because the application actor is not authenticated"
            };
        }

        if (!authorization.accepted) {
            return {
                false,
                "TRS_BUSINESS_NOT_EVALUATED_AUTHORIZATION_REQUIRED",
                "ordinary-call business authority was not evaluated because protected-domain authorization was not ALLOW"
            };
        }

        if (facts.emergencyException) {
            return {
                false,
                "TRS_EMERGENCY_EXCEPTION_OUT_OF_SCOPE",
                "PR #126 models the emergency validation exception separately; this Celix service is intentionally limited to ordinary call placement"
            };
        }

        if (facts.serviceType != "VRS") {
            return {
                false,
                "TRS_SERVICE_TYPE_OUT_OF_PROFILE",
                "this first business-authority composition is limited to the synthetic VRS ordinary-call profile from PR #126"
            };
        }

        if (!facts.routePresent) {
            return {
                false,
                "TRS_ORDINARY_CALL_PLACEMENT_DENIED_ROUTE_MISSING",
                "synthetic TRS Numbering Directory route was absent; route presence is required but is not itself registration or validation authority"
            };
        }

        if (!facts.registered) {
            return {
                false,
                "TRS_ORDINARY_CALL_PLACEMENT_DENIED_REGISTRATION_REQUIRED",
                "synthetic user registration evidence was absent; route presence did not promote the user to registered state"
            };
        }

        if (!facts.identityVerified) {
            return {
                false,
                "TRS_ORDINARY_CALL_PLACEMENT_DENIED_IDENTITY_VERIFICATION_REQUIRED",
                "synthetic identity-verification evidence was absent; registration did not promote identity verification"
            };
        }

        if (!facts.perCallValidated) {
            return {
                false,
                "TRS_ORDINARY_CALL_PLACEMENT_DENIED_VALIDATION",
                "PR #126 per-call validation failed; Ranger ALLOW and signaling admission cannot override the ordinary-call validation gate"
            };
        }

        return {
            true,
            "TRS_ORDINARY_CALL_PLACEMENT_ALLOWED",
            "synthetic route, registration, identity-verification, and per-call validation facts satisfy the narrow ordinary-call placement gate from PR #126; no call connection, compensability, claim, payment, or compliance inference"
        };
    }
};

class TrsBusinessAuthorityBundleActivator {
public:
    explicit TrsBusinessAuthorityBundleActivator(const std::shared_ptr<celix::BundleContext>& ctx) {
        registration = ctx->registerService<ITrsBusinessAuthority>(
                std::make_shared<TrsBusinessAuthority>())
            .addProperty("baudot.capability", ITrsBusinessAuthority::NAME)
            .addProperty("baudot.capability.version", ITrsBusinessAuthority::VERSION)
            .addProperty("baudot.semantic-source", std::string{PART64_SEMANTIC_SOURCE})
            .addProperty("baudot.control", "part64-contract-derived-fixture")
            .setRegisterAsync(false)
            .build();
    }

private:
    std::shared_ptr<celix::ServiceRegistration> registration{};
};

} // namespace
} // namespace baudot::celixlab

CELIX_GEN_CXX_BUNDLE_ACTIVATOR(baudot::celixlab::TrsBusinessAuthorityBundleActivator)
