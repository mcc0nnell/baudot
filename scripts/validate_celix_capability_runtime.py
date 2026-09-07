#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Iterable
PJSIP_IDENTITY = "pjsip/pjproject-2.17@5a457451fa2712ba18e12b01738e8ff3af2b26fd"

def load_observations(path: Path) -> list[dict[str, str]]:
    observations=[]
    for raw in path.read_text(encoding="utf-8").splitlines():
        line=raw.strip()
        if not (line.startswith("{") and line.endswith("}")): continue
        try: candidate=json.loads(line)
        except json.JSONDecodeError: continue
        if candidate.get("type") == "baudot.celix.observation": observations.append(candidate)
    if not observations: raise AssertionError(f"no Baudot Celix observations found in {path}")
    return observations

def pairs(obs: Iterable[dict[str,str]]) -> set[tuple[str,str]]:
    return {(i["capability"],i["verdict"]) for i in obs}

def require(path, profile, required):
    obs=load_observations(path)
    if {i.get("profile") for i in obs} != {profile}: raise AssertionError(f"{path}: wrong profile")
    missing=required-pairs(obs)
    if missing: raise AssertionError(f"{path}: missing {sorted(missing)}")
    forbidden={"AUTHORIZED","COMPLIANT","FCC_CERTIFIED","FUND_ELIGIBLE","PROTOCOL_CONFORMANT"}
    leaked=[(i.get("capability"),i.get("verdict")) for i in obs if i.get("verdict") in forbidden]
    if leaked: raise AssertionError(f"{path}: leaked authority verdicts {leaked}")
    return obs

def identity(obs, capability, verdict):
    matches=[i for i in obs if i.get("capability")==capability and i.get("verdict")==verdict]
    if len(matches)!=1 or PJSIP_IDENTITY not in matches[0].get("detail",""): raise AssertionError(f"missing PJSIP identity for {capability}/{verdict}")

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--good",type=Path,required=True); ap.add_argument("--fault-injected",type=Path,required=True); ap.add_argument("--missing-rtt",type=Path,required=True); ap.add_argument("--parsed-not-admitted",type=Path,required=True); a=ap.parse_args()
    good=require(a.good,"good",{("SignalingParser","PJSIP_PARSE_ACCEPTED"),("CallAdmission","PJSIP_UAS_TEXT_PROFILE_ADMITTED"),("RealtimeTextTransport","RTT_FIXTURE_ACCEPTED"),("AuthorityBoundary","NOT_MODELED")}); identity(good,"SignalingParser","PJSIP_PARSE_ACCEPTED"); identity(good,"CallAdmission","PJSIP_UAS_TEXT_PROFILE_ADMITTED")
    fault=require(a.fault_injected,"fault-injected",{("SignalingParser","CAPABILITY_MISSING"),("CallAdmission","FAULT_INJECTED_FAIL_OPEN"),("RealtimeTextTransport","FAULT_INJECTED_FAIL_OPEN"),("AuthorityBoundary","NOT_MODELED")})
    missing=require(a.missing_rtt,"missing-rtt",{("SignalingParser","PJSIP_PARSE_ACCEPTED"),("CallAdmission","PJSIP_UAS_TEXT_PROFILE_ADMITTED"),("RealtimeTextTransport","CAPABILITY_MISSING"),("AuthorityBoundary","NOT_MODELED")}); identity(missing,"SignalingParser","PJSIP_PARSE_ACCEPTED"); identity(missing,"CallAdmission","PJSIP_UAS_TEXT_PROFILE_ADMITTED")
    parsed=require(a.parsed_not_admitted,"parsed-not-admitted",{("SignalingParser","PJSIP_PARSE_ACCEPTED"),("CallAdmission","PJSIP_UAS_TEXT_PROFILE_NOT_ADMITTED"),("RealtimeTextTransport","RTT_FIXTURE_ACCEPTED"),("AuthorityBoundary","NOT_MODELED")}); identity(parsed,"SignalingParser","PJSIP_PARSE_ACCEPTED"); identity(parsed,"CallAdmission","PJSIP_UAS_TEXT_PROFILE_NOT_ADMITTED")
    print(json.dumps({"schema":"baudot.celix.capability-runtime-summary.v3","pjsipImplementation":PJSIP_IDENTITY,"parserSuccessImpliesAdmission":False,"authorizationClaimed":False,"protocolConformanceClaimed":False,"profiles":{"good":len(good),"faultInjected":len(fault),"missingRtt":len(missing),"parsedNotAdmitted":len(parsed)}},indent=2,sort_keys=True)); return 0
if __name__ == "__main__": raise SystemExit(main())
