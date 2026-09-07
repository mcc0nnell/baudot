#include "BaudotCapabilities.h"

#include <celix/BundleActivator.h>

#include <algorithm>
#include <cctype>
#include <memory>
#include <optional>
#include <string>
#include <string_view>

namespace baudot::celixlab {
namespace {

constexpr std::string_view ADMISSION_IDENTITY =
    "baudot/native-pjsip-uas-text-profile-v1";

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

class PjsipTextProfileAdmission final : public ICallAdmission {
public:
    explicit PjsipTextProfileAdmission(std::shared_ptr<celix::BundleContext> ctx)
        : ctx_{std::move(ctx)} {}

    CapabilityDecision evaluate(std::string_view signaling) override {
        std::optional<CapabilityDecision> parserDecision;
        const bool parserFound = ctx_->useService<ISignalingParser>()
            .addUseCallback([&parserDecision, signaling](ISignalingParser& parser) {
                parserDecision = parser.parse(signaling);
            })
            .build();

        if (!parserFound || !parserDecision.has_value()) {
            return {
                false,
                "PARSER_CAPABILITY_MISSING",
                std::string{ADMISSION_IDENTITY} +
                    ": required ISignalingParser service unavailable; admission failed closed"
            };
        }

        if (!parserDecision->accepted) {
            return {
                false,
                "PJSIP_UAS_TEXT_PROFILE_NOT_ADMITTED",
                std::string{ADMISSION_IDENTITY} +
                    ": parser rejected signaling; admission did not reinterpret parser evidence; parser=" +
                    parserDecision->verdict
            };
        }

        const std::size_t separator = signaling.find("\r\n\r\n");
        if (separator == std::string_view::npos) {
            return {
                false,
                "PJSIP_UAS_TEXT_PROFILE_NOT_ADMITTED",
                std::string{ADMISSION_IDENTITY} +
                    ": parsed INVITE had no message-body boundary; synthetic UAS profile not admitted"
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
                std::string{ADMISSION_IDENTITY} +
                    ": parser accepted and signaling matched the synthetic native-UAS text-only profile "
                    "(audioCount=0, videoCount=0, textCount=1); no SIP/SDP/T.140 conformance or authority inference"
            };
        }

        return {
            false,
            "PJSIP_UAS_TEXT_PROFILE_NOT_ADMITTED",
            std::string{ADMISSION_IDENTITY} +
                ": parser accepted but signaling did not match the synthetic text-only UAS admission profile; "
                "parser success remains distinct from admission"
        };
    }

private:
    std::shared_ptr<celix::BundleContext> ctx_{};
};

class PjsipCallAdmissionBundleActivator {
public:
    explicit PjsipCallAdmissionBundleActivator(const std::shared_ptr<celix::BundleContext>& ctx) {
        registration = ctx->registerService<ICallAdmission>(
                std::make_shared<PjsipTextProfileAdmission>(ctx))
            .addProperty("baudot.capability", ICallAdmission::NAME)
            .addProperty("baudot.capability.version", ICallAdmission::VERSION)
            .addProperty("baudot.implementation", std::string{ADMISSION_IDENTITY})
            .addProperty("baudot.requires", ISignalingParser::NAME)
            .addProperty("baudot.control", "native-pjsip-uas-text-profile")
            .setRegisterAsync(false)
            .build();
    }

private:
    std::shared_ptr<celix::ServiceRegistration> registration{};
};

} // namespace
} // namespace baudot::celixlab

CELIX_GEN_CXX_BUNDLE_ACTIVATOR(baudot::celixlab::PjsipCallAdmissionBundleActivator)
