#include "linphone/core.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

/*
 * Baudot-owned qualification driver for the external Linphone SDK candidate.
 *
 * This driver deliberately stays at the public Liblinphone API boundary. It
 * does not construct RTP packets, call Mediastreamer2 RFC 4103 filters, or
 * classify T.140 semantics. Its only positive stimulus is one application
 * character passed to linphone_chat_message_put_char().
 */

static void sleep_ms(long milliseconds) {
    struct timespec requested;
    requested.tv_sec = milliseconds / 1000;
    requested.tv_nsec = (milliseconds % 1000) * 1000000L;
    nanosleep(&requested, NULL);
}

static int env_int(const char *name, int fallback) {
    const char *value = getenv(name);
    char *end = NULL;
    long parsed;

    if (value == NULL || *value == '\0') {
        return fallback;
    }
    parsed = strtol(value, &end, 10);
    if (end == value || *end != '\0' || parsed <= 0 || parsed > 3600) {
        fprintf(stderr, "invalid %s=%s\n", name, value);
        exit(2);
    }
    return (int)parsed;
}

static const char *destination(int argc, char **argv) {
    const char *from_env = getenv("BAUDOT_LINPHONE_REMOTE_URI");
    if (from_env != NULL && *from_env != '\0') {
        return from_env;
    }
    if (argc > 1 && argv[1] != NULL && *argv[1] != '\0') {
        return argv[1];
    }
    return NULL;
}

static int terminal_call_state(LinphoneCallState state) {
    return state == LinphoneCallError || state == LinphoneCallEnd || state == LinphoneCallReleased;
}

int main(int argc, char **argv) {
    const char *dest = destination(argc, argv);
    const int connect_timeout_seconds = env_int("BAUDOT_LINPHONE_CONNECT_TIMEOUT", 20);
    const int settle_milliseconds = env_int("BAUDOT_LINPHONE_SETTLE_MS", 1200);
    LinphoneCoreVTable vtable = {0};
    LinphoneCore *core = NULL;
    LinphoneCall *call = NULL;
    LinphoneCallParams *params = NULL;
    LinphoneChatRoom *chat_room = NULL;
    LinphoneChatMessage *message = NULL;
    LCSipTransports transports;
    int elapsed_ms = 0;
    int result = 1;

    if (dest == NULL) {
        fprintf(stderr, "usage: %s sip:destination or set BAUDOT_LINPHONE_REMOTE_URI\n", argv[0]);
        return 2;
    }

    memset(&transports, 0, sizeof(transports));
    transports.udp_port = LC_SIP_TRANSPORT_RANDOM;
    transports.tcp_port = LC_SIP_TRANSPORT_RANDOM;
    transports.tls_port = LC_SIP_TRANSPORT_RANDOM;

    core = linphone_core_new(&vtable, NULL, NULL, NULL);
    if (core == NULL) {
        fprintf(stderr, "failed to create LinphoneCore\n");
        return 3;
    }

    if (linphone_core_set_sip_transports(core, &transports) != 0) {
        fprintf(stderr, "failed to configure random SIP transports\n");
        goto cleanup;
    }

    params = linphone_core_create_call_params(core, NULL);
    if (params == NULL) {
        fprintf(stderr, "failed to create call parameters\n");
        goto cleanup;
    }

    /* Keep the first qualification narrow: text media only. */
    linphone_call_params_enable_audio(params, FALSE);
    linphone_call_params_enable_video(params, FALSE);
    if (linphone_call_params_enable_realtime_text(params, TRUE) != 0) {
        fprintf(stderr, "failed to enable real-time text\n");
        goto cleanup;
    }

    call = linphone_core_invite_with_params(core, dest, params);
    linphone_call_params_unref(params);
    params = NULL;
    if (call == NULL) {
        fprintf(stderr, "failed to create outbound Linphone call to %s\n", dest);
        goto cleanup;
    }
    linphone_call_ref(call);

    printf("baudot.linphone.invite_created=true\n");
    printf("baudot.linphone.remote_uri=%s\n", dest);
    fflush(stdout);

    while (elapsed_ms < connect_timeout_seconds * 1000) {
        LinphoneCallState state;
        linphone_core_iterate(core);
        state = linphone_call_get_state(call);
        if (state == LinphoneCallStreamsRunning) {
            break;
        }
        if (terminal_call_state(state)) {
            fprintf(stderr, "Linphone call ended before streams were running: state=%d\n", (int)state);
            goto cleanup;
        }
        sleep_ms(25);
        elapsed_ms += 25;
    }

    if (linphone_call_get_state(call) != LinphoneCallStreamsRunning) {
        fprintf(stderr, "timed out waiting for LinphoneCallStreamsRunning\n");
        goto cleanup;
    }

    printf("baudot.linphone.streams_running=true\n");
    fflush(stdout);

    chat_room = linphone_call_get_chat_room(call);
    if (chat_room == NULL) {
        fprintf(stderr, "RTT-enabled call did not expose a call-associated chat room\n");
        goto cleanup;
    }

    message = linphone_chat_room_create_message(chat_room, "");
    if (message == NULL) {
        fprintf(stderr, "failed to create call-associated RTT message\n");
        goto cleanup;
    }

    if (linphone_chat_message_put_char(message, (uint32_t)'H') != 0) {
        fprintf(stderr, "linphone_chat_message_put_char failed\n");
        goto cleanup;
    }

    printf("baudot.linphone.native_rtt_api=linphone_chat_message_put_char\n");
    printf("baudot.linphone.character=H\n");
    printf("baudot.linphone.character_codepoint=72\n");
    fflush(stdout);

    /* Give the implementation time to packetize and emit native text media. */
    elapsed_ms = 0;
    while (elapsed_ms < settle_milliseconds) {
        linphone_core_iterate(core);
        sleep_ms(25);
        elapsed_ms += 25;
    }

    result = 0;

cleanup:
    if (message != NULL) {
        linphone_chat_message_unref(message);
    }
    if (params != NULL) {
        linphone_call_params_unref(params);
    }
    if (call != NULL) {
        LinphoneCallState state = linphone_call_get_state(call);
        if (state != LinphoneCallEnd && state != LinphoneCallReleased) {
            linphone_core_terminate_call(core, call);
            for (int i = 0; i < 20; ++i) {
                linphone_core_iterate(core);
                sleep_ms(25);
            }
        }
        linphone_call_unref(call);
    }
    if (core != NULL) {
        linphone_core_destroy(core);
    }

    return result;
}
