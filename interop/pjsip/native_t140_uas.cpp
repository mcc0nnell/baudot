#include <pjsua2.hpp>

#include <chrono>
#include <condition_variable>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>

using namespace pj;

namespace {

std::mutex state_mutex;
std::condition_variable state_cv;
bool incoming_call_observed = false;
bool call_confirmed = false;
bool text_media_active = false;
bool text_sent = false;
bool call_disconnected = false;
std::string configured_text = "H";

int env_int(const char *name, int fallback) {
    const char *value = std::getenv(name);
    return value == nullptr || *value == '\0' ? fallback : std::stoi(value);
}

std::string env_string(const char *name, const std::string &fallback) {
    const char *value = std::getenv(name);
    return value == nullptr || *value == '\0' ? fallback : std::string(value);
}

class NativeTextCall final : public Call {
public:
    NativeTextCall(Account &account, int call_id) : Call(account, call_id) {}

    void onCallState(OnCallStateParam &prm) override {
        PJ_UNUSED_ARG(prm);
        const CallInfo info = getInfo();
        {
            std::lock_guard<std::mutex> lock(state_mutex);
            call_confirmed = info.state == PJSIP_INV_STATE_CONFIRMED || call_confirmed;
            call_disconnected = info.state == PJSIP_INV_STATE_DISCONNECTED;
        }
        std::cout << "PJSIP_NATIVE_T140_UAS_CALL_STATE state=" << info.stateText
                  << " code=" << info.lastStatusCode << std::endl;
        maybeSend();
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
            std::cout << "PJSIP_NATIVE_T140_UAS_MEDIA_STATE index=" << media.index
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
        maybeSend();
        state_cv.notify_all();
    }

    void onCallRxText(OnCallRxTextParam &prm) override {
        std::cout << "PJSIP_NATIVE_T140_UAS_RX_TEXT seq=" << prm.seq
                  << " text=" << prm.text << std::endl;
    }

private:
    void maybeSend() {
        bool should_send = false;
        {
            std::lock_guard<std::mutex> lock(state_mutex);
            if (call_confirmed && text_media_active && !text_sent && !call_disconnected) {
                text_sent = true;
                should_send = true;
            }
        }
        if (!should_send) {
            return;
        }

        try {
            CallSendTextParam param;
            param.medIdx = -1;
            param.text = configured_text;
            sendText(param);
            std::cout << "PJSIP_NATIVE_T140_UAS_SEND_REQUESTED text="
                      << configured_text << std::endl;
        } catch (...) {
            {
                std::lock_guard<std::mutex> lock(state_mutex);
                text_sent = false;
            }
            throw;
        }
        state_cv.notify_all();
    }
};

class NativeTextAccount final : public Account {
public:
    void onIncomingCall(OnIncomingCallParam &iprm) override {
        call = std::make_unique<NativeTextCall>(*this, iprm.callId);
        {
            std::lock_guard<std::mutex> lock(state_mutex);
            incoming_call_observed = true;
        }
        std::cout << "PJSIP_NATIVE_T140_UAS_INCOMING callId=" << iprm.callId << std::endl;

        CallOpParam answer(true);
        answer.statusCode = PJSIP_SC_OK;
        answer.opt.audioCount = 0;
        answer.opt.videoCount = 0;
        answer.opt.textCount = 1;
        call->answer(answer);
        std::cout << "PJSIP_NATIVE_T140_UAS_ANSWER_REQUESTED textCount=1" << std::endl;
        state_cv.notify_all();
    }

private:
    std::unique_ptr<NativeTextCall> call;
};

} // namespace

int main() {
    const int local_port = env_int("BAUDOT_PJSIP_UAS_PORT", 5302);
    configured_text = env_string("BAUDOT_PJSIP_TEXT", "H");

    Endpoint endpoint;
    endpoint.libCreate();

    try {
        EpConfig endpoint_config;
        endpoint_config.uaConfig.userAgent = "Baudot-PJSIP-native-T140-UAS/2.17";
        endpoint_config.uaConfig.maxCalls = 2;
        endpoint_config.logConfig.level = 4;
        endpoint_config.logConfig.consoleLevel = 4;
        endpoint.libInit(endpoint_config);

        TransportConfig transport_config;
        transport_config.port = local_port;
        endpoint.transportCreate(PJSIP_TRANSPORT_UDP, transport_config);
        endpoint.libStart();

        AccountConfig account_config;
        account_config.idUri = "sip:pjsip-target@127.0.0.1:" + std::to_string(local_port);
        NativeTextAccount account;
        account.create(account_config);

        std::cout << "PJSIP_NATIVE_T140_UAS_READY release=2.17 port=" << local_port << std::endl;

        {
            std::unique_lock<std::mutex> lock(state_mutex);
            if (!state_cv.wait_for(lock, std::chrono::seconds(15), [] {
                    return incoming_call_observed && text_sent;
                })) {
                throw std::runtime_error("timed out waiting for incoming native text send");
            }
        }

        std::cout << "PJSIP_NATIVE_T140_UAS_TEXT_SENT" << std::endl;

        {
            std::unique_lock<std::mutex> lock(state_mutex);
            if (!state_cv.wait_for(lock, std::chrono::seconds(15), [] {
                    return call_disconnected;
                })) {
                throw std::runtime_error("timed out waiting for remote call release");
            }
        }

        std::cout << "PJSIP_NATIVE_T140_UAS_REMOTE_RELEASE_OBSERVED" << std::endl;
        account.shutdown();
        endpoint.libDestroy();
        std::cout << "PJSIP_NATIVE_T140_UAS_COMPLETE" << std::endl;
        return 0;
    } catch (const Error &error) {
        std::cerr << "PJSIP_NATIVE_T140_UAS_ERROR status=" << error.status
                  << " reason=" << error.info() << std::endl;
        try {
            endpoint.libDestroy();
        } catch (...) {
        }
        return 2;
    } catch (const std::exception &error) {
        std::cerr << "PJSIP_NATIVE_T140_UAS_ERROR reason=" << error.what() << std::endl;
        try {
            endpoint.libDestroy();
        } catch (...) {
        }
        return 3;
    }
}
