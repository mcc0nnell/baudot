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
    "Via: SIP/2.0/UDP 127.0.0.1:5060;branch=z9hG4bK-baudot-celix-business\r\n"
    "Max-Forwards: 70\r\n"
    "From: <sip:caller@example.invalid>;tag=baudot-celix-business\r\n"
    "To: <sip:callee@example.invalid>\r\n"
    "Call-ID: baudot-celix-business@example.invalid\r\n"
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

#if defined(BAUDOT_BUSINESS_GOOD)
constexpr std::string_view PROFILE = "business-good";
constexpr bool PER_CALL_VALIDATED = true;
#elif defined(BAUDOT_BUSINESS_VALIDATION_FAIL)
constexpr std::string_view PROFILE = "business-validation-fail";
constexpr bool PER_CALL_VALIDATED = false;
#elif defined(BAUDOT_BUSINESS_AUTHORIZATION_DENY)
constexpr std::string_view PROFILE = "business-authorization-deny";
constexpr bool PER_CALL_VALIDATED = true;
#else
#error "Select a Baudot TRS business composition profile"
#endif

class TrsBusinessCompositionProbeBundleActivator {
public:
    explicit TrsBusinessCompositionProbeBundleActivator(const std::shared_ptr<celix::BundleContext>& ctx) {
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

        std::optional<CapabilityDecision> businessDecision;
        if (actorDecision.has_value() && authorizationDecision.has_value()) {
            TrsCallFacts facts{};
            facts.routePresent = true;
            facts.registered = true;
            facts.identityVerified = true;
            facts.perCallValidated = PER_CALL_VALIDATED;
            facts.emergencyException = false;
            facts.serviceType = "VRS";

            const bool businessFound = ctx->useService<ITrsBusinessAuthority>()
                .addUseCallback([&businessDecision, &actorDecision, &authorizationDecision, &facts](ITrsBusinessAuthority& authority) {
                    businessDecision = authority.evaluateOrdinaryCallPlacement(
                        actorDecision->actor,
                        *authorizationDecision,
                        facts);
                })
                .build();
            if (!businessFound) {
                businessDecision.reset();
            }
        }
        if (businessDecision.has_value()) {
            emit({std::string{PROFILE}, "TrsBusinessAuthority", businessDecision->verdict, businessDecision->detail});
        } else {
            emit({std::string{PROFILE}, "TrsBusinessAuthority", "CAPABILITY_MISSING", "no TRS business-authority decision was available"});
        }

        emit({
            std::string{PROFILE},
            "FundAuthorityBoundary",
            "NOT_MODELED",
            "ordinary-call placement authority does not establish call connection, compensability, reimbursement eligibility, claim approval, payment authorization, Fund entitlement, or regulatory compliance"
        });
    }
};

} // namespace
} // namespace baudot::celixlab

CELIX_GEN_CXX_BUNDLE_ACTIVATOR(baudot::celixlab::TrsBusinessCompositionProbeBundleActivator)
