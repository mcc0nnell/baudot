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
std::string last_state;

int env_int(const char *name, int fallback) {
    const char *value = std::getenv(name);
    if (value == nullptr || *value == '\0') {
        return fallback;
    }
    return std::stoi(value);
}

std::string env_string(const char *name, const std::string &fallback) {
    const char *value = std::getenv(name);
    return value == nullptr || *value == '\0' ? fallback : std::string(value);
}

class NativeTextCall final : public Call {
public:
    explicit NativeTextCall(Account &account) : Call(account) {}

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
        std::cout << "PJSIP_NATIVE_T140_CALL_STATE state=" << info.stateText
                  << " code=" << info.lastStatusCode << std::endl;
        state_cv.notify_all();
    }

    void onCallRxText(OnCallRxTextParam &prm) override {
        std::cout << "PJSIP_NATIVE_T140_RX_TEXT seq=" << prm.seq
                  << " text=" << prm.text << std::endl;
    }
};

} // namespace

int main() {
    const int local_port = env_int("BAUDOT_PJSIP_LOCAL_PORT", 5291);
    const int remote_port = env_int("BAUDOT_PJSIP_REMOTE_PORT", 5290);
    const std::string remote_uri = env_string(
            "BAUDOT_PJSIP_REMOTE_URI",
            "sip:baudot@127.0.0.1:" + std::to_string(remote_port));
    const std::string text = env_string("BAUDOT_PJSIP_TEXT", "H");

    Endpoint endpoint;
    endpoint.libCreate();

    try {
        EpConfig endpoint_config;
        endpoint_config.uaConfig.userAgent = "Baudot-PJSIP-native-T140/2.17";
        endpoint_config.uaConfig.maxCalls = 2;
        endpoint_config.logConfig.level = 4;
        endpoint_config.logConfig.consoleLevel = 4;
        endpoint.libInit(endpoint_config);

        TransportConfig transport_config;
        transport_config.port = local_port;
        endpoint.transportCreate(PJSIP_TRANSPORT_UDP, transport_config);
        endpoint.libStart();

        AccountConfig account_config;
        account_config.idUri = "sip:pjsip@127.0.0.1:" + std::to_string(local_port);
        Account account;
        account.create(account_config);

        NativeTextCall call(account);
        CallOpParam call_param(true);
        call_param.opt.audioCount = 0;
        call_param.opt.videoCount = 0;
        call_param.opt.textCount = 1;

        std::cout << "PJSIP_NATIVE_T140_START release=2.17 remote=" << remote_uri
                  << " textCount=1" << std::endl;
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

        std::cout << "PJSIP_NATIVE_T140_CALL_CONFIRMED" << std::endl;
        std::this_thread::sleep_for(std::chrono::milliseconds(250));

        CallSendTextParam text_param;
        text_param.medIdx = -1;
        text_param.text = text;
        call.sendText(text_param);
        std::cout << "PJSIP_NATIVE_T140_SEND_REQUESTED text=" << text << std::endl;

        std::this_thread::sleep_for(std::chrono::milliseconds(1600));

        if (call.isActive()) {
            CallOpParam hangup_param;
            hangup_param.statusCode = PJSIP_SC_DECLINE;
            call.hangup(hangup_param);
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(300));

        account.shutdown();
        endpoint.libDestroy();
        std::cout << "PJSIP_NATIVE_T140_COMPLETE" << std::endl;
        return 0;
    } catch (const Error &error) {
        std::cerr << "PJSIP_NATIVE_T140_ERROR status=" << error.status
                  << " reason=" << error.info() << std::endl;
        try {
            endpoint.libDestroy();
        } catch (...) {
        }
        return 2;
    } catch (const std::exception &error) {
        std::cerr << "PJSIP_NATIVE_T140_ERROR reason=" << error.what() << std::endl;
        try {
            endpoint.libDestroy();
        } catch (...) {
        }
        return 3;
    }
}
