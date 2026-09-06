#include "BaudotCapabilities.h"

#include <celix/BundleActivator.h>

extern "C" {
#include <pjlib.h>
#include <pjsip/sip_msg.h>
#include <pjsip/sip_parser.h>
}

#include <memory>
#include <stdexcept>
#include <string>
#include <string_view>

namespace baudot::celixlab {
namespace {

constexpr std::string_view PJSIP_IDENTITY =
    "pjsip/pjproject-2.17@5a457451fa2712ba18e12b01738e8ff3af2b26fd";

class PjsipCallAdmission final : public ICallAdmission {
public:
    PjsipCallAdmission() {
        const pj_status_t status = pj_init();
        if (status != PJ_SUCCESS) {
            throw std::runtime_error("pj_init failed for Celix PJSIP admission adapter");
        }
        initialized_ = true;
        pj_caching_pool_init(&cachingPool_, nullptr, 0);
    }

    ~PjsipCallAdmission() noexcept override {
        if (initialized_) {
            pj_caching_pool_destroy(&cachingPool_);
            pj_shutdown();
        }
    }

    CapabilityDecision evaluate(std::string_view signaling) override {
        std::string buffer{signaling};
        buffer.push_back('\0');

        pj_pool_t* pool = pj_pool_create(
            &cachingPool_.factory,
            "baudot-celix-pjsip",
            4096,
            4096,
            nullptr);
        if (pool == nullptr) {
            return {
                false,
                "PJSIP_PARSE_ERROR",
                std::string{PJSIP_IDENTITY} + ": parser pool allocation failed"
            };
        }

        pjsip_parser_err_report errors;
        pj_list_init(&errors);
        pjsip_msg* message = pjsip_parse_msg(
            pool,
            buffer.data(),
            static_cast<pj_size_t>(signaling.size()),
            &errors);

        const bool parseClean = message != nullptr && pj_list_empty(&errors);
        const bool inviteRequest =
            parseClean &&
            message->type == PJSIP_REQUEST_MSG &&
            pj_stricmp2(&message->line.req.method.name, "INVITE") == 0;

        pj_pool_release(pool);

        if (inviteRequest) {
            return {
                true,
                "PJSIP_PARSE_ACCEPTED",
                std::string{PJSIP_IDENTITY} +
                    ": native parser accepted an INVITE request; no protocol-conformance or authority inference"
            };
        }

        return {
            false,
            "PJSIP_PARSE_REJECTED",
            std::string{PJSIP_IDENTITY} +
                ": native parser did not produce a clean INVITE request; no authority inference"
        };
    }

private:
    bool initialized_{false};
    pj_caching_pool cachingPool_{};
};

class PjsipCallAdmissionBundleActivator {
public:
    explicit PjsipCallAdmissionBundleActivator(const std::shared_ptr<celix::BundleContext>& ctx) {
        registration = ctx->registerService<ICallAdmission>(std::make_shared<PjsipCallAdmission>())
            .addProperty("baudot.capability", ICallAdmission::NAME)
            .addProperty("baudot.capability.version", ICallAdmission::VERSION)
            .addProperty("baudot.implementation", std::string{PJSIP_IDENTITY})
            .addProperty("baudot.control", "native-pjsip")
            .setRegisterAsync(false)
            .build();
    }

private:
    std::shared_ptr<celix::ServiceRegistration> registration{};
};

} // namespace
} // namespace baudot::celixlab

CELIX_GEN_CXX_BUNDLE_ACTIVATOR(baudot::celixlab::PjsipCallAdmissionBundleActivator)
