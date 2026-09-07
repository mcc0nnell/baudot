#pragma once

#include <string>
#include <string_view>
#include <vector>

namespace baudot::celixlab {

struct CapabilityDecision {
    bool accepted{false};
    std::string verdict{};
    std::string detail{};
};

struct EvidenceObservation {
    std::string profile{};
    std::string capability{};
    std::string verdict{};
    std::string detail{};
};

struct ActorContext {
    bool authenticated{false};
    bool remembered{false};
    std::string actorId{};
    std::string actorType{};
    std::string tenantId{};
    std::string providerId{};
    std::vector<std::string> roles{};
    std::string sessionId{};
    std::string authenticatedAt{};
    std::string authenticationStrength{};
};

struct ActorContextDecision {
    ActorContext actor{};
    std::string verdict{};
    std::string detail{};
};

struct TrsCallFacts {
    bool routePresent{false};
    bool registered{false};
    bool identityVerified{false};
    bool perCallValidated{false};
    bool emergencyException{false};
    std::string serviceType{};
};

struct VrsCompensabilityFacts {
    bool completedInternetBasedTrsCall{false};
    bool providerCommissionCertified{false};
    bool upstreamUserValidated{false};
    bool callRecordComplete{false};
    bool prohibitedIncentiveKnown{false};
    bool unauthorizedOrUnnecessaryUseKnown{false};
    bool providerInvolvedRemoteTraining{false};
    bool internationalIpOrigin{false};
    bool executiveCertificationPresent{false};
    bool auditPaymentSuspended{false};
    std::string withholdingState{};
    std::string administratorDetermination{};
};

struct CompensabilityDecision {
    bool eligibleToSeekCompensation{false};
    bool establishedCompensable{false};
    std::string verdict{};
    std::string detail{};
};

struct RateDecision {
    bool calculated{false};
    std::string scenario{};
    std::string amountUsd{};
    std::string verdict{};
    std::string detail{};
};

struct FundClaimFacts {
    std::string syntheticBusinessTransactionId{};
    std::string claimDecision{};
    std::string approvedClaimAmountUsd{};
};

struct FundClaimDecision {
    bool approved{false};
    std::string syntheticBusinessTransactionId{};
    std::string approvedAmountUsd{};
    std::string verdict{};
    std::string detail{};
};

struct ProviderPayableIntentFacts {
    std::string eventType{};
    std::string postingDate{};
    std::string amountUsd{};
    std::string expectedDebitAccount{};
    std::string expectedCreditAccount{};
    bool priorPostingObservedForBusinessTransactionId{false};
    bool accountingPeriodOpen{true};
    bool authorizedOpenPostingDate{false};
};

struct ProviderPayableIntentDecision {
    bool readyForPosting{false};
    std::string syntheticBusinessTransactionId{};
    std::string eventType{};
    std::string amountUsd{};
    std::string debitAccount{};
    std::string creditAccount{};
    std::string verdict{};
    std::string detail{};
};

struct FineractJournalDecision {
    bool posted{false};
    std::string syntheticBusinessTransactionId{};
    std::string fineractTransactionId{};
    std::string verdict{};
    std::string detail{};
};

class ISignalingParser {
public:
    static constexpr const char* NAME = "baudot.signaling_parser";
    static constexpr const char* VERSION = "1.0.0";

    virtual ~ISignalingParser() noexcept = default;
    virtual CapabilityDecision parse(std::string_view signaling) = 0;
};

class ICallAdmission {
public:
    static constexpr const char* NAME = "baudot.call_admission";
    static constexpr const char* VERSION = "2.0.0";

    virtual ~ICallAdmission() noexcept = default;
    virtual CapabilityDecision evaluate(std::string_view signaling) = 0;
};

class IRealtimeTextTransport {
public:
    static constexpr const char* NAME = "baudot.realtime_text_transport";
    static constexpr const char* VERSION = "1.0.0";

    virtual ~IRealtimeTextTransport() noexcept = default;
    virtual CapabilityDecision evaluate(std::string_view payload) = 0;
};

class IActorContextProvider {
public:
    static constexpr const char* NAME = "baudot.actor_context";
    static constexpr const char* VERSION = "1.0.0";

    virtual ~IActorContextProvider() noexcept = default;
    virtual ActorContextDecision current() = 0;
};

class IAuthorizationService {
public:
    static constexpr const char* NAME = "baudot.authorization";
    static constexpr const char* VERSION = "1.0.0";

    virtual ~IAuthorizationService() noexcept = default;
    virtual CapabilityDecision authorize(
        const ActorContext& actor,
        std::string_view resourceType,
        std::string_view action,
        std::string_view permission) = 0;
};

class ITrsBusinessAuthority {
public:
    static constexpr const char* NAME = "baudot.trs_business_authority";
    static constexpr const char* VERSION = "1.0.0";

    virtual ~ITrsBusinessAuthority() noexcept = default;
    virtual CapabilityDecision evaluateOrdinaryCallPlacement(
        const ActorContext& actor,
        const CapabilityDecision& authorization,
        const TrsCallFacts& facts) = 0;
};

class ICompensabilityService {
public:
    static constexpr const char* NAME = "baudot.compensability";
    static constexpr const char* VERSION = "1.0.0";

    virtual ~ICompensabilityService() noexcept = default;
    virtual CompensabilityDecision evaluateVrs(
        const CapabilityDecision& trsBusinessAuthority,
        const VrsCompensabilityFacts& facts) = 0;
};

class IFundClaimAuthority {
public:
    static constexpr const char* NAME = "baudot.fund_claim_authority";
    static constexpr const char* VERSION = "1.0.0";

    virtual ~IFundClaimAuthority() noexcept = default;
    virtual FundClaimDecision evaluateVrsClaim(
        const CompensabilityDecision& compensability,
        const RateDecision& rate,
        const FundClaimFacts& facts) = 0;
};

class IProviderPayableIntentService {
public:
    static constexpr const char* NAME = "baudot.provider_payable_intent";
    static constexpr const char* VERSION = "1.0.0";

    virtual ~IProviderPayableIntentService() noexcept = default;
    virtual ProviderPayableIntentDecision evaluate(
        const FundClaimDecision& claim,
        const ProviderPayableIntentFacts& facts) = 0;
};

class IFineractJournalAdapter {
public:
    static constexpr const char* NAME = "baudot.fineract_journal_adapter";
    static constexpr const char* VERSION = "1.0.0";

    virtual ~IFineractJournalAdapter() noexcept = default;
    virtual FineractJournalDecision post(const ProviderPayableIntentDecision& intent) = 0;
};

class IEvidenceEmitter {
public:
    static constexpr const char* NAME = "baudot.evidence_emitter";
    static constexpr const char* VERSION = "1.0.0";

    virtual ~IEvidenceEmitter() noexcept = default;
    virtual void emit(const EvidenceObservation& observation) = 0;
};

} // namespace baudot::celixlab
