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
    "Via: SIP/2.0/UDP 127.0.0.1:5060;branch=z9hG4bK-baudot-celix-claim\r\n"
    "Max-Forwards: 70\r\n"
    "From: <sip:caller@example.invalid>;tag=baudot-celix-claim\r\n"
    "To: <sip:callee@example.invalid>\r\n"
    "Call-ID: baudot-celix-claim@example.invalid\r\n"
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

#if defined(BAUDOT_CLAIM_APPROVED)
constexpr std::string_view PROFILE = "fund-claim-approved";
constexpr std::string_view ADMIN_DETERMINATION = "compensable";
constexpr bool RATE_CALCULATED = true;
constexpr std::string_view CLAIM_DECISION = "approved";
constexpr std::string_view APPROVED_AMOUNT = "8830.00";
#elif defined(BAUDOT_CLAIM_COMPENSABILITY_PENDING)
constexpr std::string_view PROFILE = "fund-claim-compensability-pending";
constexpr std::string_view ADMIN_DETERMINATION = "pending";
constexpr bool RATE_CALCULATED = true;
constexpr std::string_view CLAIM_DECISION = "approved";
constexpr std::string_view APPROVED_AMOUNT = "8830.00";
#elif defined(BAUDOT_CLAIM_RATE_MISSING)
constexpr std::string_view PROFILE = "fund-claim-rate-missing";
constexpr std::string_view ADMIN_DETERMINATION = "compensable";
constexpr bool RATE_CALCULATED = false;
constexpr std::string_view CLAIM_DECISION = "approved";
constexpr std::string_view APPROVED_AMOUNT = "8830.00";
#elif defined(BAUDOT_CLAIM_PENDING)
constexpr std::string_view PROFILE = "fund-claim-pending";
constexpr std::string_view ADMIN_DETERMINATION = "compensable";
constexpr bool RATE_CALCULATED = true;
constexpr std::string_view CLAIM_DECISION = "pending";
constexpr std::string_view APPROVED_AMOUNT = "";
#elif defined(BAUDOT_CLAIM_AMOUNT_MISMATCH)
constexpr std::string_view PROFILE = "fund-claim-amount-mismatch";
constexpr std::string_view ADMIN_DETERMINATION = "compensable";
constexpr bool RATE_CALCULATED = true;
constexpr std::string_view CLAIM_DECISION = "approved";
constexpr std::string_view APPROVED_AMOUNT = "8829.99";
#else
#error "Select a Baudot Fund claim composition profile"
#endif

class FundClaimCompositionProbeBundleActivator {
public:
    explicit FundClaimCompositionProbeBundleActivator(const std::shared_ptr<celix::BundleContext>& ctx) {
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
        emit(parserFound && parserDecision.has_value()
            ? EvidenceObservation{std::string{PROFILE}, "SignalingParser", parserDecision->verdict, parserDecision->detail}
            : EvidenceObservation{std::string{PROFILE}, "SignalingParser", "CAPABILITY_MISSING", "no signaling parser service was available"});

        std::optional<CapabilityDecision> admissionDecision;
        const bool admissionFound = ctx->useService<ICallAdmission>()
            .addUseCallback([&admissionDecision](ICallAdmission& admission) {
                admissionDecision = admission.evaluate(INVITE_FIXTURE);
            })
            .build();
        emit(admissionFound && admissionDecision.has_value()
            ? EvidenceObservation{std::string{PROFILE}, "CallAdmission", admissionDecision->verdict, admissionDecision->detail}
            : EvidenceObservation{std::string{PROFILE}, "CallAdmission", "CAPABILITY_MISSING", "no call admission service was available"});

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
            const bool found = ctx->useService<IAuthorizationService>()
                .addUseCallback([&authorizationDecision, &actorDecision](IAuthorizationService& authorization) {
                    authorizationDecision = authorization.authorize(
                        actorDecision->actor, "telephone-number", "QUERY", "query");
                })
                .build();
            if (!found) {
                authorizationDecision.reset();
            }
        }
        emit(authorizationDecision.has_value()
            ? EvidenceObservation{std::string{PROFILE}, "Authorization", authorizationDecision->verdict, authorizationDecision->detail}
            : EvidenceObservation{std::string{PROFILE}, "Authorization", "CAPABILITY_MISSING", "no authorization decision was available"});

        std::optional<CapabilityDecision> businessDecision;
        if (actorDecision.has_value() && authorizationDecision.has_value()) {
            TrsCallFacts facts{};
            facts.routePresent = true;
            facts.registered = true;
            facts.identityVerified = true;
            facts.perCallValidated = true;
            facts.emergencyException = false;
            facts.serviceType = "VRS";
            const bool found = ctx->useService<ITrsBusinessAuthority>()
                .addUseCallback([&businessDecision, &actorDecision, &authorizationDecision, &facts](ITrsBusinessAuthority& authority) {
                    businessDecision = authority.evaluateOrdinaryCallPlacement(
                        actorDecision->actor, *authorizationDecision, facts);
                })
                .build();
            if (!found) {
                businessDecision.reset();
            }
        }
        emit(businessDecision.has_value()
            ? EvidenceObservation{std::string{PROFILE}, "TrsBusinessAuthority", businessDecision->verdict, businessDecision->detail}
            : EvidenceObservation{std::string{PROFILE}, "TrsBusinessAuthority", "CAPABILITY_MISSING", "no TRS business-authority decision was available"});

        std::optional<CompensabilityDecision> compensabilityDecision;
        if (businessDecision.has_value()) {
            VrsCompensabilityFacts facts{};
            facts.completedInternetBasedTrsCall = true;
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
            const bool found = ctx->useService<ICompensabilityService>()
                .addUseCallback([&compensabilityDecision, &businessDecision, &facts](ICompensabilityService& service) {
                    compensabilityDecision = service.evaluateVrs(*businessDecision, facts);
                })
                .build();
            if (!found) {
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

        RateDecision rate{};
        rate.calculated = RATE_CALCULATED;
        rate.scenario = "VRS-RATE-VIDEO-TEXT-1000";
        rate.amountUsd = RATE_CALCULATED ? "8830.00" : "";
        rate.verdict = RATE_CALCULATED ? "VRS_RATE_RESULT_AVAILABLE" : "VRS_RATE_RESULT_MISSING";
        rate.detail = RATE_CALCULATED
            ? "typed synthetic PR #136 rate result: VRS-RATE-VIDEO-TEXT-1000 amountUsd=8830.00; rate calculation remains outside Fund claim authority"
            : "no completed PR #136 rate result supplied; claim authority must fail closed";
        emit({std::string{PROFILE}, "VrsRateResult", rate.verdict, rate.detail});

        std::optional<FundClaimDecision> claimDecision;
        if (compensabilityDecision.has_value()) {
            FundClaimFacts facts{};
            facts.syntheticBusinessTransactionId = "claim-vrs-celix-example-001";
            facts.claimDecision = std::string{CLAIM_DECISION};
            facts.approvedClaimAmountUsd = std::string{APPROVED_AMOUNT};
            const bool found = ctx->useService<IFundClaimAuthority>()
                .addUseCallback([&claimDecision, &compensabilityDecision, &rate, &facts](IFundClaimAuthority& authority) {
                    claimDecision = authority.evaluateVrsClaim(*compensabilityDecision, rate, facts);
                })
                .build();
            if (!found) {
                claimDecision.reset();
            }
        }
        if (claimDecision.has_value()) {
            emit({
                std::string{PROFILE},
                "FundClaimAuthority",
                claimDecision->verdict,
                claimDecision->detail +
                    "; approved=" + (claimDecision->approved ? "true" : "false") +
                    "; approvedAmountUsd=" + claimDecision->approvedAmountUsd
            });
        } else {
            emit({std::string{PROFILE}, "FundClaimAuthority", "CAPABILITY_MISSING", "no Fund claim authority decision was available"});
        }

        emit({
            std::string{PROFILE},
            "ProviderPayableBoundary",
            "NOT_MODELED",
            "Fund claim approval does not create provider payable, a Fineract journal, payment authorization, Fund cash movement, settlement, or regulatory-compliance verdict"
        });
    }
};

} // namespace
} // namespace baudot::celixlab

CELIX_GEN_CXX_BUNDLE_ACTIVATOR(baudot::celixlab::FundClaimCompositionProbeBundleActivator)
