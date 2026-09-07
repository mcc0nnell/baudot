#include "BaudotCapabilities.h"

#include <celix/BundleActivator.h>

#include <memory>
#include <string>
#include <string_view>

namespace baudot::celixlab {
namespace {

constexpr std::string_view COMPENSABILITY_SEMANTIC_SOURCE =
    "Part 64 VRS compensability and Fund claim gate contract PR-131";

class VrsCompensabilityService final : public ICompensabilityService {
public:
    CompensabilityDecision evaluateVrs(
        const CapabilityDecision& trsBusinessAuthority,
        const VrsCompensabilityFacts& facts) override {
        if (!trsBusinessAuthority.accepted) {
            return {
                false,
                false,
                "VRS_COMPENSABILITY_NOT_EVALUATED_BUSINESS_AUTHORITY_REQUIRED",
                "PR #131 compensability was not evaluated because the upstream TRS ordinary-call business-authority gate was not satisfied"
            };
        }

        if (!facts.completedInternetBasedTrsCall) {
            return {
                false,
                false,
                "VRS_COMPENSABILITY_INELIGIBLE_CALL_NOT_COMPLETED",
                "PR #131 requires completed-call evidence before a VRS compensation candidate can be evaluated; call placement authority is not call completion"
            };
        }

        if (!facts.providerCommissionCertified) {
            return {
                false,
                false,
                "VRS_COMPENSABILITY_INELIGIBLE_PROVIDER_CERTIFICATION_REQUIRED",
                "PR #131 provider certification prerequisite was absent; no compensability or payable-claim inference"
            };
        }

        if (!facts.upstreamUserValidated) {
            return {
                false,
                false,
                "VRS_COMPENSABILITY_INELIGIBLE_USER_VALIDATION_REQUIRED",
                "PR #131 upstream user-validation prerequisite was absent"
            };
        }

        if (!facts.callRecordComplete) {
            return {
                false,
                false,
                "VRS_COMPENSABILITY_INELIGIBLE_CALL_RECORD_INCOMPLETE",
                "PR #131 complete call-record evidence was absent"
            };
        }

        if (facts.prohibitedIncentiveKnown) {
            return {
                false,
                false,
                "VRS_COMPENSABILITY_DENIED_PROHIBITED_INCENTIVE",
                "PR #131 prohibited VRS registration/use incentive blocks compensation eligibility"
            };
        }

        if (facts.unauthorizedOrUnnecessaryUseKnown) {
            return {
                false,
                false,
                "VRS_COMPENSABILITY_DENIED_UNAUTHORIZED_OR_UNNECESSARY_USE",
                "PR #131 known unauthorized, induced, or unnecessary use forbids seeking payment"
            };
        }

        if (facts.providerInvolvedRemoteTraining) {
            return {
                false,
                false,
                "VRS_COMPENSABILITY_DENIED_PROVIDER_INVOLVED_REMOTE_TRAINING",
                "PR #131 provider-involved remote training is outside compensable VRS call treatment"
            };
        }

        if (facts.internationalIpOrigin) {
            return {
                false,
                false,
                "VRS_COMPENSABILITY_INTERNATIONAL_PROFILE_NOT_MODELED",
                "PR #131 international-origin travel-exception evidence is intentionally outside this first Celix compensability profile"
            };
        }

        if (!facts.executiveCertificationPresent) {
            return {
                false,
                false,
                "VRS_COMPENSABILITY_INELIGIBLE_EXECUTIVE_CERTIFICATION_REQUIRED",
                "PR #131 synthetic compensation-request certification prerequisite was absent"
            };
        }

        if (facts.auditPaymentSuspended) {
            return {
                false,
                false,
                "VRS_COMPENSABILITY_PAYMENT_SUSPENDED_AUDIT",
                "PR #131 audit/documentation suspension state prevents a terminal compensable result in this profile"
            };
        }

        if (facts.withholdingState != "none") {
            return {
                true,
                false,
                "VRS_COMPENSABILITY_WITHHELD_PENDING_EXTERNAL_DETERMINATION",
                "PR #131 withholding remains distinct from final compensability and payment release"
            };
        }

        if (facts.administratorDetermination == "compensable") {
            return {
                true,
                true,
                "VRS_COMPENSABILITY_EXTERNALLY_ESTABLISHED",
                "explicit synthetic external administrator/Commission determination from the PR #131 contract establishes compensability for this fixture only; no payable claim, rate, journal, settlement, or regulatory-compliance inference"
            };
        }

        if (facts.administratorDetermination == "pending") {
            return {
                true,
                false,
                "VRS_COMPENSABILITY_PENDING_EXTERNAL_DETERMINATION",
                "all modeled PR #131 candidate prerequisites are present, but no final external compensability determination exists; eligible to seek compensation is not established compensability"
            };
        }

        return {
            true,
            false,
            "VRS_COMPENSABILITY_EXTERNAL_DETERMINATION_REQUIRED",
            "PR #131 candidate prerequisites do not manufacture a final compensability determination; explicit external determination remains required"
        };
    }
};

class VrsCompensabilityBundleActivator {
public:
    explicit VrsCompensabilityBundleActivator(const std::shared_ptr<celix::BundleContext>& ctx) {
        registration = ctx->registerService<ICompensabilityService>(
                std::make_shared<VrsCompensabilityService>())
            .addProperty("baudot.capability", ICompensabilityService::NAME)
            .addProperty("baudot.capability.version", ICompensabilityService::VERSION)
            .addProperty("baudot.semantic-source", std::string{COMPENSABILITY_SEMANTIC_SOURCE})
            .addProperty("baudot.control", "part64-contract-derived-fixture")
            .setRegisterAsync(false)
            .build();
    }

private:
    std::shared_ptr<celix::ServiceRegistration> registration{};
};

} // namespace
} // namespace baudot::celixlab

CELIX_GEN_CXX_BUNDLE_ACTIVATOR(baudot::celixlab::VrsCompensabilityBundleActivator)
