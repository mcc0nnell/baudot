import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";

const outputPath = process.env.BAUDOT_BROWSER_EVIDENCE || "target/evidence/fed002/browser-webrtc.json";
const timeoutMs = Number(process.env.BAUDOT_BROWSER_TIMEOUT_MS || "15000");

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  const evidence = await page.evaluate(async ({ timeoutMs }) => {
    const pcA = new RTCPeerConnection();
    const pcB = new RTCPeerConnection();

    const waitFor = (predicate, label) => new Promise((resolve, reject) => {
      const deadline = performance.now() + timeoutMs;
      const poll = () => {
        if (predicate()) {
          resolve();
          return;
        }
        if (performance.now() >= deadline) {
          reject(new Error(`timeout waiting for ${label}`));
          return;
        }
        setTimeout(poll, 25);
      };
      poll();
    });

    const waitForIceGathering = async (pc, label) => {
      if (pc.iceGatheringState === "complete") return;
      await waitFor(() => pc.iceGatheringState === "complete", `${label} ICE gathering`);
    };

    let remoteChannel;
    let receivedText = null;
    pcB.ondatachannel = (event) => {
      remoteChannel = event.channel;
      remoteChannel.onmessage = (messageEvent) => {
        receivedText = String(messageEvent.data);
      };
    };

    const localChannel = pcA.createDataChannel("baudot-t140", {
      ordered: true,
      protocol: "t140",
    });

    await pcA.setLocalDescription(await pcA.createOffer());
    await waitForIceGathering(pcA, "offerer");
    await pcB.setRemoteDescription(pcA.localDescription);

    await pcB.setLocalDescription(await pcB.createAnswer());
    await waitForIceGathering(pcB, "answerer");
    await pcA.setRemoteDescription(pcB.localDescription);

    await waitFor(() => remoteChannel !== undefined, "remote T.140 data channel");
    await waitFor(
      () => localChannel.readyState === "open" && remoteChannel?.readyState === "open",
      "T.140 data channel open",
    );
    await waitFor(
      () => ["connected", "completed"].includes(pcA.iceConnectionState)
        && ["connected", "completed"].includes(pcB.iceConnectionState),
      "ICE connected",
    );
    await waitFor(
      () => pcA.sctp?.state === "connected" && pcB.sctp?.state === "connected",
      "SCTP connected",
    );
    await waitFor(
      () => pcA.sctp?.transport?.state === "connected" && pcB.sctp?.transport?.state === "connected",
      "DTLS connected",
    );

    localChannel.send("Hi");
    await waitFor(() => receivedText === "Hi", "T.140 message delivery");

    const summarizePeer = async (pc) => {
      const stats = await pc.getStats();
      const candidatePairs = [];
      for (const report of stats.values()) {
        if (report.type === "candidate-pair" && report.state === "succeeded") {
          candidatePairs.push({
            id: report.id,
            nominated: report.nominated === true,
            state: report.state,
            localCandidateId: report.localCandidateId ?? null,
            remoteCandidateId: report.remoteCandidateId ?? null,
          });
        }
      }
      return {
        connectionState: pc.connectionState,
        iceConnectionState: pc.iceConnectionState,
        iceGatheringState: pc.iceGatheringState,
        signalingState: pc.signalingState,
        sctpState: pc.sctp?.state ?? null,
        dtlsState: pc.sctp?.transport?.state ?? null,
        succeededCandidatePairs: candidatePairs,
      };
    };

    const encodeHex = (text) => Array.from(new TextEncoder().encode(text))
      .map((value) => value.toString(16).padStart(2, "0"))
      .join(" ");

    const channelSummary = (channel) => ({
      label: channel.label,
      protocol: channel.protocol,
      ordered: channel.ordered,
      maxPacketLifeTime: channel.maxPacketLifeTime,
      maxRetransmits: channel.maxRetransmits,
      negotiated: channel.negotiated,
      readyState: channel.readyState,
    });

    const result = {
      implementation: {
        userAgent: navigator.userAgent,
        platform: navigator.platform,
      },
      offerer: await summarizePeer(pcA),
      answerer: await summarizePeer(pcB),
      localDataChannel: channelSummary(localChannel),
      remoteDataChannel: channelSummary(remoteChannel),
      receivedText,
      receivedUtf8Hex: encodeHex(receivedText),
    };

    localChannel.close();
    remoteChannel.close();
    pcA.close();
    pcB.close();
    return result;
  }, { timeoutMs });

  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, `${JSON.stringify(evidence, null, 2)}\n`, "utf8");
  console.log(JSON.stringify(evidence, null, 2));
} finally {
  await browser.close();
}
