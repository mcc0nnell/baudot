#include "BaudotCapabilities.h"

#include <celix/BundleActivator.h>

#include <memory>
#include <string>

namespace baudot::celixlab {
namespace {

class SyntheticActorContextProvider final : public IActorContextProvider {
public:
    ActorContextDecision current() override {
#if defined(BAUDOT_ACTOR_AUTHENTICATED)
        ActorContext actor{
            true,
            false,
            "provider-a-operator",
            "operator",
            "synthetic-tenant-a",
            "provider-a",
            {"provider-operator"},
            "celix-session-authenticated-001",
            "2026-09-06T00:00:00Z",
            "password-synthetic"
        };
        return {
            std::move(actor),
            "SHIRO_CONTEXT_AUTHENTICATED",
            "bounded synthetic actor/session projection derived from the qualified Shiro contract in PR #127; not a Shiro runtime"
        };
#elif defined(BAUDOT_ACTOR_REMEMBERED_ONLY)
        ActorContext actor{
            false,
            true,
            "provider-a-operator",
            "operator",
            "synthetic-tenant-a",
            "provider-a",
            {"provider-operator"},
            "",
            "",
            "remembered-only"
        };
        return {
            std::move(actor),
            "SHIRO_CONTEXT_REMEMBERED_NOT_AUTHENTICATED",
            "remembered-only synthetic actor derived from the Shiro boundary in PR #127; protected authorization must not treat it as authenticated"
        };
#else
#error "Select a Baudot actor-context profile"
#endif
    }
};

class ActorContextBundleActivator {
public:
    explicit ActorContextBundleActivator(const std::shared_ptr<celix::BundleContext>& ctx) {
        registration = ctx->registerService<IActorContextProvider>(
                std::make_shared<SyntheticActorContextProvider>())
            .addProperty("baudot.capability", IActorContextProvider::NAME)
            .addProperty("baudot.capability.version", IActorContextProvider::VERSION)
            .addProperty("baudot.semantic-source", "Shiro boundary PR-127")
            .addProperty("baudot.control", "contract-derived-fixture")
            .setRegisterAsync(false)
            .build();
    }

private:
    std::shared_ptr<celix::ServiceRegistration> registration{};
};

} // namespace
} // namespace baudot::celixlab

CELIX_GEN_CXX_BUNDLE_ACTIVATOR(baudot::celixlab::ActorContextBundleActivator)
