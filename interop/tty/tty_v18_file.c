#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <sndfile.h>
#include <spandsp.h>

#define SAMPLE_RATE_HZ 8000
#define SAMPLES_PER_CHUNK 160
#define MAX_CHUNKS (60 * 50)
#define FLUSH_CHUNKS 50
#define MAX_TEXT 1024

struct collector {
    char text[MAX_TEXT];
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

static void free_v18(v18_state_t *state)
{
    if (state != NULL)
        v18_free(state);
}

static void pad_silence(int16_t *samples, int actual)
{
    if (actual < 0)
        actual = 0;
    if (actual < SAMPLES_PER_CHUNK) {
        memset(&samples[actual],
               0,
               (size_t) (SAMPLES_PER_CHUNK - actual) * sizeof(*samples));
    }
}

static int encode_wav(const char *path, const char *message)
{
    SF_INFO info;
    SNDFILE *wav = NULL;
    v18_state_t *tx = NULL;
    int16_t audio[SAMPLES_PER_CHUNK];
    int produced;
    int saw_audio = 0;
    int idle_chunks = 0;
    int chunks_written = 0;
    int i;

    memset(&info, 0, sizeof(info));
    info.samplerate = SAMPLE_RATE_HZ;
    info.channels = 1;
    info.format = SF_FORMAT_WAV | SF_FORMAT_PCM_16;

    wav = sf_open(path, SFM_WRITE, &info);
    if (wav == NULL) {
        fprintf(stderr, "failed to open output WAV %s: %s\n", path, sf_strerror(NULL));
        return 2;
    }

    tx = v18_init(NULL,
                  true,
                  V18_MODE_WEITBRECHT_5BIT_4545,
                  V18_AUTOMODING_NONE,
                  collect_text,
                  NULL,
                  ignore_status,
                  NULL);
    if (tx == NULL) {
        fprintf(stderr, "failed to initialize SpanDSP V.18 transmitter\n");
        sf_close(wav);
        return 2;
    }

    if (v18_put(tx, message, -1) != (int) strlen(message)) {
        fprintf(stderr, "v18_put rejected part of the message\n");
        free_v18(tx);
        sf_close(wav);
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

        pad_silence(audio, produced);
        if (sf_writef_short(wav, audio, SAMPLES_PER_CHUNK) != SAMPLES_PER_CHUNK) {
            fprintf(stderr, "failed while writing output WAV\n");
            free_v18(tx);
            sf_close(wav);
            return 2;
        }
        ++chunks_written;

        if (saw_audio && idle_chunks >= FLUSH_CHUNKS)
            break;
    }

    free_v18(tx);
    if (sf_close(wav) != 0) {
        fprintf(stderr, "failed to finalize output WAV\n");
        return 2;
    }

    if (!saw_audio) {
        fprintf(stderr, "SpanDSP generated no V.18 audio\n");
        return 1;
    }

    fprintf(stderr,
            "audioGenerated=true sampleRateHz=%d chunks=%d path=%s\n",
            SAMPLE_RATE_HZ,
            chunks_written,
            path);
    return 0;
}

static int decode_wav(const char *path)
{
    SF_INFO info;
    SNDFILE *wav = NULL;
    v18_state_t *rx = NULL;
    struct collector received = {{0}, 0};
    int16_t audio[SAMPLES_PER_CHUNK];
    sf_count_t frames;
    int i;

    memset(&info, 0, sizeof(info));
    wav = sf_open(path, SFM_READ, &info);
    if (wav == NULL) {
        fprintf(stderr, "failed to open input WAV %s: %s\n", path, sf_strerror(NULL));
        return 2;
    }

    if (info.samplerate != SAMPLE_RATE_HZ || info.channels != 1) {
        fprintf(stderr,
                "unsupported WAV profile: sampleRateHz=%d channels=%d\n",
                info.samplerate,
                info.channels);
        sf_close(wav);
        return 2;
    }

    rx = v18_init(NULL,
                  false,
                  V18_MODE_WEITBRECHT_5BIT_4545,
                  V18_AUTOMODING_NONE,
                  collect_text,
                  &received,
                  ignore_status,
                  NULL);
    if (rx == NULL) {
        fprintf(stderr, "failed to initialize SpanDSP V.18 receiver\n");
        sf_close(wav);
        return 2;
    }

    while ((frames = sf_readf_short(wav, audio, SAMPLES_PER_CHUNK)) > 0) {
        if (frames < SAMPLES_PER_CHUNK) {
            memset(&audio[frames],
                   0,
                   (size_t) (SAMPLES_PER_CHUNK - frames) * sizeof(*audio));
        }
        v18_rx(rx, audio, SAMPLES_PER_CHUNK);
    }

    memset(audio, 0, sizeof(audio));
    for (i = 0; i < FLUSH_CHUNKS; ++i)
        v18_rx(rx, audio, SAMPLES_PER_CHUNK);

    free_v18(rx);
    sf_close(wav);

    if (received.len == 0) {
        fprintf(stderr, "SpanDSP decoded no V.18 text\n");
        return 1;
    }

    if (fwrite(received.text, 1, received.len, stdout) != received.len) {
        fprintf(stderr, "failed to write decoded text\n");
        return 2;
    }
    return 0;
}

static void usage(const char *program)
{
    fprintf(stderr,
            "usage:\n"
            "  %s encode OUTPUT.wav MESSAGE\n"
            "  %s decode INPUT.wav\n",
            program,
            program);
}

int main(int argc, char **argv)
{
    if (argc >= 2 && strcmp(argv[1], "encode") == 0) {
        if (argc != 4) {
            usage(argv[0]);
            return 2;
        }
        return encode_wav(argv[2], argv[3]);
    }

    if (argc >= 2 && strcmp(argv[1], "decode") == 0) {
        if (argc != 3) {
            usage(argv[0]);
            return 2;
        }
        return decode_wav(argv[2]);
    }

    usage(argv[0]);
    return 2;
}
