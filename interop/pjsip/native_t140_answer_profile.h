#pragma once

namespace baudot::pjsipinterop {

struct NativeT140AnswerProfile {
    int statusCode{200};
    unsigned audioCount{0};
    unsigned videoCount{0};
    unsigned textCount{1};
};

constexpr NativeT140AnswerProfile nativeT140AnswerProfile() noexcept {
    return {};
}

} // namespace baudot::pjsipinterop
