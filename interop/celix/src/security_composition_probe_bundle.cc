#include "BaudotCapabilities.h"

#include <celix/BundleActivator.h>

#include <memory>
#include <optional>
#include <string>
#include <string_view>

namespace baudot::celixlab {
namespace {

constexpr std::string_view INVITE_FIXTURE =
    "INVITE sip:callee@example.invalid SIP/2.0\r\n"
    "Via: SIP/2.0/UDP 127.0.0.1:5060;branch=z9hG4bK-baudot-celix-security\r\n"
    "Max-Forwards: 70\r\n"
    "From: <sip:caller@example.invalid>;tag=baudot-celix-security\r\n"
    "To: <sip:callee@example.invalid>\r\n"
    "Call-ID: baudot-celix-security@example.invalid\r\n"
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

#if defined(BAUDOT_SECURITY_GOOD)
constexpr std::string_view PROFILE = "security-good";
#elif defined(BAUDOT_SECURITY_DENY)
constexpr std::string_view PROFILE = "security-authorization-deny";
#elif defined(BAUDOT_SECURITY_REMEMBERED)
constexpr std::string_view PROFILE = "security-remembered-only";
#else
#error "Select a Baudot security composition profile"
#endif

class SecurityCompositionProbeBundleActivator {
public:
    explicit SecurityCompositionProbeBundleActivator(const std::shared_ptr<celix::BundleContext>& ctx) {
        auto emit = [&ctx](const EvidenceObservation& observation) {
            return ctx->useService<IEvidenceEmitter>()
                .addUseCallback([&observation](IEvidenceEmitter& emitter) { emitter.emit(observation); })
                .build();
        };

        std::optional<CapabilityDecision> parserDecision;
        const bool parserFound = ctx->useService<ISignalingParser>()
            .addUseCallback([&parserDecision](ISignalingParser& parser) {
                parserDecision = parser.parse(INVITE_FIXTURE);
            })
            .build();
        if (parserFound && parserDecision.has_value()) {
            emit({std::string{PROFILE}, "SignalingParser", parserDecision->verdict, parserDecision->detail});
        } else {
            emit({std::string{PROFILE}, "SignalingParser", "CAPABILITY_MISSING", "no signaling parser service was available"});
        }

        std::optional<CapabilityDecision> admissionDecision;
        const bool admissionFound = ctx->useService<ICallAdmission>()
            .addUseCallback([&admissionDecision](ICallAdmission& admission) {
                admissionDecision = admission.evaluate(INVITE_FIXTURE);
            })
            .build();
        if (admissionFound && admissionDecision.has_value()) {
            emit({std::string{PROFILE}, "CallAdmission", admissionDecision->verdict, admissionDecision->detail});
        } else {
            emit({std::string{PROFILE}, "CallAdmission", "CAPABILITY_MISSING", "no call admission service was available"});
        }

        std::optional<ActorContextDecision> actorDecision;
        const bool actorFound = ctx->useService<IActorContextProvider>()
            .addUseCallback([&actorDecision](IActorContextProvider& provider) {
                actorDecision = provider.current();
            })
            .build();

        if (actorFound && actorDecision.has_value()) {
            emit({
                std::string{PROFILE},
                "ActorAuthentication",
                actorDecision->verdict,
                actorDecision->detail + "; actorId=" + actorDecision->actor.actorId +
                    "; actorType=" + actorDecision->actor.actorType
            });
        } else {
            emit({std::string{PROFILE}, "ActorAuthentication", "CAPABILITY_MISSING", "no actor context service was available"});
        }

        std::optional<CapabilityDecision> authorizationDecision;
        if (actorDecision.has_value()) {
            const bool authorizationFound = ctx->useService<IAuthorizationService>()
                .addUseCallback([&authorizationDecision, &actorDecision](IAuthorizationService& authorization) {
                    authorizationDecision = authorization.authorize(
                        actorDecision->actor,
                        "telephone-number",
                        "QUERY",
                        "query");
                })
                .build();
            if (!authorizationFound) {
                authorizationDecision.reset();
            }
        }

        if (authorizationDecision.has_value()) {
            emit({std::string{PROFILE}, "Authorization", authorizationDecision->verdict, authorizationDecision->detail});
        } else {
            emit({std::string{PROFILE}, "Authorization", "CAPABILITY_MISSING", "no authorization decision was available"});
        }

        emit({
            std::string{PROFILE},
            "AuthorityBoundary",
            "NOT_MODELED",
            "parser, admission, application authentication, and Ranger-shaped authorization remain distinct from TRS business authority and regulatory compliance"
        });
    }
};

} // namespace
} // namespace baudot::celixlab

CELIX_GEN_CXX_BUNDLE_ACTIVATOR(baudot::celixlab::SecurityCompositionProbeBundleActivator)
