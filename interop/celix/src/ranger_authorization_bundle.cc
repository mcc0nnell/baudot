#include "BaudotCapabilities.h"

#include <celix/BundleActivator.h>

#include <memory>
#include <string>
#include <string_view>

namespace baudot::celixlab {
namespace {

constexpr std::string_view RANGER_SEMANTIC_SOURCE =
    "Ranger PDP contract PR-114";

class RangerContractAuthorization final : public IAuthorizationService {
public:
    CapabilityDecision authorize(
        const ActorContext& actor,
        std::string_view resourceType,
        std::string_view action,
        std::string_view permission) override {
        if (!actor.authenticated) {
            return {
                false,
                "AUTHORIZATION_NOT_EVALUATED_AUTHENTICATION_REQUIRED",
                "Ranger-shaped authorization adapter rejected the request before policy evaluation because the actor is not authenticated; no PDP call inferred"
            };
        }

        const bool expectedMapping =
            resourceType == "telephone-number" &&
            action == "QUERY" &&
            permission == "query";
        if (!expectedMapping) {
            return {
                false,
                "RANGER_MAPPING_REJECTED",
                "operation fell outside the neutral telephone-number/QUERY/query mapping from PR #114"
            };
        }

#if defined(BAUDOT_RANGER_ALLOW)
        return {
            true,
            "RANGER_ALLOW",
            "explicit synthetic ALLOW shaped by the Ranger PDP boundary in PR #114; composition fixture only, not a live Ranger decision"
        };
#elif defined(BAUDOT_RANGER_DENY)
        return {
            false,
            "RANGER_DENY",
            "explicit synthetic DENY shaped by the Ranger PDP boundary in PR #114; composition fixture only, not a live Ranger decision"
        };
#else
#error "Select a Baudot Ranger authorization profile"
#endif
    }
};

class RangerAuthorizationBundleActivator {
public:
    explicit RangerAuthorizationBundleActivator(const std::shared_ptr<celix::BundleContext>& ctx) {
        registration = ctx->registerService<IAuthorizationService>(
                std::make_shared<RangerContractAuthorization>())
            .addProperty("baudot.capability", IAuthorizationService::NAME)
            .addProperty("baudot.capability.version", IAuthorizationService::VERSION)
            .addProperty("baudot.semantic-source", std::string{RANGER_SEMANTIC_SOURCE})
            .addProperty("baudot.control", "contract-derived-fixture")
            .setRegisterAsync(false)
            .build();
    }

private:
    std::shared_ptr<celix::ServiceRegistration> registration{};
};

} // namespace
} // namespace baudot::celixlab

CELIX_GEN_CXX_BUNDLE_ACTIVATOR(baudot::celixlab::RangerAuthorizationBundleActivator)
