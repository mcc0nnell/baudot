#include "BaudotCapabilities.h"

#include <celix/BundleActivator.h>

extern "C" {
#include <pjlib.h>
#include <pjsip/sip_endpoint.h>
#include <pjsip/sip_msg.h>
#include <pjsip/sip_parser.h>
}

#include <algorithm>
#include <cctype>
#include <memory>
#include <stdexcept>
#include <string>
#include <string_view>

namespace baudot::celixlab {
namespace {

constexpr std::string_view PJSIP_IDENTITY =
    "pjsip/pjproject-2.17@5a457451fa2712ba18e12b01738e8ff3af2b26fd";

std::string lowercase(std::string_view input) {
    std::string output{input};
    std::transform(output.begin(), output.end(), output.begin(), [](unsigned char ch) {
        return static_cast<char>(std::tolower(ch));
    });
    return output;
}

std::size_t countToken(std::string_view input, std::string_view token) {
    std::size_t count = 0;
    std::size_t offset = 0;
    while ((offset = input.find(token, offset)) != std::string_view::npos) {
        ++count;
        offset += token.size();
    }
    return count;
}

class PjsipCapabilities final : public ISignalingParser, public ICallAdmission {
public:
    PjsipCapabilities() {
        const pj_status_t initStatus = pj_init();
        if (initStatus != PJ_SUCCESS) {
            throw std::runtime_error("pj_init failed for Celix PJSIP capability adapter");
        }
        pjInitialized_ = true;

        pj_caching_pool_init(&cachingPool_, &pj_pool_factory_default_policy, 0);
        poolInitialized_ = true;

        const pj_status_t endpointStatus = pjsip_endpt_create(
            &cachingPool_.factory,
            "baudot-celix-pjsip",
            &endpoint_);
        if (endpointStatus != PJ_SUCCESS) {
            cleanup();
            throw std::runtime_error("pjsip_endpt_create failed for Celix PJSIP capability adapter");
        }
    }

    ~PjsipCapabilities() noexcept override {
        cleanup();
    }

    CapabilityDecision parse(std::string_view signaling) override {
        std::string buffer{signaling};
        buffer.push_back('\0');

        pj_pool_t* pool = pj_pool_create(
            &cachingPool_.factory,
            "baudot-celix-pjsip-parse",
            4096,
            4096,
            nullptr);
        if (pool == nullptr) {
            return {false, "PJSIP_PARSE_ERROR", std::string{PJSIP_IDENTITY} + ": parser pool allocation failed"};
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
                std::string{PJSIP_IDENTITY} + ": native parser produced a clean INVITE request; parser evidence only"
            };
        }

        return {
            false,
            "PJSIP_PARSE_REJECTED",
            std::string{PJSIP_IDENTITY} + ": native parser did not produce a clean INVITE request; no admission or authority inference"
        };
    }

    CapabilityDecision evaluate(std::string_view signaling) override {
        const CapabilityDecision parserDecision = parse(signaling);
        if (!parserDecision.accepted) {
            return {
                false,
                "PJSIP_UAS_TEXT_PROFILE_NOT_ADMITTED",
                std::string{PJSIP_IDENTITY} + ": signaling was not a clean native-parsed INVITE; synthetic UAS profile not admitted"
            };
        }

        const std::size_t separator = signaling.find("\r\n\r\n");
        if (separator == std::string_view::npos) {
            return {
                false,
                "PJSIP_UAS_TEXT_PROFILE_NOT_ADMITTED",
                std::string{PJSIP_IDENTITY} + ": parsed INVITE had no message-body boundary; synthetic UAS profile not admitted"
            };
        }

        const std::string headers = lowercase(signaling.substr(0, separator + 2));
        const std::string body = lowercase(signaling.substr(separator + 4));

        const bool sdpDeclared = headers.find("\r\ncontent-type: application/sdp\r\n") != std::string::npos;
        const bool exactlyOneTextMedia = countToken(body, "\r\nm=text ") == 1;
        const bool noAudioMedia = body.find("\r\nm=audio ") == std::string::npos;
        const bool noVideoMedia = body.find("\r\nm=video ") == std::string::npos;
        const bool t140Mapped = body.find("t140/1000") != std::string::npos;

        if (sdpDeclared && exactlyOneTextMedia && noAudioMedia && noVideoMedia && t140Mapped) {
            return {
                true,
                "PJSIP_UAS_TEXT_PROFILE_ADMITTED",
                std::string{PJSIP_IDENTITY} + ": clean INVITE matched the synthetic native-UAS text-only admission profile (audioCount=0, videoCount=0, textCount=1); no SIP/SDP/T.140 conformance or authority inference"
            };
        }

        return {
            false,
            "PJSIP_UAS_TEXT_PROFILE_NOT_ADMITTED",
            std::string{PJSIP_IDENTITY} + ": clean native-parsed INVITE did not match the synthetic text-only UAS admission profile; parser success remains distinct from admission"
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
        provider = std::make_shared<PjsipCapabilities>();

        parserRegistration = ctx->registerService<ISignalingParser>(
                std::static_pointer_cast<ISignalingParser>(provider))
            .addProperty("baudot.capability", ISignalingParser::NAME)
            .addProperty("baudot.capability.version", ISignalingParser::VERSION)
            .addProperty("baudot.implementation", std::string{PJSIP_IDENTITY})
            .addProperty("baudot.control", "native-pjsip-parser")
            .setRegisterAsync(false)
            .build();

        admissionRegistration = ctx->registerService<ICallAdmission>(
                std::static_pointer_cast<ICallAdmission>(provider))
            .addProperty("baudot.capability", ICallAdmission::NAME)
            .addProperty("baudot.capability.version", ICallAdmission::VERSION)
            .addProperty("baudot.implementation", std::string{PJSIP_IDENTITY})
            .addProperty("baudot.control", "native-pjsip-uas-text-profile")
            .setRegisterAsync(false)
            .build();
    }

private:
    std::shared_ptr<PjsipCapabilities> provider{};
    std::shared_ptr<celix::ServiceRegistration> parserRegistration{};
    std::shared_ptr<celix::ServiceRegistration> admissionRegistration{};
};

} // namespace
} // namespace baudot::celixlab

CELIX_GEN_CXX_BUNDLE_ACTIVATOR(baudot::celixlab::PjsipCallAdmissionBundleActivator)
