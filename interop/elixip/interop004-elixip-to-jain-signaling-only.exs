# BAUDOT-INTEROP-004 reverse-direction signaling-only arm.
#
# Elixip owns the original UAC/referrer behavior and sends an in-dialog REFER to
# the JAIN SIP transfer processor. JAIN establishes the replacement dialog with
# its controlled provider-b peer, negotiates text/t140, observes no T.140 during
# the bounded window, and must preserve this original Elixip dialog.
defmodule Baudot.Elixip.Interop004ElixipToJainSignalingOnly do
  use SIP.Scenario

  config(
    username: "baudot-elixip-referrer",
    authusername: "baudot-elixip-referrer",
    displayname: "Baudot Elixip Referrer",
    domain: "127.0.0.1",
    passwd: "unused",
    proxyusesrv: false
  )

  @provider_a "sip:provider-a@127.0.0.1:5280"
  @provider_b "sip:provider-b@127.0.0.1:5283"

  state initial_state do
    goto(calling)
  end

  state calling do
    # No media is needed on the original leg. A zero-length explicit body keeps
    # this UAC independent of Elixip's media-server adapter.
    send_INVITE(@provider_a, "", 5)

    on_events do
      {code, _rsp, _trans, _dlg} when code in 100..199 ->
        stay("original call progress")

      {200, rsp, trans, _dlg} ->
        process_invite_reply(rsp, trans)
        IO.puts("BAUDOT-ELIXIP originalDialogEstablished=true")
        goto(send_transfer, "original dialog established")

      {code, _rsp, _trans, _dlg} when code in 300..699 ->
        scenario_failure("original INVITE failed with #{code}")
    after
      8_000 -> scenario_failure("original INVITE timed out")
    end
  end

  state send_transfer do
    send_REFER(@provider_b)
    IO.puts("BAUDOT-ELIXIP referSent=true target=#{@provider_b}")
    goto(wait_transfer)
  end

  state wait_transfer do
    on_events do
      {202, _rsp, _trans, _dlg} ->
        IO.puts("BAUDOT-ELIXIP referAccepted=true")
        stay("REFER accepted")

      {:NOTIFY, req, _trans, _dlg} ->
        state = req["Subscription-State"] || req["subscription-state"] || ""
        body = body_text(req.body)
        reply_request(req, 200, "OK")

        if String.starts_with?(String.downcase(state), "terminated") and
             String.contains?(body, "SIP/2.0 200") do
          IO.puts("BAUDOT-ELIXIP terminalNotifyObserved=true subscriptionState=#{state}")
          goto(verify_old_leg_preserved, "terminal REFER NOTIFY")
        else
          stay("REFER NOTIFY progress")
        end

      {:BYE, req, _trans, _dlg} ->
        reply_request(req, 200, "OK")
        scenario_failure("original leg released before RTT readiness")

      {code, _rsp, _trans, _dlg} when code in 300..699 ->
        scenario_failure("REFER failed with #{code}")
    after
      12_000 -> scenario_failure("REFER did not reach terminal NOTIFY")
    end
  end

  state verify_old_leg_preserved do
    on_events do
      {:BYE, req, _trans, _dlg} ->
        reply_request(req, 200, "OK")
        scenario_failure("original leg released in signaling-only arm")
    after
      2_000 ->
        IO.puts("BAUDOT-ELIXIP oldLegPreserved=true")
        scenario_success("signaling complete; no RTT readiness; original leg preserved")
    end
  end

  defp body_text(body) when is_binary(body), do: body

  defp body_text(body) when is_list(body) do
    body
    |> Enum.map(fn
      %{data: data} when is_binary(data) -> data
      %{"data" => data} when is_binary(data) -> data
      _ -> ""
    end)
    |> Enum.join("\n")
  end

  defp body_text(_), do: ""
end
