#include "BaudotCapabilities.h"

#include <celix/BundleActivator.h>

#include <memory>
#include <string>
#include <string_view>

namespace baudot::celixlab {
namespace {

constexpr std::string_view FUND_CLAIM_SEMANTIC_SOURCE =
    "Part 64 VRS rate contract PR-136 plus synthetic Fund claim handoff PR-137";

class FundClaimAuthority final : public IFundClaimAuthority {
public:
    FundClaimDecision evaluateVrsClaim(
        const CompensabilityDecision& compensability,
        const RateDecision& rate,
        const FundClaimFacts& facts) override {
        if (!compensability.establishedCompensable) {
            return {
                false,
                facts.syntheticBusinessTransactionId,
                {},
                "FUND_CLAIM_NOT_EVALUATED_COMPENSABILITY_REQUIRED",
                "PR #137 requires terminal externally established compensability before synthetic claim authority can be evaluated"
            };
        }

        if (!rate.calculated || rate.amountUsd.empty()) {
            return {
                false,
                facts.syntheticBusinessTransactionId,
                {},
                "FUND_CLAIM_NOT_EVALUATED_RATE_REQUIRED",
                "PR #137 requires a separate completed PR #136 rate result; claim authority cannot calculate or infer the compensation rate"
            };
        }

        if (facts.claimDecision == "pending") {
            return {
                false,
                facts.syntheticBusinessTransactionId,
                {},
                "FUND_CLAIM_PENDING_DECISION",
                "terminal compensability and a rate result exist, but the synthetic claim decision remains pending"
            };
        }

        if (facts.claimDecision == "denied") {
            return {
                false,
                facts.syntheticBusinessTransactionId,
                {},
                "FUND_CLAIM_DENIED",
                "the explicit synthetic Fund claim decision is denied; no provider-payable or accounting authority is inferred"
            };
        }

        if (facts.claimDecision != "approved") {
            return {
                false,
                facts.syntheticBusinessTransactionId,
                {},
                "FUND_CLAIM_DECISION_REQUIRED",
                "an explicit synthetic Fund claim decision is required; compensability and rate calculation do not manufacture claim approval"
            };
        }

        if (facts.approvedClaimAmountUsd != rate.amountUsd) {
            return {
                false,
                facts.syntheticBusinessTransactionId,
                {},
                "FUND_CLAIM_REJECTED_AMOUNT_MISMATCH",
                "PR #137 exact-amount integrity failed: approved claim amount does not match the upstream rate result"
            };
        }

        return {
            true,
            facts.syntheticBusinessTransactionId,
            facts.approvedClaimAmountUsd,
            "FUND_CLAIM_APPROVED",
            "explicit synthetic PR #137 claim approval accepted against terminal compensability and the exact typed PR #136 rate result; provider payable, Fineract posting, payment authorization, cash movement, and settlement remain downstream authorities"
        };
    }
};

class FundClaimAuthorityBundleActivator {
public:
    explicit FundClaimAuthorityBundleActivator(const std::shared_ptr<celix::BundleContext>& ctx) {
        registration = ctx->registerService<IFundClaimAuthority>(
                std::make_shared<FundClaimAuthority>())
            .addProperty("baudot.capability", IFundClaimAuthority::NAME)
            .addProperty("baudot.capability.version", IFundClaimAuthority::VERSION)
            .addProperty("baudot.semantic-source", std::string{FUND_CLAIM_SEMANTIC_SOURCE})
            .addProperty("baudot.control", "part64-fund-contract-derived-fixture")
            .setRegisterAsync(false)
            .build();
    }

private:
    std::shared_ptr<celix::ServiceRegistration> registration{};
};

} // namespace
} // namespace baudot::celixlab

CELIX_GEN_CXX_BUNDLE_ACTIVATOR(baudot::celixlab::FundClaimAuthorityBundleActivator)
