# Dual ACE Connect Lite runtime lab

This lab boots **two unmodified instances of the pinned historical ACE Connect Lite Node application** and drives its observed VRS-classification path against the Baudot iTRS CTE.

Source pin:

```text
mitrefccace/aceconnectlite
da74e6450193be1456ce2cdf65dd5ffdf0e92f1e
```

At that commit, `server.js` builds `GET /vrsverify/?vrsnum=<number>`, treats `message === "success"` as a VRS classification, chooses the Asterisk context `outbound-CA`, and then submits an AMI `Originate`. A failed classification leaves the context as `from-phones`. The source `config.json_TEMPLATE` exposes the `vrscheck.url` and `vrscheck.port` seams used by the lab.

## Topology

```text
ACE Connect Lite A                       ACE Connect Lite B
real server.js :8831                     real server.js :8832
       |                                        |
       | /vrsverify/                            | /vrsverify/
       v                                        v
Baudot adapter A :8801                  Baudot adapter B :8802
       \                                        /
        \                                      /
                    iTRS CTE :8800
                         |
                  directory/query state

ACE A --AMI--> stub :5038            ACE B --AMI--> stub :5039
             \                         /
              deterministic evidence
```

The two ACE processes share the same pinned source tree but run from separate working directories with separate `config.json` files, ports, login identities, and AMI peers.

## What is executed

The runner uses ACE's real `/login` handler to establish each synthetic agent/channel mapping. It then connects through the version of `socket.io-client` installed with the pinned ACE source and emits ACE's real `outbound-call` event.

The proof requires the actual ACE application to:

1. call the dedicated Baudot `/vrsverify/` adapter;
2. receive the CTE-backed classification;
3. choose the expected Asterisk context; and
4. submit an AMI `Originate` action observed by the corresponding synthetic AMI peer.

The matrix is:

```text
ACE A -> 2025550103 -> success -> outbound-CA
ACE B -> 2025550101 -> success -> outbound-CA
ACE A -> 2025550105 -> failure -> from-phones
```

Expected final line:

```text
Dual ACE Connect Lite runtime lab: 5/5 PASS
```

Run it with a checkout of the exact ACE source pin:

```bash
bash scripts/run-dual-ace-runtime-lab.sh /path/to/aceconnectlite
```

CI checks out that upstream repository at the exact commit automatically.

## Evidence boundary

This is stronger than a compatibility-response mock because the historical ACE application itself decides the AMI context. It is still **not a completed VRS call**.

The AMI endpoints are deterministic Baudot stubs. They accept and record ACE actions but do not implement Asterisk dialplan, SIP transport, media, RTT, interpreter queues, emergency calling, or provider production behavior.

The resulting claim is intentionally narrow:

> The pinned ACE Connect Lite application can consume the Baudot CTE-backed `/vrsverify/` classification seam and select its historical outbound call context deterministically for two isolated synthetic provider instances.

The next layer is to replace the AMI stub with a controlled Asterisk fixture and observe the resulting SIP transaction through Baudot's existing signaling/evidence stack.
