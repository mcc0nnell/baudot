# Baudot repository convergence plan

Baudot now has enough independently useful proving lanes that repository structure matters as much as adding another experiment. This document defines a convergence order for open work so `main` becomes the canonical description of the system rather than a lagging subset of parallel branches.

The goal is not to flatten every experiment into one runtime. The goal is to preserve the project's strongest invariant while making the dependency graph understandable:

```text
observation != stronger claim
```

More concretely:

```text
connected != usable
negotiated != ready
routed != authorized
ledgered != eligible
implementation agreement != conformance
```

## Canonical planes

Baudot should converge around six planes. Each plane has a narrow authority and may be tested independently.

```text
                           BAUDOT

  semantics          execution          routing / identity
  ----------         ---------          ------------------
  T.140              JAIN SIP           Tilden handoff
  RFC 4103/2198      PJSIP              iTRS CTE
  legacy TTY/V.18    Elixip             provider fixtures
        |                |                    |
        +----------------+--------------------+
                         |
                  evidence / reduction
                         |
              Wiretap / preserved artifacts
                         |
        +----------------+--------------------+
        |                                     |
 application federation                  fund plane
 Teams / Zoom / WebRTC               public fund model
 ACE Omni bridge                     synthetic claims
                                     contributions
                                     Apache Fineract
                         |
                  governed control
                 Juneau / Camel
```

No plane gains another plane's authority merely because the components are composed.

## Merge rule

A branch should land on `main` when it meets all four conditions:

1. its authority boundary is explicit;
2. its executable claims are no stronger than the evidence it preserves;
3. it does not introduce a second canonical contract for a concept already represented elsewhere; and
4. its base reflects the current canonical dependency chain.

This means green CI is necessary but not sufficient. Duplicate or stale architecture should be reconciled before merge.

## Wave 1 — independent main-based slices

These branches are conceptually independent and should be the easiest path to make `main` representative of the current project.

- **#50 — GitHub Pages scaffold.** Human-readable projection only; repository evidence remains authoritative.
- **#58 — public VRS interoperability contract.** Source-bound public research plus executable clean-room matrix.
- **#64 — SIPp hostile signaling.** External stimulus generator; never a verdict authority.
- **#66 — Teams / Zoom application ingest.** Source-observation normalization only.
- **#67 — governed control-plane ADR.** Juneau/Camel boundary with Tilden/Baudot authority preserved.
- **#72 — public TRS Fund + contributor + Fineract ledger model.** Public calibration and synthetic accounting contract.

After #67 lands, **#68** can follow as the Apache capability decomposition stacked on that ADR.

These merges increase architectural visibility without forcing the larger stacked runtime chains to move first.

## Wave 2 — Tilden convergence

The Tilden work has one clear canonical direction but currently includes sibling branches that overlap in purpose.

Preferred chain:

```text
#53  selection handoff documentation
  -> #54 live selected-route signaling
      -> #55 selected-route native RTT readiness
          -> #60 selected-provider REFER/RTT handoff
              -> #65 explicit reselection recovery
```

### #57 review

#57 and #55 both extend #54 toward RTT readiness. #55 is the stronger canonical candidate because it binds the selected endpoint to the already-qualified PJSIP native-media path and preserves the independent Baudot readiness token.

Before merging both, review #57 for any unique generic-route behavior not already represented by #55. If no unique invariant remains, preserve useful tests or documentation and retire the duplicate branch rather than keeping two canonical `TILDEN-HANDOFF-002` definitions.

## Wave 3 — iTRS / provider runtime chain

Preferred chain:

```text
#40  deterministic iTRS mock + JAIN handoff
  -> #59 database-shaped iTRS CTE
      -> #69 two live ACE Connect Lite instances
          -> #70 real Asterisk + JAIN signaling
```

This chain is valuable because every step replaces one synthetic boundary with an independently observable implementation boundary while keeping the route authority separate from provider behavior.

Do not collapse these facts:

```text
ACE /vrsverify/ classification
!= iTRS logical route
!= Asterisk dial decision
!= SIP dialog establishment
!= RTT/media readiness
```

## Wave 4 — Fund runtime convergence

There are now two complementary Fund branches:

- **#72** — public calibration, contributor assessment rules, and a neutral Fineract journal contract from `main`;
- **#71** — synthetic reimbursement/payment lifecycle stacked on the ACE/Asterisk runtime chain.

They should not land as two competing Fund models.

Canonical direction:

```text
#72 public policy/calibration contract
       |
       v
live/pinned Fineract execution adapter
       |
       v
#71 runtime call-evidence composition
```

After #72 lands, narrow or rebase #71 so its unique responsibility is runtime composition and real Fineract execution evidence. Shared account vocabulary, claim lifecycle semantics, and authority boundaries should come from the public Fund contract rather than being duplicated.

Target end-to-end relationship:

```text
call evidence
!= compensable event
!= approved claim
!= payable
!= settlement
!= reconciliation

Form 499-A revenue
!= contribution factor
!= assessment
!= receipt
!= reconciliation
```

## Wave 5 — implementation and media expansion

These can land independently after conflict review because they extend the implementation ensemble rather than redefining core semantics:

- **#48 — legacy TTY/V.18 + G.711/Wiretap lane**;
- **#52 — PJSIP RFC 2198 characterization**;
- **#56 — Linphone native RTT candidate**;
- **#61 — ACE Kamailio/rtpengine donor model**.

The key merge criterion is that characterization remains characterization. An implementation limitation or success must not silently become a normative Baudot rule.

## Wave 6 — federation and evidence-plane branches

The federation branches contain strong work but need base cleanup because several later proofs were developed on stacked feature branches.

Relevant open branches include:

- **#35 — federated call assembly**;
- **#39 — RFC 2198 recovery across controlled/routed loss**;
- **#44 -> #45 — ACE Omni evidence bridge**.

Before landing, rebase these onto a `main` that already contains the qualified PJSIP/readiness primitives they depend on. Preserve the existing evidence split:

```text
source emitted
!= network delivered
!= gateway observed
!= browser received
!= semantic recovery
!= terminal readiness
```

The Omni bridge should remain an evidence transport boundary. Omni ledger acceptance must not promote a Baudot scenario's conformance status.

## Wave 7 — build/reactor migration

**#41** intentionally introduced a parallel Maven parent/reactor without replacing the active root build. That caution remains correct.

Merge the provider/runtime chains first, then decide the final module migration with the actual stable tree in front of us.

Target shape:

```text
baudot-parent
  +-- core/reference
  +-- testkit
  +-- interop adapters
  +-- iTRS CTE
  +-- provider SPI
  +-- provider fixtures
  +-- fund adapters
  `-- site
```

The module graph should describe proven repository boundaries; it should not force boundaries prematurely.

## PR hygiene after each wave

After a canonical branch lands:

1. retarget dependent PRs to the new `main` or newly canonical base;
2. remove commits already present through the merged base;
3. close only genuinely superseded branches after unique evidence/tests are preserved;
4. make PR titles describe the remaining delta rather than the branch's historical journey; and
5. verify that Pages/status projections read machine-readable repository state rather than maintaining a second truth registry.

## What should not happen

Do not create a single giant merge branch that absorbs every open PR. That would erase the evidence history and make regressions impossible to attribute.

Do not let the project become an application framework whose abstractions are more important than the experiments. The executable evidence chain remains the center.

Do not merge duplicate semantic identifiers merely because both branches are green. Resolve ownership first.

Do not promote historical ACE, Rolka Loube public reports, PJSIP, Elixip, Linphone, SIPp, OpenMeetings, Fineract, Wiretap, Teams, Zoom, Camel, Juneau, or any other external implementation into normative Baudot truth.

## Definition of converged

The repository is converged when a new reader can start from `main` and answer, without reading open PR history:

1. What behavior does Baudot own?
2. Which external implementations are under test?
3. Which component owns each routing, accounting, signaling, media, and verdict decision?
4. What evidence promotes a scenario from planned to runnable to stronger status?
5. Which public-source models calibrate synthetic test environments?
6. How can one reproduce the important proving lanes locally or in CI?

At that point, new experiments can branch from a stable laboratory instead of also having to reconstruct the laboratory's architecture.