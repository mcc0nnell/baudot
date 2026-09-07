#include "BaudotCapabilities.h"

#include <celix/BundleActivator.h>

#include <memory>
#include <string>
#include <string_view>

namespace baudot::celixlab {
namespace {

constexpr std::string_view DISBURSEMENT_SEMANTIC_SOURCE =
    "Fineract journal contract providerDisbursement Dr 2100 Provider Payable / Cr 1100 TRS Fund Cash";

class ProviderDisbursementIntentService final : public IProviderDisbursementIntentService {
public:
    ProviderDisbursementIntentDecision evaluate(
        const PaymentAuthorizationDecision& authorization,
        const ProviderDisbursementIntentFacts& facts) override {
        if (!authorization.authorized || authorization.verdict != "PAYMENT_AUTHORIZED") {
            return {
                false,
                authorization.syntheticBusinessTransactionId,
                facts.eventType,
                {},
                {},
                {},
                "PROVIDER_DISBURSEMENT_INTENT_NOT_EVALUATED_PAYMENT_AUTHORIZATION_REQUIRED",
                "canonical providerDisbursement intent requires explicit upstream payment authorization; provider payable or Fineract ledger success alone cannot create disbursement authority"
            };
        }

        if (facts.eventType != "providerDisbursement") {
            return {
                false,
                authorization.syntheticBusinessTransactionId,
                facts.eventType,
                {},
                {},
                {},
                "PROVIDER_DISBURSEMENT_INTENT_REJECTED_EVENT_TYPE",
                "only the canonical providerDisbursement event is admitted by this disbursement-intent service"
            };
        }

        if (facts.amountUsd != authorization.authorizedAmountUsd) {
            return {
                false,
                authorization.syntheticBusinessTransactionId,
                facts.eventType,
                {},
                {},
                {},
                "PROVIDER_DISBURSEMENT_INTENT_REJECTED_AMOUNT_MISMATCH",
                "providerDisbursement amount must equal the explicitly authorized payment amount exactly"
            };
        }

        if (facts.expectedDebitAccount != "2100" || facts.expectedCreditAccount != "1100") {
            return {
                false,
                authorization.syntheticBusinessTransactionId,
                facts.eventType,
                facts.amountUsd,
                facts.expectedDebitAccount,
                facts.expectedCreditAccount,
                "PROVIDER_DISBURSEMENT_INTENT_REJECTED_JOURNAL_MAPPING",
                "canonical providerDisbursement mapping is Dr 2100 Provider Payable / Cr 1100 TRS Fund Cash"
            };
        }

        if (facts.priorDisbursementObservedForBusinessTransactionId) {
            return {
                false,
                authorization.syntheticBusinessTransactionId,
                facts.eventType,
                facts.amountUsd,
                facts.expectedDebitAccount,
                facts.expectedCreditAccount,
                "PROVIDER_DISBURSEMENT_INTENT_REJECTED_IDEMPOTENT_REPLAY",
                "a previously observed provider disbursement for the same synthetic business transaction id blocks a second financial effect"
            };
        }

        if (!facts.accountingPeriodOpen && !facts.authorizedOpenPostingDate) {
            return {
                false,
                authorization.syntheticBusinessTransactionId,
                facts.eventType,
                facts.amountUsd,
                facts.expectedDebitAccount,
                facts.expectedCreditAccount,
                "PROVIDER_DISBURSEMENT_INTENT_REJECTED_ACCOUNTING_CLOSURE",
                "providerDisbursement intent cannot target a closed accounting period without a separately authorized open posting date"
            };
        }

        return {
            true,
            authorization.syntheticBusinessTransactionId,
            facts.eventType,
            facts.amountUsd,
            facts.expectedDebitAccount,
            facts.expectedCreditAccount,
            "PROVIDER_DISBURSEMENT_INTENT_READY",
            "canonical synthetic providerDisbursement intent is ready for a future execution adapter; no journal post, bank instruction, Fund cash movement, settlement, or regulatory-compliance verdict is created by this service"
        };
    }
};

class ProviderDisbursementIntentBundleActivator {
public:
    explicit ProviderDisbursementIntentBundleActivator(const std::shared_ptr<celix::BundleContext>& ctx) {
        registration = ctx->registerService<IProviderDisbursementIntentService>(
                std::make_shared<ProviderDisbursementIntentService>())
            .addProperty("baudot.capability", IProviderDisbursementIntentService::NAME)
            .addProperty("baudot.capability.version", IProviderDisbursementIntentService::VERSION)
            .addProperty("baudot.semantic-source", std::string{DISBURSEMENT_SEMANTIC_SOURCE})
            .addProperty("baudot.control", "cash-movement-not-modeled")
            .setRegisterAsync(false)
            .build();
    }

private:
    std::shared_ptr<celix::ServiceRegistration> registration{};
};

} // namespace
} // namespace baudot::celixlab

CELIX_GEN_CXX_BUNDLE_ACTIVATOR(baudot::celixlab::ProviderDisbursementIntentBundleActivator)
