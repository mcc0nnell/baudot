# BAUDOT-INTEROP-004 reverse-direction positive handoff arm.
#
# Elixip owns the original UAC/referrer behavior and sends the in-dialog REFER.
# JAIN SIP executes the transfer. A Baudot-owned controlled provider-b emits the
# repository canonical primary T.140 RTP packet only after it observes the
# replacement ACK. Elixip must observe the original-leg BYE only after that
# readiness path succeeds.
defmodule Baudot.Elixip.Interop004ElixipToJainPositiveHandoff do
  use SIP.Scenario

  config(
    username: "baudot-elixip-referrer-positive",
    authusername: "baudot-elixip-referrer-positive",
    displayname: "Baudot Elixip Referrer Positive",
    domain: "127.0.0.1",
    passwd: "unused",
    proxyusesrv: false
  )

  @provider_a "sip:provider-a@127.0.0.1:5290"
  @provider_b "sip:provider-b@127.0.0.1:5293"

  state initial_state do
    goto(calling)
  end

  state calling do
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
          goto(wait_old_leg_release, "terminal REFER NOTIFY")
        else
          stay("REFER NOTIFY progress")
        end

      {:BYE, req, _trans, _dlg} ->
        reply_request(req, 200, "OK")
        scenario_failure("original leg released before terminal transfer evidence")

      {code, _rsp, _trans, _dlg} when code in 300..699 ->
        scenario_failure("REFER failed with #{code}")
    after
      12_000 -> scenario_failure("REFER did not reach terminal NOTIFY")
    end
  end

  state wait_old_leg_release do
    on_events do
      {:BYE, req, _trans, _dlg} ->
        reply_request(req, 200, "OK")
        IO.puts("BAUDOT-ELIXIP oldLegReleased=true")
        scenario_success("original leg released after positive RTT readiness")
    after
      6_000 -> scenario_failure("original leg was not released after positive RTT readiness")
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
