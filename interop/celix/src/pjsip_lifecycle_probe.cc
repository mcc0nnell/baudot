#include "BaudotCapabilities.h"

#include <celix/FrameworkFactory.h>

#include <cstdlib>
#include <iostream>
#include <memory>
#include <optional>
#include <string>
#include <string_view>

namespace baudot::celixlab {
namespace {

constexpr std::string_view PJSIP_IDENTITY =
    "pjsip/pjproject-2.17@5a457451fa2712ba18e12b01738e8ff3af2b26fd";

constexpr std::string_view INVITE_FIXTURE =
    "INVITE sip:callee@example.invalid SIP/2.0\r\n"
    "Via: SIP/2.0/UDP 127.0.0.1:5060;branch=z9hG4bK-baudot-celix-lifecycle\r\n"
    "Max-Forwards: 70\r\n"
    "From: <sip:caller@example.invalid>;tag=baudot-celix-lifecycle\r\n"
    "To: <sip:callee@example.invalid>\r\n"
    "Call-ID: baudot-celix-lifecycle@example.invalid\r\n"
    "CSeq: 1 INVITE\r\n"
    "Content-Length: 0\r\n"
    "\r\n";

std::string jsonEscape(std::string_view input) {
    std::string escaped;
    escaped.reserve(input.size());
    for (const char ch : input) {
        switch (ch) {
            case '\\': escaped += "\\\\"; break;
            case '"': escaped += "\\\""; break;
            case '\n': escaped += "\\n"; break;
            case '\r': escaped += "\\r"; break;
            case '\t': escaped += "\\t"; break;
            default: escaped += ch; break;
        }
    }
    return escaped;
}

void emit(
    std::string_view phase,
    std::string_view capability,
    std::string_view verdict,
    std::string_view detail) {
    std::cout
        << "{\"type\":\"baudot.celix.lifecycle-observation\""
        << ",\"phase\":\"" << jsonEscape(phase) << "\""
        << ",\"capability\":\"" << jsonEscape(capability) << "\""
        << ",\"verdict\":\"" << jsonEscape(verdict) << "\""
        << ",\"detail\":\"" << jsonEscape(detail) << "\"}"
        << std::endl;
}

void emitAuthorityBoundary(std::string_view phase) {
    emit(
        phase,
        "AuthorityBoundary",
        "NOT_MODELED",
        "bundle lifecycle does not establish authentication, authorization, protocol conformance, TRS business authority, or regulatory compliance");
}

std::optional<CapabilityDecision> evaluateAdmission(const std::shared_ptr<celix::BundleContext>& ctx) {
    std::optional<CapabilityDecision> decision;
    const bool found = ctx->useService<ICallAdmission>()
        .addUseCallback([&decision](ICallAdmission& admission) {
            decision = admission.evaluate(INVITE_FIXTURE);
        })
        .build();
    if (!found) {
        return std::nullopt;
    }
    return decision;
}

bool emitExpectedActiveAdmission(
    const std::shared_ptr<celix::BundleContext>& ctx,
    std::string_view phase) {
    const auto decision = evaluateAdmission(ctx);
    if (!decision.has_value()) {
        std::cerr << phase << ": ICallAdmission service missing" << std::endl;
        return false;
    }
    if (decision->verdict != "PJSIP_PARSE_ACCEPTED") {
        std::cerr << phase << ": unexpected admission verdict " << decision->verdict << std::endl;
        return false;
    }
    emit(phase, "CallAdmission", decision->verdict, decision->detail);
    emitAuthorityBoundary(phase);
    return true;
}

} // namespace
} // namespace baudot::celixlab

int main(int argc, char** argv) {
    using namespace baudot::celixlab;

    if (argc != 2) {
        std::cerr << "usage: baudot_celix_pjsip_lifecycle <pjsip-call-admission-bundle.zip>" << std::endl;
        return EXIT_FAILURE;
    }

    celix::Properties properties{};
    properties.set("CELIX_FRAMEWORK_CLEAN_CACHE_DIR_ON_CREATE", "true");
    properties.set("CELIX_FRAMEWORK_CACHE_DIR", ".baudot-celix-pjsip-lifecycle-cache");
    properties.set("CELIX_LOGGING_DEFAULT_ACTIVE_LOG_LEVEL", "warning");

    auto framework = celix::createFramework(properties);
    auto ctx = framework->getFrameworkBundleContext();

    const long admissionBundleId = ctx->installBundle(argv[1], true);
    if (admissionBundleId < 0) {
        std::cerr << "failed to install/start PJSIP call-admission bundle" << std::endl;
        return EXIT_FAILURE;
    }

    if (!emitExpectedActiveAdmission(ctx, "active")) {
        return EXIT_FAILURE;
    }

    if (!ctx->stopBundle(admissionBundleId)) {
        std::cerr << "failed to stop PJSIP call-admission bundle" << std::endl;
        return EXIT_FAILURE;
    }

    if (ctx->findService<ICallAdmission>() >= 0) {
        std::cerr << "ICallAdmission remained registered after bundle stop" << std::endl;
        return EXIT_FAILURE;
    }
    emit(
        "stopped",
        "CallAdmission",
        "CAPABILITY_MISSING",
        "PJSIP call-admission bundle stopped; no ICallAdmission service remains registered");
    emitAuthorityBoundary("stopped");

    if (!ctx->startBundle(admissionBundleId)) {
        std::cerr << "failed to restart PJSIP call-admission bundle" << std::endl;
        return EXIT_FAILURE;
    }

    if (!emitExpectedActiveAdmission(ctx, "restored")) {
        return EXIT_FAILURE;
    }

    return EXIT_SUCCESS;
}
