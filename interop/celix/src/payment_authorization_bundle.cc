#include "BaudotCapabilities.h"

#include <celix/BundleActivator.h>

#include <memory>
#include <string>
#include <string_view>

namespace baudot::celixlab {
namespace {

constexpr std::string_view PAYMENT_SEMANTIC_SOURCE =
    "Fineract journal contract providerDisbursement authority baudot-synthetic-payment-authorization";

class PaymentAuthorizationService final : public IPaymentAuthorizationService {
public:
    PaymentAuthorizationDecision evaluate(
        const ProviderPayableIntentDecision& payableIntent,
        const FineractJournalDecision& journal,
        const PaymentAuthorizationFacts& facts) override {
        if (!payableIntent.readyForPosting || payableIntent.verdict != "PROVIDER_PAYABLE_INTENT_READY") {
            return {
                false,
                payableIntent.syntheticBusinessTransactionId,
                facts.authorizationId,
                {},
                "PAYMENT_AUTHORIZATION_NOT_EVALUATED_PAYABLE_INTENT_REQUIRED",
                "payment authorization requires a canonical upstream provider-payable accounting intent; downstream payment facts cannot manufacture claim or accounting authority"
            };
        }

        if (!journal.posted) {
            return {
                false,
                payableIntent.syntheticBusinessTransactionId,
                facts.authorizationId,
                {},
                "PAYMENT_AUTHORIZATION_NOT_EVALUATED_POSTED_PAYABLE_REQUIRED",
                "payment authorization requires the canonical provider-payable journal to be posted before a provider disbursement may be considered; adapter-specific verdict text is not itself authority"
            };
        }

        if (journal.syntheticBusinessTransactionId != payableIntent.syntheticBusinessTransactionId) {
            return {
                false,
                payableIntent.syntheticBusinessTransactionId,
                facts.authorizationId,
                {},
                "PAYMENT_AUTHORIZATION_REJECTED_TRANSACTION_LINEAGE_MISMATCH",
                "posted journal business-transaction lineage must match the provider-payable accounting intent exactly"
            };
        }

        if (journal.fineractTransactionId.empty()) {
            return {
                false,
                payableIntent.syntheticBusinessTransactionId,
                facts.authorizationId,
                {},
                "PAYMENT_AUTHORIZATION_REJECTED_LEDGER_TRANSACTION_ID_REQUIRED",
                "posted provider-payable evidence must carry a ledger transaction id before payment authority can be evaluated"
            };
        }

        if (facts.paymentDecision == "pending") {
            return {
                false,
                payableIntent.syntheticBusinessTransactionId,
                facts.authorizationId,
                {},
                "PAYMENT_AUTHORIZATION_PENDING",
                "provider payable is posted, but the explicit synthetic payment-authority decision remains pending"
            };
        }

        if (facts.paymentDecision == "denied") {
            return {
                false,
                payableIntent.syntheticBusinessTransactionId,
                facts.authorizationId,
                {},
                "PAYMENT_AUTHORIZATION_DENIED",
                "the explicit synthetic payment-authority decision denied disbursement; provider payable and ledger success do not move Fund cash"
            };
        }

        if (facts.paymentDecision != "approved") {
            return {
                false,
                payableIntent.syntheticBusinessTransactionId,
                facts.authorizationId,
                {},
                "PAYMENT_AUTHORIZATION_DECISION_REQUIRED",
                "an explicit synthetic payment-authority decision is required; posted provider payable does not imply payment authorization"
            };
        }

        if (facts.authorizationId.empty()) {
            return {
                false,
                payableIntent.syntheticBusinessTransactionId,
                {},
                {},
                "PAYMENT_AUTHORIZATION_REJECTED_AUTHORIZATION_ID_REQUIRED",
                "approved synthetic payment authority must carry a stable authorization id for evidence lineage"
            };
        }

        if (facts.authorizedAmountUsd != payableIntent.amountUsd) {
            return {
                false,
                payableIntent.syntheticBusinessTransactionId,
                facts.authorizationId,
                {},
                "PAYMENT_AUTHORIZATION_REJECTED_AMOUNT_MISMATCH",
                "authorized payment amount must equal the posted provider-payable amount exactly; payment authority cannot rewrite accounting value"
            };
        }

        return {
            true,
            payableIntent.syntheticBusinessTransactionId,
            facts.authorizationId,
            facts.authorizedAmountUsd,
            "PAYMENT_AUTHORIZED",
            "explicit synthetic payment authority accepted against a canonical posted provider payable; this authorizes only construction of a providerDisbursement intent and does not post Dr 2100 / Cr 1100, move Fund cash, settle, or establish regulatory compliance"
        };
    }
};

class PaymentAuthorizationBundleActivator {
public:
    explicit PaymentAuthorizationBundleActivator(const std::shared_ptr<celix::BundleContext>& ctx) {
        registration = ctx->registerService<IPaymentAuthorizationService>(
                std::make_shared<PaymentAuthorizationService>())
            .addProperty("baudot.capability", IPaymentAuthorizationService::NAME)
            .addProperty("baudot.capability.version", IPaymentAuthorizationService::VERSION)
            .addProperty("baudot.semantic-source", std::string{PAYMENT_SEMANTIC_SOURCE})
            .addProperty("baudot.control", "payment-authority-separate-from-ledger-execution")
            .setRegisterAsync(false)
            .build();
    }

private:
    std::shared_ptr<celix::ServiceRegistration> registration{};
};

} // namespace
} // namespace baudot::celixlab

CELIX_GEN_CXX_BUNDLE_ACTIVATOR(baudot::celixlab::PaymentAuthorizationBundleActivator)
