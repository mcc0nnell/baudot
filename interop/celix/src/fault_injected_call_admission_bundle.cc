#include "BaudotCapabilities.h"

#include <celix/BundleActivator.h>

#include <memory>
#include <string_view>

namespace baudot::celixlab {
namespace {

class FaultInjectedCallAdmission final : public ICallAdmission {
public:
    CapabilityDecision evaluate(std::string_view /*signaling*/) override {
        return {
            true,
            "FAULT_INJECTED_FAIL_OPEN",
            "negative-control bundle deliberately admits malformed signaling"
        };
    }
};

class FaultInjectedCallAdmissionBundleActivator {
public:
    explicit FaultInjectedCallAdmissionBundleActivator(const std::shared_ptr<celix::BundleContext>& ctx) {
        registration = ctx->registerService<ICallAdmission>(std::make_shared<FaultInjectedCallAdmission>())
            .addProperty("baudot.capability", ICallAdmission::NAME)
            .addProperty("baudot.capability.version", ICallAdmission::VERSION)
            .addProperty("baudot.control", "fault-injected")
            .setRegisterAsync(false)
            .build();
    }

private:
    std::shared_ptr<celix::ServiceRegistration> registration{};
};

} // namespace
} // namespace baudot::celixlab

CELIX_GEN_CXX_BUNDLE_ACTIVATOR(baudot::celixlab::FaultInjectedCallAdmissionBundleActivator)
