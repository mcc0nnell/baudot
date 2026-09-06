#include "BaudotCapabilities.h"
#include "native_t140_answer_profile.h"

#include <celix/BundleActivator.h>

extern "C" {
#include <pjlib.h>
#include <pjsip/sip_endpoint.h>
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
        const pj_status_t initStatus = pj_init();
        if (initStatus != PJ_SUCCESS) {
            throw std::runtime_error("pj_init failed for Celix PJSIP admission adapter");
        }
        pjInitialized_ = true;

        pj_caching_pool_init(&cachingPool_, &pj_pool_factory_default_policy, 0);
        poolInitialized_ = true;

        // pjsip_parse_msg() depends on parser tables initialized by the PJSIP
        // endpoint lifecycle. Use the public endpoint API rather than calling
        // PJSIP's internal init_sip_parser() symbol directly. Creating an
        // endpoint constructs runtime managers but does not register or start
        // any UDP/TCP transport or bind a listening socket.
        const pj_status_t endpointStatus = pjsip_endpt_create(
            &cachingPool_.factory,
            "baudot-celix-pjsip",
            &endpoint_);
        if (endpointStatus != PJ_SUCCESS) {
            cleanup();
            throw std::runtime_error("pjsip_endpt_create failed for Celix PJSIP admission adapter");
        }
    }

    ~PjsipCallAdmission() noexcept override {
        cleanup();
    }

    CapabilityDecision evaluate(std::string_view signaling) override {
        std::string buffer{signaling};
        buffer.push_back('\0');

        pj_pool_t* pool = pj_pool_create(
            &cachingPool_.factory,
            "baudot-celix-pjsip-parse",
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

        if (!inviteRequest) {
            return {
                false,
                "PJSIP_PARSE_REJECTED",
                std::string{PJSIP_IDENTITY} +
                    ": native parser did not produce a clean INVITE request; no authority inference"
            };
        }

        constexpr auto answerProfile = baudot::pjsipinterop::nativeT140AnswerProfile();
        return {
            true,
            "PJSIP_UAS_TEXT_ANSWER_SELECTED",
            std::string{PJSIP_IDENTITY} +
                ": parser=PJSIP_PARSE_ACCEPTED; shared native_t140_uas answer profile statusCode=" +
                std::to_string(answerProfile.statusCode) +
                " audioCount=" + std::to_string(answerProfile.audioCount) +
                " videoCount=" + std::to_string(answerProfile.videoCount) +
                " textCount=" + std::to_string(answerProfile.textCount) +
                "; application answer selection only, not protocol-conformance or authority evidence"
        };
    }

private:
    void cleanup() noexcept {
        if (endpoint_ != nullptr) {
            pjsip_endpt_destroy(endpoint_);
            endpoint_ = nullptr;
        }
        if (poolInitialized_) {
            pj_caching_pool_destroy(&cachingPool_);
            poolInitialized_ = false;
        }
        if (pjInitialized_) {
            pj_shutdown();
            pjInitialized_ = false;
        }
    }

    bool pjInitialized_{false};
    bool poolInitialized_{false};
    pj_caching_pool cachingPool_{};
    pjsip_endpoint* endpoint_{nullptr};
};

class PjsipCallAdmissionBundleActivator {
public:
    explicit PjsipCallAdmissionBundleActivator(const std::shared_ptr<celix::BundleContext>& ctx) {
        registration = ctx->registerService<ICallAdmission>(std::make_shared<PjsipCallAdmission>())
            .addProperty("baudot.capability", ICallAdmission::NAME)
            .addProperty("baudot.capability.version", ICallAdmission::VERSION)
            .addProperty("baudot.implementation", std::string{PJSIP_IDENTITY})
            .addProperty("baudot.control", "native-pjsip-uas-answer-profile")
            .setRegisterAsync(false)
            .build();
    }

private:
    std::shared_ptr<celix::ServiceRegistration> registration{};
};

} // namespace
} // namespace baudot::celixlab

CELIX_GEN_CXX_BUNDLE_ACTIVATOR(baudot::celixlab::PjsipCallAdmissionBundleActivator)
