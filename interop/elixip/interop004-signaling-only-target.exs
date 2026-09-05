# BAUDOT-INTEROP-004 cross-implementation negative arm.
#
# Run with the independently admitted Elixip executable in UAS mode:
#
#   elixipp --listen udp:5262 interop004-signaling-only-target.exs
#
# This endpoint deliberately proves only replacement signaling. It answers the
# replacement INVITE with text/t140 SDP and never emits an RTP/T.140 packet. The
# Baudot/JAIN side must therefore keep the original leg alive even though the
# replacement SIP dialog is established.
defmodule Baudot.Elixip.Interop004SignalingOnlyTarget do
  use SIP.Scenario
  use SIP.Session.CallUAS

  uas(:invite)
  config(domains: :any)

  @answer_sdp "v=0\r\n" <>
                "o=baudot-elixip 0 0 IN IP4 127.0.0.1\r\n" <>
                "s=baudot-interop004-signaling-only\r\n" <>
                "c=IN IP4 127.0.0.1\r\n" <>
                "t=0 0\r\n" <>
                "m=text 42620 RTP/AVP 98\r\n" <>
                "a=rtpmap:98 t140/1000\r\n" <>
                "a=sendrecv\r\n"

  state initial_state do
    goto(wait_invite)
  end

  state wait_invite do
    on_events do
      {:INVITE, req, _trans, _dlg} ->
        body = body_text(req.body)

        cond do
          not String.contains?(body, "m=text ") ->
            reply_invite(488, "Text media required")
            scenario_failure("replacement offer omitted m=text")

          not String.contains?(String.downcase(body), "t140/1000") ->
            reply_invite(488, "T.140 required")
            scenario_failure("replacement offer omitted t140/1000")

          true ->
            reply_invite(180, "Ringing")
            reply_invite_with_body(200, @answer_sdp)
            goto(wait_ack, "replacement text dialog answered")
        end
    after
      15_000 -> scenario_failure("no replacement INVITE received")
    end
  end

  state wait_ack do
    on_events do
      {:ACK, _req, _trans, _dlg} ->
        # This marker is part of the external implementation observation. The
        # orchestration layer preserves stdout and the independent Baudot reducer
        # requires it before accepting "replacement dialog established".
        IO.puts("BAUDOT-ELIXIP replacementAckObserved=true")
        goto(signaling_only_window, "replacement ACK received")

      {:BYE, req, _trans, _dlg} ->
        reply_request(req, 200, "OK")
        scenario_failure("replacement leg torn down before readiness observation")
    after
      5_000 -> scenario_failure("replacement ACK not received")
    end
  end

  state signaling_only_window do
    # Intentionally do not create a media server, UDP socket, or T.140 sender.
    # The bounded no-packet observation belongs to Baudot's independent side.
    on_events do
      {:BYE, req, _trans, _dlg} ->
        reply_request(req, 200, "OK")
        scenario_success("replacement leg closed after signaling-only trial")

      {:dialog_terminated, _dlg, _reason} ->
        scenario_success("replacement dialog ended after signaling-only trial")
    after
      5_000 -> scenario_success("replacement signaling established; no T.140 emitted")
    end
  end

  on_shutdown do
    scenario_aborted("controller stopped signaling-only replacement target")
  end

  # Elixip represents MIME-bearing SIP bodies as parsed body parts such as
  # [%{contenttype: "application/sdp", data: "..."}]. Keep this shape adapter
  # inside the Baudot-owned scenario rather than reaching into Elixip internals.
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
