#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path
PJSIP_IDENTITY="pjsip/pjproject-2.17@5a457451fa2712ba18e12b01738e8ff3af2b26fd"; TYPE="baudot.celix.lifecycle-observation"
def load(path):
    out=[]
    for raw in path.read_text(encoding="utf-8").splitlines():
        try: item=json.loads(raw.strip())
        except json.JSONDecodeError: continue
        if item.get("type")==TYPE: out.append(item)
    if not out: raise AssertionError("no lifecycle observations")
    return out
def one(obs,phase,cap,verdict):
    m=[i for i in obs if i.get("phase")==phase and i.get("capability")==cap and i.get("verdict")==verdict]
    if len(m)!=1: raise AssertionError(f"expected one {phase}/{cap}/{verdict}, saw {len(m)}")
    return m[0]
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--log",type=Path,required=True); a=ap.parse_args(); obs=load(a.log)
    if len(obs)!=9: raise AssertionError(f"expected nine lifecycle observations, saw {len(obs)}")
    active_p=one(obs,"active","SignalingParser","PJSIP_PARSE_ACCEPTED"); active_a=one(obs,"active","CallAdmission","PJSIP_UAS_TEXT_PROFILE_ADMITTED"); one(obs,"active","AuthorityBoundary","NOT_MODELED")
    stopped_p=one(obs,"stopped","SignalingParser","CAPABILITY_MISSING"); stopped_a=one(obs,"stopped","CallAdmission","CAPABILITY_MISSING"); one(obs,"stopped","AuthorityBoundary","NOT_MODELED")
    restored_p=one(obs,"restored","SignalingParser","PJSIP_PARSE_ACCEPTED"); restored_a=one(obs,"restored","CallAdmission","PJSIP_UAS_TEXT_PROFILE_ADMITTED"); one(obs,"restored","AuthorityBoundary","NOT_MODELED")
    for label,item in (("active parser",active_p),("active admission",active_a),("restored parser",restored_p),("restored admission",restored_a)):
        if PJSIP_IDENTITY not in item.get("detail",""): raise AssertionError(f"{label}: missing PJSIP identity")
    for item in (stopped_p,stopped_a):
        if "stopped" not in item.get("detail",""): raise AssertionError("stopped observation lost cause")
    forbidden={"AUTHORIZED","COMPLIANT","FCC_CERTIFIED","FUND_ELIGIBLE","PROTOCOL_CONFORMANT"}
    if any(i.get("verdict") in forbidden for i in obs): raise AssertionError("lifecycle leaked authority/conformance verdict")
    print(json.dumps({"schema":"baudot.celix.pjsip-lifecycle-summary.v2","pjsipImplementation":PJSIP_IDENTITY,"parserSequence":["PJSIP_PARSE_ACCEPTED","CAPABILITY_MISSING","PJSIP_PARSE_ACCEPTED"],"admissionSequence":["PJSIP_UAS_TEXT_PROFILE_ADMITTED","CAPABILITY_MISSING","PJSIP_UAS_TEXT_PROFILE_ADMITTED"],"authorizationClaimed":False,"protocolConformanceClaimed":False,"trsBusinessAuthorityClaimed":False,"observations":len(obs)},indent=2,sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
