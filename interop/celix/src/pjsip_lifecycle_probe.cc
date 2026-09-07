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
constexpr std::string_view ADMISSION_IDENTITY =
    "baudot/native-pjsip-uas-text-profile-v1";

constexpr std::string_view INVITE_FIXTURE =
    "INVITE sip:callee@example.invalid SIP/2.0\r\n"
    "Via: SIP/2.0/UDP 127.0.0.1:5060;branch=z9hG4bK-baudot-celix-lifecycle\r\n"
    "Max-Forwards: 70\r\n"
    "From: <sip:caller@example.invalid>;tag=baudot-celix-lifecycle\r\n"
    "To: <sip:callee@example.invalid>\r\n"
    "Call-ID: baudot-celix-lifecycle@example.invalid\r\n"
    "CSeq: 1 INVITE\r\n"
    "Content-Type: application/sdp\r\n"
    "Content-Length: 121\r\n"
    "\r\n"
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
        "parser dependency lifecycle does not establish SIP/SDP/T.140 conformance, authentication, authorization, TRS business authority, or regulatory compliance");
}

std::optional<CapabilityDecision> evaluateParser(const std::shared_ptr<celix::BundleContext>& ctx) {
    std::optional<CapabilityDecision> decision;
    const bool found = ctx->useService<ISignalingParser>()
        .addUseCallback([&decision](ISignalingParser& parser) {
            decision = parser.parse(INVITE_FIXTURE);
        })
        .build();
    return found ? decision : std::nullopt;
}

std::optional<CapabilityDecision> evaluateAdmission(const std::shared_ptr<celix::BundleContext>& ctx) {
    std::optional<CapabilityDecision> decision;
    const bool found = ctx->useService<ICallAdmission>()
        .addUseCallback([&decision](ICallAdmission& admission) {
            decision = admission.evaluate(INVITE_FIXTURE);
        })
        .build();
    return found ? decision : std::nullopt;
}

std::optional<CapabilityDecision> evaluateRtt(const std::shared_ptr<celix::BundleContext>& ctx) {
    std::optional<CapabilityDecision> decision;
    const bool found = ctx->useService<IRealtimeTextTransport>()
        .addUseCallback([&decision](IRealtimeTextTransport& rtt) {
            decision = rtt.evaluate("hello");
        })
        .build();
    return found ? decision : std::nullopt;
}

bool emitExpectedHealthyCapabilities(
    const std::shared_ptr<celix::BundleContext>& ctx,
    std::string_view phase) {
    const auto parser = evaluateParser(ctx);
    const auto admission = evaluateAdmission(ctx);
    const auto rtt = evaluateRtt(ctx);

    if (!parser.has_value() || parser->verdict != "PJSIP_PARSE_ACCEPTED") {
        std::cerr << phase << ": expected healthy parser" << std::endl;
        return false;
    }
    if (!admission.has_value() || admission->verdict != "PJSIP_UAS_TEXT_PROFILE_ADMITTED") {
        std::cerr << phase << ": expected healthy admission" << std::endl;
        return false;
    }
    if (!rtt.has_value() || rtt->verdict != "RTT_FIXTURE_ACCEPTED") {
        std::cerr << phase << ": expected healthy RTT" << std::endl;
        return false;
    }

    emit(phase, "SignalingParser", parser->verdict, parser->detail);
    emit(phase, "CallAdmission", admission->verdict, admission->detail);
    emit(phase, "RealtimeTextTransport", rtt->verdict, rtt->detail);
    emitAuthorityBoundary(phase);
    return true;
}

} // namespace
} // namespace baudot::celixlab

int main(int argc, char** argv) {
    using namespace baudot::celixlab;

    if (argc != 4) {
        std::cerr
            << "usage: baudot_celix_pjsip_lifecycle <parser-bundle.zip> <admission-bundle.zip> <rtt-bundle.zip>"
            << std::endl;
        return EXIT_FAILURE;
    }

    celix::Properties properties{};
    properties.set("CELIX_FRAMEWORK_CLEAN_CACHE_DIR_ON_CREATE", "true");
    properties.set("CELIX_FRAMEWORK_CACHE_DIR", ".baudot-celix-pjsip-lifecycle-cache");
    properties.set("CELIX_LOGGING_DEFAULT_ACTIVE_LOG_LEVEL", "warning");

    auto framework = celix::createFramework(properties);
    auto ctx = framework->getFrameworkBundleContext();

    const long parserBundleId = ctx->installBundle(argv[1], true);
    const long admissionBundleId = ctx->installBundle(argv[2], true);
    const long rttBundleId = ctx->installBundle(argv[3], true);
    if (parserBundleId < 0 || admissionBundleId < 0 || rttBundleId < 0) {
        std::cerr << "failed to install/start parser, admission, or RTT bundle" << std::endl;
        return EXIT_FAILURE;
    }

    const long admissionServiceId = ctx->findService<ICallAdmission>();
    const long rttServiceId = ctx->findService<IRealtimeTextTransport>();
    if (admissionServiceId < 0 || rttServiceId < 0) {
        std::cerr << "admission or RTT service missing before parser lifecycle test" << std::endl;
        return EXIT_FAILURE;
    }

    if (!emitExpectedHealthyCapabilities(ctx, "active")) {
        return EXIT_FAILURE;
    }

    if (!ctx->stopBundle(parserBundleId)) {
        std::cerr << "failed to stop only the PJSIP parser bundle" << std::endl;
        return EXIT_FAILURE;
    }

    if (ctx->findService<ISignalingParser>() >= 0) {
        std::cerr << "ISignalingParser remained registered after parser bundle stop" << std::endl;
        return EXIT_FAILURE;
    }
    if (ctx->findService<ICallAdmission>() != admissionServiceId) {
        std::cerr << "ICallAdmission service changed or disappeared when parser stopped" << std::endl;
        return EXIT_FAILURE;
    }
    if (ctx->findService<IRealtimeTextTransport>() != rttServiceId) {
        std::cerr << "RTT service changed or disappeared when parser stopped" << std::endl;
        return EXIT_FAILURE;
    }

    emit(
        "parser-stopped",
        "SignalingParser",
        "CAPABILITY_MISSING",
        "PJSIP parser bundle stopped; ISignalingParser is absent while admission and RTT bundles remain active");

    const auto failClosedAdmission = evaluateAdmission(ctx);
    if (!failClosedAdmission.has_value() || failClosedAdmission->verdict != "PARSER_CAPABILITY_MISSING") {
        std::cerr << "admission did not fail closed when parser disappeared" << std::endl;
        return EXIT_FAILURE;
    }
    emit(
        "parser-stopped",
        "CallAdmission",
        failClosedAdmission->verdict,
        failClosedAdmission->detail);

    const auto liveRtt = evaluateRtt(ctx);
    if (!liveRtt.has_value() || liveRtt->verdict != "RTT_FIXTURE_ACCEPTED") {
        std::cerr << "RTT did not remain live while parser was stopped" << std::endl;
        return EXIT_FAILURE;
    }
    emit("parser-stopped", "RealtimeTextTransport", liveRtt->verdict, liveRtt->detail);
    emitAuthorityBoundary("parser-stopped");

    if (!ctx->startBundle(parserBundleId)) {
        std::cerr << "failed to restart PJSIP parser bundle" << std::endl;
        return EXIT_FAILURE;
    }

    if (ctx->findService<ICallAdmission>() != admissionServiceId) {
        std::cerr << "ICallAdmission service changed across parser restoration" << std::endl;
        return EXIT_FAILURE;
    }
    if (ctx->findService<IRealtimeTextTransport>() != rttServiceId) {
        std::cerr << "RTT service changed across parser restoration" << std::endl;
        return EXIT_FAILURE;
    }

    if (!emitExpectedHealthyCapabilities(ctx, "restored")) {
        return EXIT_FAILURE;
    }

    return EXIT_SUCCESS;
}
