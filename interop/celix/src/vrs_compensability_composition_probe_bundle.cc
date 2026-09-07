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
    "Via: SIP/2.0/UDP 127.0.0.1:5060;branch=z9hG4bK-baudot-celix-comp\r\n"
    "Max-Forwards: 70\r\n"
    "From: <sip:caller@example.invalid>;tag=baudot-celix-comp\r\n"
    "To: <sip:callee@example.invalid>\r\n"
    "Call-ID: baudot-celix-comp@example.invalid\r\n"
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

#if defined(BAUDOT_COMP_EXTERNALLY_ESTABLISHED)
constexpr std::string_view PROFILE = "compensability-externally-established";
constexpr bool CALL_COMPLETED = true;
constexpr std::string_view ADMIN_DETERMINATION = "compensable";
#elif defined(BAUDOT_COMP_PENDING)
constexpr std::string_view PROFILE = "compensability-pending";
constexpr bool CALL_COMPLETED = true;
constexpr std::string_view ADMIN_DETERMINATION = "pending";
#elif defined(BAUDOT_COMP_PLACEMENT_ONLY)
constexpr std::string_view PROFILE = "compensability-placement-only";
constexpr bool CALL_COMPLETED = false;
constexpr std::string_view ADMIN_DETERMINATION = "compensable";
#else
#error "Select a Baudot VRS compensability composition profile"
#endif

class VrsCompensabilityCompositionProbeBundleActivator {
public:
    explicit VrsCompensabilityCompositionProbeBundleActivator(const std::shared_ptr<celix::BundleContext>& ctx) {
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
            TrsCallFacts callFacts{};
            callFacts.routePresent = true;
            callFacts.registered = true;
            callFacts.identityVerified = true;
            callFacts.perCallValidated = true;
            callFacts.emergencyException = false;
            callFacts.serviceType = "VRS";

            const bool businessFound = ctx->useService<ITrsBusinessAuthority>()
                .addUseCallback([&businessDecision, &actorDecision, &authorizationDecision, &callFacts](ITrsBusinessAuthority& authority) {
                    businessDecision = authority.evaluateOrdinaryCallPlacement(
                        actorDecision->actor,
                        *authorizationDecision,
                        callFacts);
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

        std::optional<CompensabilityDecision> compensabilityDecision;
        if (businessDecision.has_value()) {
            VrsCompensabilityFacts facts{};
            facts.completedInternetBasedTrsCall = CALL_COMPLETED;
            facts.providerCommissionCertified = true;
            facts.upstreamUserValidated = true;
            facts.callRecordComplete = true;
            facts.prohibitedIncentiveKnown = false;
            facts.unauthorizedOrUnnecessaryUseKnown = false;
            facts.providerInvolvedRemoteTraining = false;
            facts.internationalIpOrigin = false;
            facts.executiveCertificationPresent = true;
            facts.auditPaymentSuspended = false;
            facts.withholdingState = "none";
            facts.administratorDetermination = std::string{ADMIN_DETERMINATION};

            const bool compensabilityFound = ctx->useService<ICompensabilityService>()
                .addUseCallback([&compensabilityDecision, &businessDecision, &facts](ICompensabilityService& service) {
                    compensabilityDecision = service.evaluateVrs(*businessDecision, facts);
                })
                .build();
            if (!compensabilityFound) {
                compensabilityDecision.reset();
            }
        }
        if (compensabilityDecision.has_value()) {
            emit({
                std::string{PROFILE},
                "VrsCompensability",
                compensabilityDecision->verdict,
                compensabilityDecision->detail +
                    "; eligibleToSeekCompensation=" + (compensabilityDecision->eligibleToSeekCompensation ? "true" : "false") +
                    "; establishedCompensable=" + (compensabilityDecision->establishedCompensable ? "true" : "false")
            });
        } else {
            emit({std::string{PROFILE}, "VrsCompensability", "CAPABILITY_MISSING", "no compensability decision was available"});
        }

        emit({
            std::string{PROFILE},
            "PayableClaimBoundary",
            "NOT_MODELED",
            "externally established compensability does not create a payable Fund claim, rate result, Fineract journal, payment authorization, settlement, or regulatory-compliance verdict"
        });
    }
};

} // namespace
} // namespace baudot::celixlab

CELIX_GEN_CXX_BUNDLE_ACTIVATOR(baudot::celixlab::VrsCompensabilityCompositionProbeBundleActivator)
