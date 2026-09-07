#include "BaudotCapabilities.h"

#include <celix/BundleActivator.h>

#include <memory>
#include <optional>
#include <string>
#include <string_view>

namespace baudot::celixlab {
namespace {

constexpr std::string_view PJSIP_TEXT_ONLY_INVITE_FIXTURE =
    "INVITE sip:callee@example.invalid SIP/2.0\r\n"
    "Via: SIP/2.0/UDP 127.0.0.1:5060;branch=z9hG4bK-baudot-celix\r\n"
    "Max-Forwards: 70\r\n"
    "From: <sip:caller@example.invalid>;tag=baudot-celix\r\n"
    "To: <sip:callee@example.invalid>\r\n"
    "Call-ID: baudot-celix-pjsip@example.invalid\r\n"
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

constexpr std::string_view PJSIP_PARSE_ONLY_INVITE_FIXTURE =
    "INVITE sip:callee@example.invalid SIP/2.0\r\n"
    "Via: SIP/2.0/UDP 127.0.0.1:5060;branch=z9hG4bK-baudot-celix-parse-only\r\n"
    "Max-Forwards: 70\r\n"
    "From: <sip:caller@example.invalid>;tag=baudot-celix-parse-only\r\n"
    "To: <sip:callee@example.invalid>\r\n"
    "Call-ID: baudot-celix-parse-only@example.invalid\r\n"
    "CSeq: 1 INVITE\r\n"
    "Content-Length: 0\r\n"
    "\r\n";

#if defined(BAUDOT_PROFILE_GOOD)
constexpr std::string_view PROFILE = "good";
constexpr std::string_view SIGNALING_FIXTURE = PJSIP_TEXT_ONLY_INVITE_FIXTURE;
constexpr std::string_view RTT_FIXTURE = "hello";
#elif defined(BAUDOT_PROFILE_FAULT_INJECTED)
constexpr std::string_view PROFILE = "fault-injected";
constexpr std::string_view SIGNALING_FIXTURE = "MALFORMED_SIGNALING";
constexpr std::string_view RTT_FIXTURE = "INVALID:RTT";
#elif defined(BAUDOT_PROFILE_MISSING_RTT)
constexpr std::string_view PROFILE = "missing-rtt";
constexpr std::string_view SIGNALING_FIXTURE = PJSIP_TEXT_ONLY_INVITE_FIXTURE;
constexpr std::string_view RTT_FIXTURE = "hello";
#elif defined(BAUDOT_PROFILE_PARSED_NOT_ADMITTED)
constexpr std::string_view PROFILE = "parsed-not-admitted";
constexpr std::string_view SIGNALING_FIXTURE = PJSIP_PARSE_ONLY_INVITE_FIXTURE;
constexpr std::string_view RTT_FIXTURE = "hello";
#else
#error "A Baudot Celix probe profile must be selected"
#endif

class CompositionProbeBundleActivator {
public:
    explicit CompositionProbeBundleActivator(const std::shared_ptr<celix::BundleContext>& ctx) {
        auto emit = [&ctx](const EvidenceObservation& observation) {
            return ctx->useService<IEvidenceEmitter>()
                .addUseCallback([&observation](IEvidenceEmitter& emitter) { emitter.emit(observation); })
                .build();
        };

        std::optional<CapabilityDecision> parserDecision;
        const bool parserFound = ctx->useService<ISignalingParser>()
            .addUseCallback([&parserDecision](ISignalingParser& parser) {
                parserDecision = parser.parse(SIGNALING_FIXTURE);
            })
            .build();

        if (parserFound && parserDecision.has_value()) {
            emit({std::string{PROFILE}, "SignalingParser", parserDecision->verdict, parserDecision->detail});
        } else {
            emit({std::string{PROFILE}, "SignalingParser", "CAPABILITY_MISSING", "no SignalingParser service was available"});
        }

        std::optional<CapabilityDecision> admissionDecision;
        const bool admissionFound = ctx->useService<ICallAdmission>()
            .addUseCallback([&admissionDecision](ICallAdmission& admission) {
                admissionDecision = admission.evaluate(SIGNALING_FIXTURE);
            })
            .build();

        if (admissionFound && admissionDecision.has_value()) {
            emit({std::string{PROFILE}, "CallAdmission", admissionDecision->verdict, admissionDecision->detail});
        } else {
            emit({std::string{PROFILE}, "CallAdmission", "CAPABILITY_MISSING", "no CallAdmission service was available"});
        }

        std::optional<CapabilityDecision> rttDecision;
        const bool rttFound = ctx->useService<IRealtimeTextTransport>()
            .addUseCallback([&rttDecision](IRealtimeTextTransport& transport) {
                rttDecision = transport.evaluate(RTT_FIXTURE);
            })
            .build();

        if (rttFound && rttDecision.has_value()) {
            emit({std::string{PROFILE}, "RealtimeTextTransport", rttDecision->verdict, rttDecision->detail});
        } else {
            emit({std::string{PROFILE}, "RealtimeTextTransport", "CAPABILITY_MISSING", "no RealtimeTextTransport service was available"});
        }

        emit({
            std::string{PROFILE},
            "AuthorityBoundary",
            "NOT_MODELED",
            "parser success, admission, authentication, authorization, TRS business authority, and regulatory compliance remain distinct decisions"
        });
    }
};

} // namespace
} // namespace baudot::celixlab

CELIX_GEN_CXX_BUNDLE_ACTIVATOR(baudot::celixlab::CompositionProbeBundleActivator)
