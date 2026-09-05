# Baudot-owned Elixip FSL scenario.
#
# This is intentionally not an interoperability test. It proves only that a
# pinned external Elixip checkout can load and execute a Baudot-owned scenario
# across the process/scenario boundary defined by ADR-0001.
defmodule Baudot.Elixip.AdmissionSmoke do
  use SIP.Scenario

  config username: "baudot-admission", domain: "example.invalid"

  state initial_state do
    appdata_set(:contract, "BAUDOT-ELIXIP-ADMISSION-001")
    goto(done, "Baudot scenario loaded by external Elixip runtime")
  end

  state done do
    scenario_success(appdata_get(:contract))
  end
end
