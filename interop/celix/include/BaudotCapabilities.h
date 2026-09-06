#pragma once

#include <string>
#include <string_view>

namespace baudot::celixlab {

struct CapabilityDecision {
    bool accepted{false};
    std::string verdict{};
    std::string detail{};
};

struct EvidenceObservation {
    std::string profile{};
    std::string capability{};
    std::string verdict{};
    std::string detail{};
};

class ICallAdmission {
public:
    static constexpr const char* NAME = "baudot.call_admission";
    static constexpr const char* VERSION = "1.0.0";

    virtual ~ICallAdmission() noexcept = default;
    virtual CapabilityDecision evaluate(std::string_view signaling) = 0;
};

class IRealtimeTextTransport {
public:
    static constexpr const char* NAME = "baudot.realtime_text_transport";
    static constexpr const char* VERSION = "1.0.0";

    virtual ~IRealtimeTextTransport() noexcept = default;
    virtual CapabilityDecision evaluate(std::string_view payload) = 0;
};

class IEvidenceEmitter {
public:
    static constexpr const char* NAME = "baudot.evidence_emitter";
    static constexpr const char* VERSION = "1.0.0";

    virtual ~IEvidenceEmitter() noexcept = default;
    virtual void emit(const EvidenceObservation& observation) = 0;
};

} // namespace baudot::celixlab
