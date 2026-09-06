#include "BaudotCapabilities.h"

#include <celix/BundleActivator.h>

#include <iostream>
#include <memory>
#include <string>
#include <string_view>

namespace baudot::celixlab {
namespace {

std::string jsonEscape(std::string_view value) {
    std::string out;
    out.reserve(value.size());
    for (const char ch : value) {
        switch (ch) {
            case '\\': out += "\\\\"; break;
            case '"': out += "\\\""; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            default: out += ch; break;
        }
    }
    return out;
}

class JsonEvidenceEmitter final : public IEvidenceEmitter {
public:
    void emit(const EvidenceObservation& observation) override {
        std::cout
            << "{\"type\":\"baudot.celix.observation\",\"profile\":\""
            << jsonEscape(observation.profile)
            << "\",\"capability\":\"" << jsonEscape(observation.capability)
            << "\",\"verdict\":\"" << jsonEscape(observation.verdict)
            << "\",\"detail\":\"" << jsonEscape(observation.detail)
            << "\"}" << std::endl;
    }
};

class EvidenceEmitterBundleActivator {
public:
    explicit EvidenceEmitterBundleActivator(const std::shared_ptr<celix::BundleContext>& ctx) {
        registration = ctx->registerService<IEvidenceEmitter>(std::make_shared<JsonEvidenceEmitter>())
            .addProperty("baudot.capability", IEvidenceEmitter::NAME)
            .addProperty("baudot.capability.version", IEvidenceEmitter::VERSION)
            .setRegisterAsync(false)
            .build();
    }

private:
    std::shared_ptr<celix::ServiceRegistration> registration{};
};

} // namespace
} // namespace baudot::celixlab

CELIX_GEN_CXX_BUNDLE_ACTIVATOR(baudot::celixlab::EvidenceEmitterBundleActivator)
