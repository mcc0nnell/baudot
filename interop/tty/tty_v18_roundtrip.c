#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <spandsp.h>

#define SAMPLES_PER_CHUNK 160
#define MAX_CHUNKS (60 * 50)
#define FLUSH_CHUNKS 20

struct collector {
    char text[1024];
    size_t len;
};

static void collect_text(void *user_data, const uint8_t *msg, int len)
{
    struct collector *collector = (struct collector *) user_data;
    size_t available;
    size_t copy_len;

    if (collector == NULL || msg == NULL || len <= 0)
        return;

    available = sizeof(collector->text) - 1 - collector->len;
    copy_len = (size_t) len < available ? (size_t) len : available;
    memcpy(&collector->text[collector->len], msg, copy_len);
    collector->len += copy_len;
    collector->text[collector->len] = '\0';
}

static void ignore_status(void *user_data, int status)
{
    (void) user_data;
    (void) status;
}

static void pad_silence(int16_t *samples, int actual, int target)
{
    if (actual < 0)
        actual = 0;
    if (actual < target)
        memset(&samples[actual], 0, (size_t) (target - actual) * sizeof(*samples));
}

int main(int argc, char **argv)
{
    const char *message = argc > 1 ? argv[1] : "HELLO GA";
    struct collector received = {{0}, 0};
    v18_state_t *tx = NULL;
    v18_state_t *rx = NULL;
    int16_t audio[SAMPLES_PER_CHUNK];
    int produced;
    int idle_chunks = 0;
    int saw_audio = 0;
    int i;

    tx = v18_init(NULL,
                  true,
                  V18_MODE_WEITBRECHT_5BIT_4545,
                  V18_AUTOMODING_NONE,
                  collect_text,
                  NULL,
                  ignore_status,
                  NULL);
    rx = v18_init(NULL,
                  false,
                  V18_MODE_WEITBRECHT_5BIT_4545,
                  V18_AUTOMODING_NONE,
                  collect_text,
                  &received,
                  ignore_status,
                  NULL);

    if (tx == NULL || rx == NULL) {
        fprintf(stderr, "failed to initialize SpanDSP V.18 contexts\n");
        v18_free(tx);
        v18_free(rx);
        return 2;
    }

    if (v18_put(tx, message, -1) != (int) strlen(message)) {
        fprintf(stderr, "v18_put rejected part of the message\n");
        v18_free(tx);
        v18_free(rx);
        return 2;
    }

    for (i = 0; i < MAX_CHUNKS; ++i) {
        produced = v18_tx(tx, audio, SAMPLES_PER_CHUNK);
        if (produced > 0) {
            saw_audio = 1;
            idle_chunks = 0;
        } else if (saw_audio) {
            ++idle_chunks;
        }

        pad_silence(audio, produced, SAMPLES_PER_CHUNK);
        v18_rx(rx, audio, SAMPLES_PER_CHUNK);

        if (received.len >= strlen(message) &&
            strcmp(received.text, message) == 0 &&
            idle_chunks >= FLUSH_CHUNKS)
            break;
    }

    printf("sent=%s\n", message);
    printf("received=%s\n", received.text);

    v18_free(tx);
    v18_free(rx);

    if (strcmp(received.text, message) != 0) {
        fprintf(stderr, "V.18 round-trip mismatch\n");
        return 1;
    }

    return 0;
}
