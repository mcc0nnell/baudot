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

constexpr std::string_view PJSIP_IDENTITY = "pjsip/pjproject-2.17@5a457451fa2712ba18e12b01738e8ff3af2b26fd";
constexpr std::string_view INVITE_FIXTURE =
    "INVITE sip:callee@example.invalid SIP/2.0\r\n"
    "Via: SIP/2.0/UDP 127.0.0.1:5060;branch=z9hG4bK-baudot-celix-lifecycle\r\n"
    "Max-Forwards: 70\r\n"
    "From: <sip:caller@example.invalid>;tag=baudot-celix-lifecycle\r\n"
    "To: <sip:callee@example.invalid>\r\n"
    "Call-ID: baudot-celix-lifecycle@example.invalid\r\n"
    "CSeq: 1 INVITE\r\n"
    "Content-Type: application/sdp\r\n"
    "Content-Length: 121\r\n\r\n"
    "v=0\r\n"
    "o=- 1 1 IN IP4 127.0.0.1\r\n"
    "s=Baudot Celix\r\n"
    "c=IN IP4 127.0.0.1\r\n"
    "t=0 0\r\n"
    "m=text 4000 RTP/AVP 98\r\n"
    "a=rtpmap:98 t140/1000\r\n";

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

void emit(std::string_view phase, std::string_view capability, std::string_view verdict, std::string_view detail) {
    std::cout << "{\"type\":\"baudot.celix.lifecycle-observation\""
              << ",\"phase\":\"" << jsonEscape(phase) << "\""
              << ",\"capability\":\"" << jsonEscape(capability) << "\""
              << ",\"verdict\":\"" << jsonEscape(verdict) << "\""
              << ",\"detail\":\"" << jsonEscape(detail) << "\"}" << std::endl;
}

void emitAuthorityBoundary(std::string_view phase) {
    emit(phase, "AuthorityBoundary", "NOT_MODELED", "bundle lifecycle does not establish SIP/SDP/T.140 conformance, authentication, authorization, TRS business authority, or regulatory compliance");
}

std::optional<CapabilityDecision> evaluateParser(const std::shared_ptr<celix::BundleContext>& ctx) {
    std::optional<CapabilityDecision> decision;
    const bool found = ctx->useService<ISignalingParser>()
        .addUseCallback([&decision](ISignalingParser& parser) { decision = parser.parse(INVITE_FIXTURE); })
        .build();
    return found ? decision : std::nullopt;
}

std::optional<CapabilityDecision> evaluateAdmission(const std::shared_ptr<celix::BundleContext>& ctx) {
    std::optional<CapabilityDecision> decision;
    const bool found = ctx->useService<ICallAdmission>()
        .addUseCallback([&decision](ICallAdmission& admission) { decision = admission.evaluate(INVITE_FIXTURE); })
        .build();
    return found ? decision : std::nullopt;
}

bool emitExpectedActiveCapabilities(const std::shared_ptr<celix::BundleContext>& ctx, std::string_view phase) {
    const auto parser = evaluateParser(ctx);
    if (!parser.has_value() || parser->verdict != "PJSIP_PARSE_ACCEPTED") {
        std::cerr << phase << ": parser capability missing or unexpected" << std::endl;
        return false;
    }
    emit(phase, "SignalingParser", parser->verdict, parser->detail);

    const auto admission = evaluateAdmission(ctx);
    if (!admission.has_value() || admission->verdict != "PJSIP_UAS_TEXT_PROFILE_ADMITTED") {
        std::cerr << phase << ": admission capability missing or unexpected" << std::endl;
        return false;
    }
    emit(phase, "CallAdmission", admission->verdict, admission->detail);
    emitAuthorityBoundary(phase);
    return true;
}

} // namespace
} // namespace baudot::celixlab

int main(int argc, char** argv) {
    using namespace baudot::celixlab;
    if (argc != 2) {
        std::cerr << "usage: baudot_celix_pjsip_lifecycle <pjsip-capability-bundle.zip>" << std::endl;
        return EXIT_FAILURE;
    }

    celix::Properties properties{};
    properties.set("CELIX_FRAMEWORK_CLEAN_CACHE_DIR_ON_CREATE", "true");
    properties.set("CELIX_FRAMEWORK_CACHE_DIR", ".baudot-celix-pjsip-lifecycle-cache");
    properties.set("CELIX_LOGGING_DEFAULT_ACTIVE_LOG_LEVEL", "warning");
    auto framework = celix::createFramework(properties);
    auto ctx = framework->getFrameworkBundleContext();

    const long capabilityBundleId = ctx->installBundle(argv[1], true);
    if (capabilityBundleId < 0 || !emitExpectedActiveCapabilities(ctx, "active")) {
        return EXIT_FAILURE;
    }

    if (!ctx->stopBundle(capabilityBundleId)) {
        return EXIT_FAILURE;
    }
    if (ctx->findService<ISignalingParser>() >= 0 || ctx->findService<ICallAdmission>() >= 0) {
        std::cerr << "PJSIP services remained registered after bundle stop" << std::endl;
        return EXIT_FAILURE;
    }
    emit("stopped", "SignalingParser", "CAPABILITY_MISSING", "PJSIP capability bundle stopped; no ISignalingParser service remains registered");
    emit("stopped", "CallAdmission", "CAPABILITY_MISSING", "PJSIP capability bundle stopped; no ICallAdmission service remains registered");
    emitAuthorityBoundary("stopped");

    if (!ctx->startBundle(capabilityBundleId) || !emitExpectedActiveCapabilities(ctx, "restored")) {
        return EXIT_FAILURE;
    }
    return EXIT_SUCCESS;
}
