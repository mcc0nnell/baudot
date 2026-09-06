#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'testkit/business/skywalking-observability-v1.json'

def req(n,a,e):
    if a!=e: raise AssertionError(f'{n}: expected {e!r}, got {a!r}')
    print(f'PASS {n}: {a}')

def main():
    x=json.loads(P.read_text())
    req('schema',x['schema'],'baudot.skywalking-observability@1')
    req('version',x['skywalking']['version'],'11.0.0')
    req('commit',x['skywalking']['releaseCommit'],'6f1fd78e872f1d380a14f271c26e8d68eb2430fc')
    for k,v in x['authority'].items(): req(k,v,False)
    t=x['telemetry']
    req('raw payload capture',t['rawBusinessPayloadCaptureAllowed'],False)
    req('raw subscriber IDs',t['rawSubscriberIdentifierCaptureAllowed'],False)
    allowed=set(t['allowedCorrelationAttributes']); forbidden=set(t['forbiddenAttributes'])
    if allowed & forbidden: raise AssertionError(f'allowed/forbidden overlap: {allowed & forbidden}')
    required_forbidden={'telephone_number','subscriber_id','raw_request_body','authorization_header','access_token','claim_approved','payment_authorized','compensable','accessibility_ready'}
    if not required_forbidden<=forbidden: raise AssertionError('missing required forbidden telemetry fields')
    trace_ids=set()
    for trace in x['traceProfiles']:
        if trace['id'] in trace_ids: raise AssertionError(f"duplicate trace profile {trace['id']}")
        trace_ids.add(trace['id'])
        if not trace['spans']: raise AssertionError(f"{trace['id']}: no spans")
        req(f"{trace['id']} business claim",trace['terminalBusinessClaim'],None)
    for alarm in x['alarmProfiles']:
        req(f"{alarm['id']} classification",alarm['classification'],'technical-only')
    req('admin public exposure',x['deploymentBoundary']['publicInternetAdminApiAllowed'],False)
    req('admin external protection',x['deploymentBoundary']['adminApiRequiresExternalProtection'],True)
    for k,v in x['claimBoundary'].items(): req(k,v,False)
    print('SkyWalking observability contract: PASS')
if __name__=='__main__': main()
