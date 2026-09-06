#!/usr/bin/env python3
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = json.loads((ROOT / "testkit/fund/synthetic-trs-fund-five-year-v1.json").read_text())
D = Decimal
CENT = D("0.01")
PUBLIC = {
    "FY2022-23": ({"vrsEmergent":"5.29","ipctsCa":"1.30","ipctsAsr":"1.30","ipRelay":"1.9576"},
                  {"kind":"legacy-dual-factor","nonIpctsFactor":"0.01125","ipctsFactor":"0.00653"}),
    "FY2023-24": ({"vrsEmergent":"7.77","ipctsCa":"1.30","ipctsAsr":"1.30","ipRelay":"2.048"},
                  {"kind":"form499-line-split","nonInternetFactor":"0.00025","internetFactor":"0.01615"}),
    "FY2024-25": ({"vrsEmergent":"8.06","ipctsCa":"1.30","ipctsAsr":"1.30","ipRelay":"2.1252"},
                  {"kind":"form499-line-split","nonInternetFactor":"0.00024","internetFactor":"0.01952"}),
    "FY2025-26": ({"vrsEmergent":"8.33","ipctsCa":"1.40","ipctsAsr":"1.05","ipRelay":"2.197"},
                  {"kind":"form499-line-split","nonInternetFactor":"0.00025","internetFactor":"0.02086"}),
    "FY2026-27": ({"vrsEmergent":"8.61","ipctsCa":"1.45","ipctsAsr":"0.95","ipRelay":"2.271"},
                  {"kind":"form499-line-split","nonInternetFactor":"0.00021","internetFactor":"0.02276"}),
}

def q(v): return D(v).quantize(CENT, rounding=ROUND_HALF_UP)
def req(ok, msg):
    if not ok: raise AssertionError(msg)

def months(start):
    y, m = map(int, start.split("-")); out = []
    for _ in range(12):
        out.append(f"{y:04d}-{m:02d}"); m += 1
        if m == 13: y, m = y + 1, 1
    return out

def rates(year, month):
    out = dict(year["rates"])
    for t in year.get("rateTransitions", []):
        if month >= t["effectiveMonth"]: out.update(t["updates"])
    return out

def assess(c, year, i, growth):
    scale = growth ** i
    internet = q(D(c["internetBase"]) * scale)
    noninternet = q(D(c["nonInternetBase"]) * scale)
    f = year["contributionFormula"]
    if f["kind"] == "legacy-dual-factor":
        return q(noninternet * D(f["nonIpctsFactor"]) + internet * D(f["ipctsFactor"]))
    req(f["nonInternetLine"] == "514b" and f["internetLine"] == "514a", "Form 499 line mapping drift")
    return q(noninternet * D(f["nonInternetFactor"]) + internet * D(f["internetFactor"]))

def schedule(total):
    x = q(total / 12); return [x] * 11 + [total - x * 11]

def activity(year, mult):
    b = year["providerMonthlyVolumeBase"]; f = float(mult)
    return {
        "vrs": round(b["vrs"] * f),
        "ca": round(b["ipctsCa"] * f),
        "asr": round(b["ipctsAsr"] * f),
        "relay": round(b["ipRelay"] * f),
    }

def claims(year, month, a):
    r = rates(year, month)
    return {
        "provider-vrs": q(D(a["vrs"]) * D(r["vrsEmergent"])),
        "provider-ipcts": q(D(a["ca"]) * D(r["ipctsCa"]) + D(a["asr"]) * D(r["ipctsAsr"])),
        "provider-iprelay": q(D(a["relay"]) * D(r["ipRelay"])),
    }

def check_public(year):
    er, ef = PUBLIC[year["id"]]
    req(year["rates"] == er, f"{year['id']} rate snapshot drift")
    for k, v in ef.items(): req(year["contributionFormula"].get(k) == v, f"{year['id']} formula drift {k}")
    f = year["contributionFormula"]
    if f["kind"] == "legacy-dual-factor": req(f["publicLineMappingClaimed"] is False, "2022-23 invented line mapping")
    else: req(f["nonInternetLine"] == "514b" and f["internetLine"] == "514a", f"{year['id']} line mapping drift")

def main():
    req(DOC["schema"] == "baudot.synthetic-trs-fund-five-year@1", "schema drift")
    req(DOC["synthetic"] is True and DOC["status"] == "experimental", "synthetic/experimental boundary drift")
    req(DOC["period"]["programYears"] == 5 and DOC["period"]["months"] == 60, "period drift")
    b = DOC["authorityBoundary"]
    req(b["providerVolumesAreSynthetic"] and b["contributorRevenueBasesAreSynthetic"], "synthetic data boundary missing")
    req(not b["administratorPrivateImplementationModeled"] and not b["productionAccountingModeled"] and not b["productionPaymentRailModeled"], "production/private claim leaked")
    req(b["fineractRole"] == "reference financial-state implementation only", "Fineract authority drift")

    years = DOC["programYears"]; req([y["id"] for y in years] == list(PUBLIC), "program-year order drift")
    for y in years: check_public(y)
    t = years[2]["rateTransitions"]
    req(t == [{"effectiveMonth":"2024-11","updates":{"ipctsCa":"1.35","ipctsAsr":"1.17"},"publicBasis":"Rolka Loube provider rate table"}], "2024 IP CTS transition drift")

    anomalies = [a["type"] for y in years for a in y["anomalies"]]
    req(anomalies == ["contributor-collection-delay","duplicate-claim-replay","claim-adjustment","provider-payment-failure","provider-overpayment-recovery"], "anomaly progression drift")
    req(len(DOC["contributors"]) == 5 and len(DOC["providers"]) == 3, "actor count drift")
    mults = [D(x) for x in DOC["generation"]["monthlySeasonalMultipliers"]]
    req(len(mults) == 12 and all(x > 0 for x in mults), "seasonal multipliers drift")
    growth = D(DOC["generation"]["contributorAnnualGrowthFactor"]); req(growth == D("1.03"), "growth drift")

    cash = D(DOC["openingBalances"]["cash"]); opening_cash = cash
    ap = D(DOC["openingBalances"]["providerPayable"])
    ar = D(DOC["openingBalances"]["contributorReceivable"])
    rr = D(DOC["openingBalances"]["recoveryReceivable"])
    delayed = defaultdict(list); deferred = defaultdict(list); recover = defaultdict(list)
    for y in years:
        for a in y["anomalies"]:
            if a["type"] == "provider-overpayment-recovery":
                recover[a["recoverMonth"]].append(D(a["overpaymentAmount"]))

    observed = {}; five = defaultdict(lambda: D("0.00")); checkpoints = {}
    for yi, y in enumerate(years):
        totals = defaultdict(lambda: D("0.00"))
        opening = {"cash":cash,"providerPayable":ap,"contributorReceivable":ar,"recoveryReceivable":rr}
        sched = {}
        for c in DOC["contributors"]:
            amt = assess(c, y, yi, growth)
            req(amt == D(y["contributionAssessmentByContributor"][c["id"]]), f"{y['id']} assessment drift {c['id']}")
            sched[c["id"]] = schedule(amt)

        for mi, month in enumerate(months(y["start"])):
            mt = defaultdict(lambda: D("0.00"))
            for _, amount in delayed.pop(month, []):
                cash += amount; ar -= amount; totals["contributionCashReceived"] += amount
            for amount in recover.pop(month, []):
                cash += amount; rr -= amount; totals["recoveriesReceived"] += amount

            for c in DOC["contributors"]:
                amount = sched[c["id"]][mi]; ar += amount; totals["contributionAssessed"] += amount
                a = next((x for x in y["anomalies"] if x["type"]=="contributor-collection-delay" and x["month"]==month and x["contributorId"]==c["id"]), None)
                if a: delayed[a["settleMonth"]].append((c["id"], amount))
                else: cash += amount; ar -= amount; totals["contributionCashReceived"] += amount

            for _, amount in deferred.pop(month, []):
                cash -= amount; ap -= amount; totals["providerCashPaid"] += amount

            a = activity(y, mults[mi])
            req(all(v > 0 for v in a.values()), f"{month} nonpositive synthetic volume")
            for pid, amount in claims(y, month, a).items():
                ap += amount; totals["reimbursementApproved"] += amount
                fail = next((x for x in y["anomalies"] if x["type"]=="provider-payment-failure" and x["month"]==month and x["providerId"]==pid), None)
                if fail: deferred[fail["retryMonth"]].append((pid, amount))
                else: cash -= amount; ap -= amount; totals["providerCashPaid"] += amount

            for x in y["anomalies"]:
                if x["month"] != month: continue
                if x["type"] == "claim-adjustment":
                    amount = D(x["amount"]); ap += amount
                    totals["reimbursementAdjustments"] += amount; totals["reimbursementApproved"] += amount
                    mt["reimbursementAdjustment"] += amount
                    cash -= amount; ap -= amount; totals["providerCashPaid"] += amount
                elif x["type"] == "duplicate-claim-replay":
                    amount = D(x["financialEffect"]); totals["duplicateReplayFinancialEffect"] += amount; mt["duplicateReplayFinancialEffect"] += amount
                elif x["type"] == "provider-overpayment-recovery":
                    amount = D(x["overpaymentAmount"]); cash -= amount; rr += amount
                    totals["providerCashPaid"] += amount; totals["overpaymentsCreated"] += amount

            checkpoints[month] = {"ar":q(ar),"ap":q(ap),"rr":q(rr),"adj":q(mt["reimbursementAdjustment"]),
                                  "dup":q(mt["duplicateReplayFinancialEffect"]),"ca":rates(y,month)["ipctsCa"],"asr":rates(y,month)["ipctsAsr"]}

        close = {"cash":q(cash),"providerPayable":q(ap),"contributorReceivable":q(ar),"recoveryReceivable":q(rr)}
        row = {k:q(v) for k,v in totals.items()}
        row["openingBalances"] = {k:q(v) for k,v in opening.items()}; row["closingBalances"] = close
        observed[y["id"]] = row
        for k,v in totals.items(): five[k] += v

    req(not delayed and not deferred and not recover, "deferred state remains after five years")
    exp = DOC["expected"]["programYears"]
    for yid, row in observed.items():
        for k,v in row.items():
            if isinstance(v, dict):
                for bk,bv in v.items(): req(bv == D(exp[yid][k][bk]), f"{yid} {k}.{bk} drift")
            else: req(v == D(exp[yid].get(k,"0.00")), f"{yid} {k} drift")

    req(checkpoints["2022-10"]["ar"] > 0 and checkpoints["2022-11"]["ar"] == 0, "contributor delay/recovery checkpoint failed")
    req(checkpoints["2024-03"]["dup"] == 0, "duplicate replay changed state")
    req(checkpoints["2024-11"]["ca"] == "1.35" and checkpoints["2024-11"]["asr"] == "1.17", "2024 rate transition missing")
    req(checkpoints["2024-12"]["adj"] == D("8888.00"), "adjustment checkpoint failed")
    req(checkpoints["2026-04"]["ap"] > 0 and checkpoints["2026-05"]["ap"] == 0, "payment retry checkpoint failed")
    req(checkpoints["2026-11"]["rr"] == D("12500.00") and checkpoints["2027-01"]["rr"] == 0, "recovery checkpoint failed")

    ef = DOC["expected"]["fiveYear"]
    for k,v in five.items(): req(q(v) == D(ef.get(k,"0.00")), f"five-year {k} drift")
    req(q(cash) == D(ef["closingBalances"]["cash"]), "closing cash drift")
    req(q(ap) == q(ar) == q(rr) == D("0.00"), "five-year close not reconciled")
    req(q(cash) == q(opening_cash + five["contributionCashReceived"] + five["recoveriesReceived"] - five["providerCashPaid"]), "cash roll-forward mismatch")

    print("synthetic TRS Fund five-year corpus: PASS")
    print("program years=5 monthly cycles=60 contributors=5 providers=3")
    print(f"contribution assessed=${q(five['contributionAssessed']):,.2f}")
    print(f"reimbursement approved=${q(five['reimbursementApproved']):,.2f}")
    print(f"ending synthetic cash=${q(cash):,.2f}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
