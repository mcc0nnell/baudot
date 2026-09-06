#include "BaudotCapabilities.h"

#include <celix/BundleActivator.h>

#include <memory>
#include <string_view>

namespace baudot::celixlab {
namespace {

class FaultInjectedRealtimeTextTransport final : public IRealtimeTextTransport {
public:
    CapabilityDecision evaluate(std::string_view /*payload*/) override {
        return {
            true,
            "FAULT_INJECTED_FAIL_OPEN",
            "negative-control bundle deliberately accepts invalid realtime-text input"
        };
    }
};

class FaultInjectedRealtimeTextBundleActivator {
public:
    explicit FaultInjectedRealtimeTextBundleActivator(const std::shared_ptr<celix::BundleContext>& ctx) {
        registration = ctx->registerService<IRealtimeTextTransport>(std::make_shared<FaultInjectedRealtimeTextTransport>())
            .addProperty("baudot.capability", IRealtimeTextTransport::NAME)
            .addProperty("baudot.capability.version", IRealtimeTextTransport::VERSION)
            .addProperty("baudot.control", "fault-injected")
            .setRegisterAsync(false)
            .build();
    }

private:
    std::shared_ptr<celix::ServiceRegistration> registration{};
};

} // namespace
} // namespace baudot::celixlab

CELIX_GEN_CXX_BUNDLE_ACTIVATOR(baudot::celixlab::FaultInjectedRealtimeTextBundleActivator)
