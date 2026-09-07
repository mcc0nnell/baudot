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
    "Via: SIP/2.0/UDP 127.0.0.1:5060;branch=z9hG4bK-baudot-celix-payable\r\n"
    "Max-Forwards: 70\r\n"
    "From: <sip:caller@example.invalid>;tag=baudot-celix-payable\r\n"
    "To: <sip:callee@example.invalid>\r\n"
    "Call-ID: baudot-celix-payable@example.invalid\r\n"
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

#if defined(BAUDOT_PAYABLE_READY)
constexpr std::string_view PROFILE = "provider-payable-ready";
constexpr std::string_view CLAIM_DECISION = "approved";
constexpr std::string_view APPROVED_AMOUNT = "8830.00";
constexpr std::string_view DEBIT_ACCOUNT = "5100";
constexpr std::string_view CREDIT_ACCOUNT = "2100";
constexpr bool PRIOR_POSTING = false;
constexpr bool ACCOUNTING_PERIOD_OPEN = true;
constexpr bool RAW_LEDGER_ACCEPTED = false;
#elif defined(BAUDOT_PAYABLE_CLAIM_PENDING_LEDGER_ACCEPTED)
constexpr std::string_view PROFILE = "provider-payable-claim-pending-ledger-accepted";
constexpr std::string_view CLAIM_DECISION = "pending";
constexpr std::string_view APPROVED_AMOUNT = "";
constexpr std::string_view DEBIT_ACCOUNT = "5100";
constexpr std::string_view CREDIT_ACCOUNT = "2100";
constexpr bool PRIOR_POSTING = false;
constexpr bool ACCOUNTING_PERIOD_OPEN = true;
constexpr bool RAW_LEDGER_ACCEPTED = true;
#elif defined(BAUDOT_PAYABLE_MAPPING_MISMATCH)
constexpr std::string_view PROFILE = "provider-payable-mapping-mismatch";
constexpr std::string_view CLAIM_DECISION = "approved";
constexpr std::string_view APPROVED_AMOUNT = "8830.00";
constexpr std::string_view DEBIT_ACCOUNT = "2100";
constexpr std::string_view CREDIT_ACCOUNT = "5100";
constexpr bool PRIOR_POSTING = false;
constexpr bool ACCOUNTING_PERIOD_OPEN = true;
constexpr bool RAW_LEDGER_ACCEPTED = false;
#elif defined(BAUDOT_PAYABLE_DUPLICATE_REPLAY)
constexpr std::string_view PROFILE = "provider-payable-duplicate-replay";
constexpr std::string_view CLAIM_DECISION = "approved";
constexpr std::string_view APPROVED_AMOUNT = "8830.00";
constexpr std::string_view DEBIT_ACCOUNT = "5100";
constexpr std::string_view CREDIT_ACCOUNT = "2100";
constexpr bool PRIOR_POSTING = true;
constexpr bool ACCOUNTING_PERIOD_OPEN = true;
constexpr bool RAW_LEDGER_ACCEPTED = false;
#elif defined(BAUDOT_PAYABLE_CLOSED_PERIOD)
constexpr std::string_view PROFILE = "provider-payable-closed-period";
constexpr std::string_view CLAIM_DECISION = "approved";
constexpr std::string_view APPROVED_AMOUNT = "8830.00";
constexpr std::string_view DEBIT_ACCOUNT = "5100";
constexpr std::string_view CREDIT_ACCOUNT = "2100";
constexpr bool PRIOR_POSTING = false;
constexpr bool ACCOUNTING_PERIOD_OPEN = false;
constexpr bool RAW_LEDGER_ACCEPTED = false;
#else
#error "Select a Baudot provider-payable composition profile"
#endif

class ProviderPayableCompositionProbeBundleActivator {
public:
    explicit ProviderPayableCompositionProbeBundleActivator(const std::shared_ptr<celix::BundleContext>& ctx) {
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
            facts.syntheticBusinessTransactionId = "claim-vrs-celix-payable-001";
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

        if (RAW_LEDGER_ACCEPTED) {
            emit({
                std::string{PROFILE},
                "RawFineractLedgerObservation",
                "FINERACT_LEDGER_ACCEPTED_FIXTURE",
                "hostile synthetic downstream ledger-success observation injected before accounting-intent evaluation; it carries no claim or payment authority"
            });
        }

        std::optional<ProviderPayableIntentDecision> payableIntent;
        if (claimDecision.has_value()) {
            ProviderPayableIntentFacts facts{};
            facts.eventType = "providerClaimApproved";
            facts.postingDate = "2026-09-07";
            facts.amountUsd = "8830.00";
            facts.expectedDebitAccount = std::string{DEBIT_ACCOUNT};
            facts.expectedCreditAccount = std::string{CREDIT_ACCOUNT};
            facts.priorPostingObservedForBusinessTransactionId = PRIOR_POSTING;
            facts.accountingPeriodOpen = ACCOUNTING_PERIOD_OPEN;
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
                    "; eventType=" + payableIntent->eventType +
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

        emit({
            std::string{PROFILE},
            "PaymentAuthorizationBoundary",
            "NOT_MODELED",
            "provider-payable intent and Fineract ledger acceptance do not authorize provider disbursement"
        });
        emit({
            std::string{PROFILE},
            "FundCashBoundary",
            "NOT_MODELED",
            "no providerDisbursement Dr 2100 / Cr 1100 intent, cash movement, settlement, or regulatory-compliance verdict is modeled by this slice"
        });
    }
};

} // namespace
} // namespace baudot::celixlab

CELIX_GEN_CXX_BUNDLE_ACTIVATOR(baudot::celixlab::ProviderPayableCompositionProbeBundleActivator)
