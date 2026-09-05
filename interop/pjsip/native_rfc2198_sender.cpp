#include <pjsua2.hpp>

#include <chrono>
#include <condition_variable>
#include <cstdlib>
#include <iostream>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>

using namespace pj;

namespace {

std::mutex state_mutex;
std::condition_variable state_cv;
bool call_confirmed = false;
bool call_disconnected = false;
bool text_media_active = false;
std::string last_state;

int env_int(const char *name, int fallback) {
    const char *value = std::getenv(name);
    return value == nullptr || *value == '\0' ? fallback : std::stoi(value);
}

std::string env_string(const char *name, const std::string &fallback) {
    const char *value = std::getenv(name);
    return value == nullptr || *value == '\0' ? fallback : std::string(value);
}

class NativeRedCall final : public Call {
public:
    explicit NativeRedCall(Account &account) : Call(account) {}

    void onCallState(OnCallStateParam &prm) override {
        PJ_UNUSED_ARG(prm);
        const CallInfo info = getInfo();
        {
            std::lock_guard<std::mutex> lock(state_mutex);
            last_state = info.stateText;
            if (info.state == PJSIP_INV_STATE_CONFIRMED) {
                call_confirmed = true;
            }
            if (info.state == PJSIP_INV_STATE_DISCONNECTED) {
                call_disconnected = true;
            }
        }
        std::cout << "PJSIP_NATIVE_RFC2198_CALL_STATE state=" << info.stateText
                  << " code=" << info.lastStatusCode << std::endl;
        state_cv.notify_all();
    }

    void onCallMediaState(OnCallMediaStateParam &prm) override {
        PJ_UNUSED_ARG(prm);
        const CallInfo info = getInfo();
        bool active = false;
        for (const CallMediaInfo &media : info.media) {
            if (media.type != PJMEDIA_TYPE_TEXT) {
                continue;
            }
            std::cout << "PJSIP_NATIVE_RFC2198_MEDIA_STATE index=" << media.index
                      << " status=" << static_cast<int>(media.status)
                      << " dir=" << static_cast<int>(media.dir) << std::endl;
            if (media.status == PJSUA_CALL_MEDIA_ACTIVE) {
                active = true;
            }
        }
        {
            std::lock_guard<std::mutex> lock(state_mutex);
            text_media_active = active;
        }
        state_cv.notify_all();
    }
};

void send_text(NativeRedCall &call, const std::string &text, int ordinal) {
    CallSendTextParam text_param;
    text_param.medIdx = -1;
    text_param.text = text;
    call.sendText(text_param);
    std::cout << "PJSIP_NATIVE_RFC2198_SEND_REQUESTED ordinal=" << ordinal
              << " text=" << text << std::endl;
}

} // namespace

int main() {
    const int local_port = env_int("BAUDOT_PJSIP_LOCAL_PORT", 5311);
    const int remote_port = env_int("BAUDOT_PJSIP_REMOTE_PORT", 5310);
    const std::string remote_uri = env_string(
            "BAUDOT_PJSIP_REMOTE_URI",
            "sip:baudot-red@127.0.0.1:" + std::to_string(remote_port));
    const std::string first_text = env_string("BAUDOT_PJSIP_TEXT_FIRST", "H");
    const std::string second_text = env_string("BAUDOT_PJSIP_TEXT_SECOND", "I");
    const std::string profile = env_string("BAUDOT_PJSIP_PROFILE_LABEL", "unknown");
    const int redundancy_level = env_int("BAUDOT_PJSIP_REDUNDANCY_LEVEL", 2);

    Endpoint endpoint;
    endpoint.libCreate();

    try {
        EpConfig endpoint_config;
        endpoint_config.uaConfig.userAgent = "Baudot-PJSIP-native-RFC2198/" + profile;
        endpoint_config.uaConfig.maxCalls = 2;
        endpoint_config.logConfig.level = 4;
        endpoint_config.logConfig.consoleLevel = 4;
        endpoint.libInit(endpoint_config);

        TransportConfig transport_config;
        transport_config.port = local_port;
        endpoint.transportCreate(PJSIP_TRANSPORT_UDP, transport_config);
        endpoint.libStart();

        AccountConfig account_config;
        account_config.idUri = "sip:pjsip-red@127.0.0.1:" + std::to_string(local_port);
        account_config.textConfig.redundancyLevel = redundancy_level;
        Account account;
        account.create(account_config);

        NativeRedCall call(account);
        CallOpParam call_param(true);
        call_param.opt.audioCount = 0;
        call_param.opt.videoCount = 0;
        call_param.opt.textCount = 1;

        std::cout << "PJSIP_NATIVE_RFC2198_START profile=" << profile
                  << " remote=" << remote_uri
                  << " textCount=1 redundancyLevel=" << redundancy_level << std::endl;
        call.makeCall(remote_uri, call_param);

        {
            std::unique_lock<std::mutex> lock(state_mutex);
            if (!state_cv.wait_for(lock, std::chrono::seconds(12), [] {
                    return call_confirmed || call_disconnected;
                })) {
                throw std::runtime_error("timed out waiting for confirmed SIP dialog");
            }
            if (!call_confirmed) {
                throw std::runtime_error("call disconnected before confirmation; last state=" + last_state);
            }
        }

        std::cout << "PJSIP_NATIVE_RFC2198_CALL_CONFIRMED" << std::endl;

        {
            std::unique_lock<std::mutex> lock(state_mutex);
            if (!state_cv.wait_for(lock, std::chrono::seconds(12), [] {
                    return text_media_active || call_disconnected;
                })) {
                throw std::runtime_error("timed out waiting for active PJSIP text media");
            }
            if (!text_media_active) {
                throw std::runtime_error("call disconnected before text media became active");
            }
        }

        std::cout << "PJSIP_NATIVE_RFC2198_TEXT_MEDIA_ACTIVE" << std::endl;

        // Drive two ordinary RTT generations. Baudot never constructs RTP or
        // RED payloads here; all wire bytes remain PJMEDIA implementation output.
        send_text(call, first_text, 1);
        std::this_thread::sleep_for(std::chrono::milliseconds(420));
        send_text(call, second_text, 2);

        // Leave enough native text-clock cycles for the configured two-level
        // redundancy history to appear on the wire.
        std::this_thread::sleep_for(std::chrono::milliseconds(1700));

        if (call.isActive()) {
            CallOpParam hangup_param;
            hangup_param.statusCode = PJSIP_SC_DECLINE;
            call.hangup(hangup_param);
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(300));

        account.shutdown();
        endpoint.libDestroy();
        std::cout << "PJSIP_NATIVE_RFC2198_COMPLETE" << std::endl;
        return 0;
    } catch (const Error &error) {
        std::cerr << "PJSIP_NATIVE_RFC2198_ERROR status=" << error.status
                  << " reason=" << error.info() << std::endl;
        try {
            endpoint.libDestroy();
        } catch (...) {
        }
        return 2;
    } catch (const std::exception &error) {
        std::cerr << "PJSIP_NATIVE_RFC2198_ERROR reason=" << error.what() << std::endl;
        try {
            endpoint.libDestroy();
        } catch (...) {
        }
        return 3;
    }
}
