#include "BaudotCapabilities.h"

#include <celix/BundleActivator.h>

#include <memory>
#include <string_view>

namespace baudot::celixlab {
namespace {

class GoodRealtimeTextTransport final : public IRealtimeTextTransport {
public:
    CapabilityDecision evaluate(std::string_view payload) override {
        if (payload == "hello") {
            return {true, "RTT_FIXTURE_ACCEPTED", "narrow synthetic realtime-text fixture accepted"};
        }
        return {false, "RTT_FIXTURE_REJECTED", "input fell outside the narrow synthetic realtime-text fixture"};
    }
};

class GoodRealtimeTextBundleActivator {
public:
    explicit GoodRealtimeTextBundleActivator(const std::shared_ptr<celix::BundleContext>& ctx) {
        registration = ctx->registerService<IRealtimeTextTransport>(std::make_shared<GoodRealtimeTextTransport>())
            .addProperty("baudot.capability", IRealtimeTextTransport::NAME)
            .addProperty("baudot.capability.version", IRealtimeTextTransport::VERSION)
            .addProperty("baudot.control", "good")
            .setRegisterAsync(false)
            .build();
    }

private:
    std::shared_ptr<celix::ServiceRegistration> registration{};
};

} // namespace
} // namespace baudot::celixlab

CELIX_GEN_CXX_BUNDLE_ACTIVATOR(baudot::celixlab::GoodRealtimeTextBundleActivator)
