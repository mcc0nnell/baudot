# BAUDOT-INTEROP-004 cross-implementation positive handoff arm.
#
# Run with the independently admitted Elixip executable in UAS mode:
#
#   elixipp --listen udp:5262 interop004-positive-handoff-target.exs
#
# Elixip owns the independent SIP/dialog behavior in this arm. After Elixip
# observes the replacement ACK, this Baudot-owned scenario emits the repository's
# deterministic canonical primary T.140 RTP datagram to the m=text port offered
# by JAIN SIP. That emission is test stimulus executed from the external scenario
# process; it is NOT evidence that Elixip itself implements RFC 4103 media.
defmodule Baudot.Elixip.Interop004PositiveHandoffTarget do
  use SIP.Scenario
  use SIP.Session.CallUAS

  uas(:invite)
  config(domains: :any)

  @answer_sdp "v=0\r\n" <>
                "o=baudot-elixip 0 0 IN IP4 127.0.0.1\r\n" <>
                "s=baudot-interop004-positive-handoff\r\n" <>
                "c=IN IP4 127.0.0.1\r\n" <>
                "t=0 0\r\n" <>
                "m=text 42620 RTP/AVP 98\r\n" <>
                "a=rtpmap:98 t140/1000\r\n" <>
                "a=sendrecv\r\n"

  # RTP v2, PT=98, seq=1, timestamp=1000, SSRC="BAUD", payload="H".
  # This is the same deterministic primary T.140 packet used by Baudot's Java
  # and Python reference paths.
  @canonical_t140 <<0x80, 0xE2, 0x00, 0x01, 0x00, 0x00, 0x03, 0xE8,
                    0x42, 0x41, 0x55, 0x44, 0x48>>

  state initial_state do
    goto(wait_invite)
  end

  state wait_invite do
    on_events do
      {:INVITE, req, _trans, _dlg} ->
        body = body_text(req.body)
        media_port = text_media_port(body)

        cond do
          is_nil(media_port) ->
            reply_invite(488, "Text media required")
            scenario_failure("replacement offer omitted m=text")

          not String.contains?(String.downcase(body), "t140/1000") ->
            reply_invite(488, "T.140 required")
            scenario_failure("replacement offer omitted t140/1000")

          true ->
            Process.put(:baudot_t140_target_port, media_port)
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
        media_port = Process.get(:baudot_t140_target_port)
        IO.puts("BAUDOT-ELIXIP replacementAckObserved=true")

        case emit_canonical_t140(media_port) do
          :ok ->
            IO.puts(
              "BAUDOT-ELIXIP canonicalT140DatagramSent=true targetPort=#{media_port} bytes=#{byte_size(@canonical_t140)}"
            )

            goto(positive_window, "canonical T.140 stimulus emitted after replacement ACK")

          {:error, reason} ->
            scenario_failure("canonical T.140 stimulus failed: #{inspect(reason)}")
        end

      {:BYE, req, _trans, _dlg} ->
        reply_request(req, 200, "OK")
        scenario_failure("replacement leg torn down before positive readiness observation")
    after
      5_000 -> scenario_failure("replacement ACK not received")
    end
  end

  state positive_window do
    # Keep the replacement dialog alive while Baudot independently observes and
    # reduces the media evidence on the JAIN side.
    on_events do
      {:BYE, req, _trans, _dlg} ->
        reply_request(req, 200, "OK")
        scenario_success("replacement leg closed after positive handoff trial")

      {:dialog_terminated, _dlg, _reason} ->
        scenario_success("replacement dialog ended after positive handoff trial")
    after
      5_000 -> scenario_success("replacement signaling established; canonical T.140 stimulus emitted")
    end
  end

  on_shutdown do
    scenario_aborted("controller stopped positive replacement target")
  end

  defp emit_canonical_t140(port) when is_integer(port) and port > 0 do
    with {:ok, socket} <- :gen_udp.open(0, [:binary]),
         :ok <- :gen_udp.send(socket, {127, 0, 0, 1}, port, @canonical_t140) do
      :gen_udp.close(socket)
      :ok
    else
      {:error, _} = error -> error
    end
  end

  defp emit_canonical_t140(_), do: {:error, :missing_media_port}

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

  defp text_media_port(body) when is_binary(body) do
    case Regex.run(~r/^m=text\s+(\d+)\s+/im, body, capture: :all_but_first) do
      [port] -> String.to_integer(port)
      _ -> nil
    end
  end
end
