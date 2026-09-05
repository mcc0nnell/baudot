import crypto from "node:crypto";
import dgram from "node:dgram";
import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";

const listenHost = process.env.BAUDOT_GATEWAY_BIND_IP || "127.0.0.1";
const listenPort = Number(process.env.BAUDOT_GATEWAY_BIND_PORT || "46000");
const forwardHost = process.env.BAUDOT_GATEWAY_FORWARD_IP || "127.0.0.1";
const forwardPort = Number(process.env.BAUDOT_GATEWAY_FORWARD_PORT || "45000");
const expectedDatagrams = Number(process.env.BAUDOT_GATEWAY_EXPECT_DATAGRAMS || "2");
const timeoutMs = Number(process.env.BAUDOT_GATEWAY_TIMEOUT_MS || "15000");
const evidenceDir = process.env.BAUDOT_GATEWAY_EVIDENCE_DIR || "target/evidence/fed003/gateway";
const readyPath = process.env.BAUDOT_GATEWAY_READY_FILE || path.join(evidenceDir, "ready.json");
const resultPath = process.env.BAUDOT_GATEWAY_RESULT_FILE || path.join(evidenceDir, "gateway-result.json");

const T140_PAYLOAD_TYPE = 98;
const RED_PAYLOAD_TYPE = 99;
const RTP_FIXED_HEADER_SIZE = 12;

function sha256(bytes) {
  return crypto.createHash("sha256").update(bytes).digest("hex");
}

function decodeUtf8(bytes) {
  return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
}

function parseRtpT140Primary(packet) {
  if (packet.length < RTP_FIXED_HEADER_SIZE + 1) {
    throw new Error("RTP packet shorter than fixed header plus T.140 payload");
  }
  const first = packet[0];
  if ((first >> 6) !== 2 || (first & 0x3f) !== 0) {
    throw new Error("gateway supports only minimal RTP v2 without padding/extensions/CSRCs");
  }

  const outerPayloadType = packet[1] & 0x7f;
  const sequenceNumber = packet.readUInt16BE(2);
  const timestamp = packet.readUInt32BE(4);
  const ssrc = packet.readUInt32BE(8);

  if (outerPayloadType === T140_PAYLOAD_TYPE) {
    const primary = packet.subarray(RTP_FIXED_HEADER_SIZE);
    return {
      outerPayloadType,
      sequenceNumber,
      timestamp,
      ssrc,
      primaryPayloadType: T140_PAYLOAD_TYPE,
      primary,
      primaryText: decodeUtf8(primary),
      redundant: [],
    };
  }

  if (outerPayloadType !== RED_PAYLOAD_TYPE) {
    throw new Error(`unsupported RTP payload type ${outerPayloadType}`);
  }

  let cursor = RTP_FIXED_HEADER_SIZE;
  const headers = [];
  let primaryPayloadType;
  while (cursor < packet.length) {
    const headerFirst = packet[cursor];
    const follows = (headerFirst & 0x80) !== 0;
    const blockPayloadType = headerFirst & 0x7f;
    if (!follows) {
      primaryPayloadType = blockPayloadType;
      cursor += 1;
      break;
    }
    if (cursor + 4 > packet.length) {
      throw new Error("truncated RFC 2198 redundant header");
    }
    const packed = packet.readUIntBE(cursor + 1, 3);
    headers.push({
      payloadType: blockPayloadType,
      timestampOffset: packed >> 10,
      blockLength: packed & 0x03ff,
    });
    cursor += 4;
  }

  if (primaryPayloadType !== T140_PAYLOAD_TYPE || headers.length === 0) {
    throw new Error("RED packet does not match the expected T.140 profile");
  }

  const redundant = [];
  for (const header of headers) {
    if (header.payloadType !== T140_PAYLOAD_TYPE) {
      throw new Error("RED packet contains a non-T.140 redundant block");
    }
    const end = cursor + header.blockLength;
    if (end > packet.length) {
      throw new Error("RED redundant block exceeds packet length");
    }
    const payload = packet.subarray(cursor, end);
    redundant.push({
      payloadType: header.payloadType,
      timestampOffset: header.timestampOffset,
      blockLength: header.blockLength,
      text: decodeUtf8(payload),
      utf8Hex: payload.toString("hex").match(/../g)?.join(" ") || "",
    });
    cursor = end;
  }

  const primary = packet.subarray(cursor);
  return {
    outerPayloadType,
    sequenceNumber,
    timestamp,
    ssrc,
    primaryPayloadType,
    primary,
    primaryText: decodeUtf8(primary),
    redundant,
  };
}

async function setupBrowser(page) {
  await page.evaluate(async ({ timeoutMs }) => {
    const pcA = new RTCPeerConnection();
    const pcB = new RTCPeerConnection();
    const state = {
      pcA,
      pcB,
      localChannel: null,
      remoteChannel: null,
      receivedMessages: [],
    };
    window.baudotGateway = state;

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

    pcB.ondatachannel = (event) => {
      state.remoteChannel = event.channel;
      state.remoteChannel.onmessage = (messageEvent) => {
        state.receivedMessages.push(String(messageEvent.data));
      };
    };

    state.localChannel = pcA.createDataChannel("baudot-t140", {
      ordered: true,
      protocol: "t140",
    });

    await pcA.setLocalDescription(await pcA.createOffer());
    await waitForIceGathering(pcA, "offerer");
    await pcB.setRemoteDescription(pcA.localDescription);
    await pcB.setLocalDescription(await pcB.createAnswer());
    await waitForIceGathering(pcB, "answerer");
    await pcA.setRemoteDescription(pcB.localDescription);

    await waitFor(() => state.remoteChannel !== null, "remote data channel");
    await waitFor(
      () => state.localChannel.readyState === "open" && state.remoteChannel.readyState === "open",
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
  }, { timeoutMs });
}

async function browserSummary(page) {
  return page.evaluate(async () => {
    const state = window.baudotGateway;
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
    const channelSummary = (channel) => ({
      label: channel.label,
      protocol: channel.protocol,
      ordered: channel.ordered,
      maxPacketLifeTime: channel.maxPacketLifeTime,
      maxRetransmits: channel.maxRetransmits,
      readyState: channel.readyState,
    });
    const joined = state.receivedMessages.join("");
    const utf8Hex = Array.from(new TextEncoder().encode(joined))
      .map((value) => value.toString(16).padStart(2, "0"))
      .join(" ");
    return {
      implementation: {
        userAgent: navigator.userAgent,
        platform: navigator.platform,
      },
      offerer: await summarizePeer(state.pcA),
      answerer: await summarizePeer(state.pcB),
      localDataChannel: channelSummary(state.localChannel),
      remoteDataChannel: channelSummary(state.remoteChannel),
      receivedMessages: [...state.receivedMessages],
      receivedText: joined,
      receivedUtf8Hex: utf8Hex,
    };
  });
}

fs.mkdirSync(evidenceDir, { recursive: true });
const browser = await chromium.launch({ headless: true });
const socket = dgram.createSocket("udp4");
const events = [];
let fatalError = null;
let datagramCount = 0;
let forwardedCount = 0;
let primaryText = "";

try {
  const page = await browser.newPage();
  await setupBrowser(page);

  await new Promise((resolve, reject) => {
    socket.once("error", reject);
    socket.bind(listenPort, listenHost, () => {
      socket.off("error", reject);
      resolve();
    });
  });

  fs.writeFileSync(
    readyPath,
    `${JSON.stringify({ ready: true, bind: `${listenHost}:${listenPort}`, forward: `${forwardHost}:${forwardPort}` }, null, 2)}\n`,
    "utf8",
  );

  let processing = Promise.resolve();
  let resolveDone;
  const done = new Promise((resolve) => { resolveDone = resolve; });

  socket.on("message", (message, remote) => {
    datagramCount += 1;
    const index = datagramCount;
    processing = processing.then(async () => {
      const rawPath = path.join(evidenceDir, `rtt-datagram-${index}-received.bin`);
      fs.writeFileSync(rawPath, message);

      await new Promise((resolve, reject) => {
        socket.send(message, forwardPort, forwardHost, (error) => {
          if (error) reject(error);
          else resolve();
        });
      });
      forwardedCount += 1;

      const parsed = parseRtpT140Primary(message);
      primaryText += parsed.primaryText;
      await page.evaluate((text) => {
        window.baudotGateway.localChannel.send(text);
      }, parsed.primaryText);

      events.push({
        index,
        source: `${remote.address}:${remote.port}`,
        bytes: message.length,
        sha256: sha256(message),
        outerPayloadType: parsed.outerPayloadType,
        sequenceNumber: parsed.sequenceNumber,
        timestamp: parsed.timestamp,
        primaryPayloadType: parsed.primaryPayloadType,
        primaryText: parsed.primaryText,
        primaryUtf8Hex: parsed.primary.toString("hex").match(/../g)?.join(" ") || "",
        redundant: parsed.redundant,
        forwardedUnchanged: true,
      });
    }).catch((error) => {
      fatalError = error;
    }).finally(() => {
      if (index >= expectedDatagrams) resolveDone();
    });
  });

  const timeout = new Promise((_, reject) => {
    setTimeout(() => reject(new Error(`timeout waiting for ${expectedDatagrams} RTP datagrams`)), timeoutMs);
  });
  await Promise.race([done, timeout]);
  await processing;
  if (fatalError) throw fatalError;

  await page.waitForFunction(
    (expected) => window.baudotGateway.receivedMessages.length >= expected,
    expectedDatagrams,
    { timeout: timeoutMs },
  );

  const browserEvidence = await browserSummary(page);
  const result = {
    scenario: "BAUDOT-FED-003",
    gateway: {
      bind: `${listenHost}:${listenPort}`,
      forward: `${forwardHost}:${forwardPort}`,
      datagramsReceived: datagramCount,
      datagramsForwarded: forwardedCount,
      primaryText,
      mediaTerminates: true,
      securityClaimBoundary: "SIP-side T.140 is decoded and re-originated over WebRTC; no unqualified E2EE claim across gateway",
    },
    inputDatagrams: events,
    browser: browserEvidence,
  };

  fs.writeFileSync(resultPath, `${JSON.stringify(result, null, 2)}\n`, "utf8");
  console.log(JSON.stringify(result, null, 2));

  if (
    datagramCount !== expectedDatagrams
    || forwardedCount !== expectedDatagrams
    || primaryText !== "Hi"
    || browserEvidence.receivedText !== primaryText
  ) {
    process.exitCode = 5;
  }
} catch (error) {
  const failure = {
    scenario: "BAUDOT-FED-003",
    error: String(error?.stack || error),
    datagramsReceived: datagramCount,
    datagramsForwarded: forwardedCount,
  };
  fs.writeFileSync(resultPath, `${JSON.stringify(failure, null, 2)}\n`, "utf8");
  console.error(JSON.stringify(failure, null, 2));
  process.exitCode = 5;
} finally {
  try { socket.close(); } catch {}
  await browser.close();
}
