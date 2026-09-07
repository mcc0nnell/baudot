#include "BaudotCapabilities.h"

#include <celix/BundleActivator.h>

#include <memory>
#include <string>
#include <string_view>

namespace baudot::celixlab {
namespace {

constexpr std::string_view ACCOUNTING_SEMANTIC_SOURCE =
    "Fineract journal contract interop/fineract/journal-contract-v1.json plus synthetic Fund handoff PR-137";

class ProviderPayableIntentService final : public IProviderPayableIntentService {
public:
    ProviderPayableIntentDecision evaluate(
        const FundClaimDecision& claim,
        const ProviderPayableIntentFacts& facts) override {
        if (!claim.approved || claim.verdict != "FUND_CLAIM_APPROVED") {
            return {
                false,
                claim.syntheticBusinessTransactionId,
                facts.eventType,
                {},
                {},
                {},
                "PROVIDER_PAYABLE_INTENT_NOT_EVALUATED_CLAIM_APPROVAL_REQUIRED",
                "canonical providerClaimApproved accounting intent requires an approved upstream Fund claim; ledger observations cannot manufacture claim approval"
            };
        }

        if (facts.eventType != "providerClaimApproved") {
            return {
                false,
                claim.syntheticBusinessTransactionId,
                facts.eventType,
                {},
                {},
                {},
                "PROVIDER_PAYABLE_INTENT_REJECTED_EVENT_TYPE",
                "only the canonical providerClaimApproved event is admitted by this accounting-intent service"
            };
        }

        if (facts.amountUsd != claim.approvedAmountUsd) {
            return {
                false,
                claim.syntheticBusinessTransactionId,
                facts.eventType,
                {},
                {},
                {},
                "PROVIDER_PAYABLE_INTENT_REJECTED_AMOUNT_MISMATCH",
                "accounting intent amount must equal the approved Fund claim amount exactly"
            };
        }

        if (facts.expectedDebitAccount != "5100" || facts.expectedCreditAccount != "2100") {
            return {
                false,
                claim.syntheticBusinessTransactionId,
                facts.eventType,
                facts.amountUsd,
                facts.expectedDebitAccount,
                facts.expectedCreditAccount,
                "PROVIDER_PAYABLE_INTENT_REJECTED_JOURNAL_MAPPING",
                "canonical providerClaimApproved mapping is Dr 5100 TRS Provider Compensation Expense / Cr 2100 Provider Payable"
            };
        }

        if (facts.priorPostingObservedForBusinessTransactionId) {
            return {
                false,
                claim.syntheticBusinessTransactionId,
                facts.eventType,
                facts.amountUsd,
                facts.expectedDebitAccount,
                facts.expectedCreditAccount,
                "PROVIDER_PAYABLE_INTENT_REJECTED_IDEMPOTENT_REPLAY",
                "the synthetic business transaction id is the Baudot adapter idempotency key; replay cannot create an additional financial effect"
            };
        }

        if (!facts.accountingPeriodOpen && !facts.authorizedOpenPostingDate) {
            return {
                false,
                claim.syntheticBusinessTransactionId,
                facts.eventType,
                facts.amountUsd,
                facts.expectedDebitAccount,
                facts.expectedCreditAccount,
                "PROVIDER_PAYABLE_INTENT_REJECTED_ACCOUNTING_CLOSURE",
                "posting after an accounting closure must fail unless a separately authorized open posting date is supplied"
            };
        }

        return {
            true,
            claim.syntheticBusinessTransactionId,
            facts.eventType,
            facts.amountUsd,
            facts.expectedDebitAccount,
            facts.expectedCreditAccount,
            "PROVIDER_PAYABLE_INTENT_READY",
            "canonical synthetic providerClaimApproved accounting intent is ready for a Fineract adapter; this does not establish ledger posting, payment authorization, Fund cash movement, settlement, or regulatory compliance"
        };
    }
};

class ProviderPayableIntentBundleActivator {
public:
    explicit ProviderPayableIntentBundleActivator(const std::shared_ptr<celix::BundleContext>& ctx) {
        registration = ctx->registerService<IProviderPayableIntentService>(
                std::make_shared<ProviderPayableIntentService>())
            .addProperty("baudot.capability", IProviderPayableIntentService::NAME)
            .addProperty("baudot.capability.version", IProviderPayableIntentService::VERSION)
            .addProperty("baudot.semantic-source", std::string{ACCOUNTING_SEMANTIC_SOURCE})
            .addProperty("baudot.control", "canonical-fineract-journal-contract")
            .setRegisterAsync(false)
            .build();
    }

private:
    std::shared_ptr<celix::ServiceRegistration> registration{};
};

} // namespace
} // namespace baudot::celixlab

CELIX_GEN_CXX_BUNDLE_ACTIVATOR(baudot::celixlab::ProviderPayableIntentBundleActivator)
