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
    "Via: SIP/2.0/UDP 127.0.0.1:5060;branch=z9hG4bK-baudot-celix-payment\r\n"
    "Max-Forwards: 70\r\n"
    "From: <sip:caller@example.invalid>;tag=baudot-celix-payment\r\n"
    "To: <sip:callee@example.invalid>\r\n"
    "Call-ID: baudot-celix-payment@example.invalid\r\n"
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

#if defined(BAUDOT_PAYMENT_READY)
constexpr std::string_view PROFILE = "payment-authorized-disbursement-ready";
constexpr std::string_view PAYMENT_DECISION = "approved";
constexpr std::string_view AUTHORIZED_AMOUNT = "8830.00";
constexpr std::string_view DISBURSEMENT_DEBIT = "2100";
constexpr std::string_view DISBURSEMENT_CREDIT = "1100";
constexpr bool PRIOR_DISBURSEMENT = false;
#elif defined(BAUDOT_PAYMENT_PENDING)
constexpr std::string_view PROFILE = "payment-pending-ledger-posted";
constexpr std::string_view PAYMENT_DECISION = "pending";
constexpr std::string_view AUTHORIZED_AMOUNT = "";
constexpr std::string_view DISBURSEMENT_DEBIT = "2100";
constexpr std::string_view DISBURSEMENT_CREDIT = "1100";
constexpr bool PRIOR_DISBURSEMENT = false;
#elif defined(BAUDOT_PAYMENT_AMOUNT_MISMATCH)
constexpr std::string_view PROFILE = "payment-amount-mismatch";
constexpr std::string_view PAYMENT_DECISION = "approved";
constexpr std::string_view AUTHORIZED_AMOUNT = "8829.99";
constexpr std::string_view DISBURSEMENT_DEBIT = "2100";
constexpr std::string_view DISBURSEMENT_CREDIT = "1100";
constexpr bool PRIOR_DISBURSEMENT = false;
#elif defined(BAUDOT_DISBURSEMENT_MAPPING_MISMATCH)
constexpr std::string_view PROFILE = "disbursement-mapping-mismatch";
constexpr std::string_view PAYMENT_DECISION = "approved";
constexpr std::string_view AUTHORIZED_AMOUNT = "8830.00";
constexpr std::string_view DISBURSEMENT_DEBIT = "1100";
constexpr std::string_view DISBURSEMENT_CREDIT = "2100";
constexpr bool PRIOR_DISBURSEMENT = false;
#elif defined(BAUDOT_DISBURSEMENT_DUPLICATE_REPLAY)
constexpr std::string_view PROFILE = "disbursement-duplicate-replay";
constexpr std::string_view PAYMENT_DECISION = "approved";
constexpr std::string_view AUTHORIZED_AMOUNT = "8830.00";
constexpr std::string_view DISBURSEMENT_DEBIT = "2100";
constexpr std::string_view DISBURSEMENT_CREDIT = "1100";
constexpr bool PRIOR_DISBURSEMENT = true;
#else
#error "Select a Baudot payment-authorization composition profile"
#endif

class PaymentAuthorizationCompositionProbeBundleActivator {
public:
    explicit PaymentAuthorizationCompositionProbeBundleActivator(const std::shared_ptr<celix::BundleContext>& ctx) {
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
            facts.administratorDetermination = "compensable";
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
        rate.calculated = true;
        rate.scenario = "VRS-RATE-VIDEO-TEXT-1000";
        rate.amountUsd = "8830.00";
        rate.verdict = "VRS_RATE_RESULT_AVAILABLE";
        rate.detail = "typed synthetic PR #136 rate result: VRS-RATE-VIDEO-TEXT-1000 amountUsd=8830.00";
        emit({std::string{PROFILE}, "VrsRateResult", rate.verdict, rate.detail});

        std::optional<FundClaimDecision> claimDecision;
        if (compensabilityDecision.has_value()) {
            FundClaimFacts facts{};
            facts.syntheticBusinessTransactionId = "claim-vrs-celix-payment-001";
            facts.claimDecision = "approved";
            facts.approvedClaimAmountUsd = "8830.00";
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

        std::optional<ProviderPayableIntentDecision> payableIntent;
        if (claimDecision.has_value()) {
            ProviderPayableIntentFacts facts{};
            facts.eventType = "providerClaimApproved";
            facts.postingDate = "2026-09-07";
            facts.amountUsd = "8830.00";
            facts.expectedDebitAccount = "5100";
            facts.expectedCreditAccount = "2100";
            facts.priorPostingObservedForBusinessTransactionId = false;
            facts.accountingPeriodOpen = true;
            facts.authorizedOpenPostingDate = false;
            const bool found = ctx->useService<IProviderPayableIntentService>()
                .addUseCallback([&payableIntent, &claimDecision, &facts](IProviderPayableIntentService& service) {
                    payableIntent = service.evaluate(*claimDecision, facts);
                })
                .build();
            if (!found) {
                payableIntent.reset();
            }
        }
        if (payableIntent.has_value()) {
            emit({
                std::string{PROFILE},
                "ProviderPayableIntent",
                payableIntent->verdict,
                payableIntent->detail +
                    "; readyForPosting=" + (payableIntent->readyForPosting ? "true" : "false") +
                    "; debit=" + payableIntent->debitAccount +
                    "; credit=" + payableIntent->creditAccount +
                    "; amountUsd=" + payableIntent->amountUsd
            });
        } else {
            emit({std::string{PROFILE}, "ProviderPayableIntent", "CAPABILITY_MISSING", "no provider-payable accounting-intent decision was available"});
        }

        std::optional<FineractJournalDecision> journalDecision;
        if (payableIntent.has_value()) {
            const bool found = ctx->useService<IFineractJournalAdapter>()
                .addUseCallback([&journalDecision, &payableIntent](IFineractJournalAdapter& adapter) {
                    journalDecision = adapter.post(*payableIntent);
                })
                .build();
            if (!found) {
                journalDecision.reset();
            }
        }
        if (journalDecision.has_value()) {
            emit({
                std::string{PROFILE},
                "FineractJournalAdapter",
                journalDecision->verdict,
                journalDecision->detail +
                    "; posted=" + (journalDecision->posted ? "true" : "false") +
                    "; fineractTransactionId=" + journalDecision->fineractTransactionId
            });
        } else {
            emit({std::string{PROFILE}, "FineractJournalAdapter", "CAPABILITY_MISSING", "no Fineract journal-adapter decision was available"});
        }

        std::optional<PaymentAuthorizationDecision> paymentDecision;
        if (payableIntent.has_value() && journalDecision.has_value()) {
            PaymentAuthorizationFacts facts{};
            facts.paymentDecision = std::string{PAYMENT_DECISION};
            facts.authorizationId = "payment-auth-celix-001";
            facts.authorizedAmountUsd = std::string{AUTHORIZED_AMOUNT};
            const bool found = ctx->useService<IPaymentAuthorizationService>()
                .addUseCallback([&paymentDecision, &payableIntent, &journalDecision, &facts](IPaymentAuthorizationService& service) {
                    paymentDecision = service.evaluate(*payableIntent, *journalDecision, facts);
                })
                .build();
            if (!found) {
                paymentDecision.reset();
            }
        }
        if (paymentDecision.has_value()) {
            emit({
                std::string{PROFILE},
                "PaymentAuthorization",
                paymentDecision->verdict,
                paymentDecision->detail +
                    "; authorized=" + (paymentDecision->authorized ? "true" : "false") +
                    "; authorizationId=" + paymentDecision->authorizationId +
                    "; authorizedAmountUsd=" + paymentDecision->authorizedAmountUsd
            });
        } else {
            emit({std::string{PROFILE}, "PaymentAuthorization", "CAPABILITY_MISSING", "no payment-authorization decision was available"});
        }

        std::optional<ProviderDisbursementIntentDecision> disbursementIntent;
        if (paymentDecision.has_value()) {
            ProviderDisbursementIntentFacts facts{};
            facts.syntheticBusinessTransactionId = "disburse-vrs-celix-payment-001";
            facts.eventType = "providerDisbursement";
            facts.postingDate = "2026-09-07";
            facts.amountUsd = "8830.00";
            facts.expectedDebitAccount = std::string{DISBURSEMENT_DEBIT};
            facts.expectedCreditAccount = std::string{DISBURSEMENT_CREDIT};
            facts.priorDisbursementObservedForBusinessTransactionId = PRIOR_DISBURSEMENT;
            facts.accountingPeriodOpen = true;
            facts.authorizedOpenPostingDate = false;
            const bool found = ctx->useService<IProviderDisbursementIntentService>()
                .addUseCallback([&disbursementIntent, &paymentDecision, &facts](IProviderDisbursementIntentService& service) {
                    disbursementIntent = service.evaluate(*paymentDecision, facts);
                })
                .build();
            if (!found) {
                disbursementIntent.reset();
            }
        }
        if (disbursementIntent.has_value()) {
            emit({
                std::string{PROFILE},
                "ProviderDisbursementIntent",
                disbursementIntent->verdict,
                disbursementIntent->detail +
                    "; readyForPosting=" + (disbursementIntent->readyForPosting ? "true" : "false") +
                    "; businessTransactionId=" + disbursementIntent->syntheticBusinessTransactionId +
                    "; sourceProviderPayableBusinessTransactionId=" + disbursementIntent->sourceProviderPayableBusinessTransactionId +
                    "; paymentAuthorizationId=" + disbursementIntent->paymentAuthorizationId +
                    "; eventType=" + disbursementIntent->eventType +
                    "; debit=" + disbursementIntent->debitAccount +
                    "; credit=" + disbursementIntent->creditAccount +
                    "; amountUsd=" + disbursementIntent->amountUsd
            });
        } else {
            emit({std::string{PROFILE}, "ProviderDisbursementIntent", "CAPABILITY_MISSING", "no provider-disbursement intent decision was available"});
        }

        emit({
            std::string{PROFILE},
            "FundCashBoundary",
            "NOT_MODELED",
            "providerDisbursement intent is not a Fineract disbursement post, bank instruction, Fund cash movement, settlement, or regulatory-compliance verdict"
        });
    }
};

} // namespace
} // namespace baudot::celixlab

CELIX_GEN_CXX_BUNDLE_ACTIVATOR(baudot::celixlab::PaymentAuthorizationCompositionProbeBundleActivator)
