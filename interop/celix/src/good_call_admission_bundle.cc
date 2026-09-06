#include "BaudotCapabilities.h"

#include <celix/BundleActivator.h>

#include <memory>
#include <string_view>

namespace baudot::celixlab {
namespace {

class GoodCallAdmission final : public ICallAdmission {
public:
    CapabilityDecision evaluate(std::string_view signaling) override {
        const bool looksLikeSyntheticInvite =
            signaling.rfind("INVITE ", 0) == 0 && signaling.find(" SIP/2.0") != std::string_view::npos;
        if (looksLikeSyntheticInvite) {
            return {true, "ADMISSION_FIXTURE_ACCEPTED", "narrow synthetic SIP-shaped fixture accepted"};
        }
        return {false, "ADMISSION_FIXTURE_REJECTED", "input fell outside the narrow synthetic admission fixture"};
    }
};

class GoodCallAdmissionBundleActivator {
public:
    explicit GoodCallAdmissionBundleActivator(const std::shared_ptr<celix::BundleContext>& ctx) {
        registration = ctx->registerService<ICallAdmission>(std::make_shared<GoodCallAdmission>())
            .addProperty("baudot.capability", ICallAdmission::NAME)
            .addProperty("baudot.capability.version", ICallAdmission::VERSION)
            .addProperty("baudot.control", "good")
            .setRegisterAsync(false)
            .build();
    }

private:
    std::shared_ptr<celix::ServiceRegistration> registration{};
};

} // namespace
} // namespace baudot::celixlab

CELIX_GEN_CXX_BUNDLE_ACTIVATOR(baudot::celixlab::GoodCallAdmissionBundleActivator)
