#include "BaudotCapabilities.h"

#include <celix/BundleActivator.h>

#include <memory>
#include <string>

namespace baudot::celixlab {
namespace {

class FineractJournalAdapter final : public IFineractJournalAdapter {
public:
    FineractJournalDecision post(const ProviderPayableIntentDecision& intent) override {
        if (!intent.readyForPosting || intent.verdict != "PROVIDER_PAYABLE_INTENT_READY") {
            return {
                false,
                intent.syntheticBusinessTransactionId,
                {},
                "FINERACT_POST_NOT_ATTEMPTED_INTENT_REQUIRED",
                "synthetic Fineract execution requires a ready Baudot accounting intent; ledger execution cannot create claim approval or accounting authority"
            };
        }

        if (intent.eventType != "providerClaimApproved" ||
            intent.debitAccount != "5100" ||
            intent.creditAccount != "2100" ||
            intent.amountUsd.empty()) {
            return {
                false,
                intent.syntheticBusinessTransactionId,
                {},
                "FINERACT_POST_REJECTED_NONCANONICAL_INTENT",
                "synthetic Fineract adapter accepts only the canonical providerClaimApproved Dr 5100 / Cr 2100 intent"
            };
        }

        return {
            true,
            intent.syntheticBusinessTransactionId,
            "fineract-fixture-journal-001",
            "FINERACT_JOURNAL_ACCEPTED_FIXTURE",
            "synthetic Fineract adapter accepted the canonical provider-payable journal intent; ledger success does not imply program eligibility, claim approval, payment authorization, Fund cash movement, settlement, or regulatory compliance"
        };
    }
};

class FineractJournalAdapterBundleActivator {
public:
    explicit FineractJournalAdapterBundleActivator(const std::shared_ptr<celix::BundleContext>& ctx) {
        registration = ctx->registerService<IFineractJournalAdapter>(
                std::make_shared<FineractJournalAdapter>())
            .addProperty("baudot.capability", IFineractJournalAdapter::NAME)
            .addProperty("baudot.capability.version", IFineractJournalAdapter::VERSION)
            .addProperty("baudot.authority", "synthetic-accounting-adapter-only")
            .addProperty("baudot.control", "fineract-ledger-success-does-not-imply-program-authority")
            .setRegisterAsync(false)
            .build();
    }

private:
    std::shared_ptr<celix::ServiceRegistration> registration{};
};

} // namespace
} // namespace baudot::celixlab

CELIX_GEN_CXX_BUNDLE_ACTIVATOR(baudot::celixlab::FineractJournalAdapterBundleActivator)
