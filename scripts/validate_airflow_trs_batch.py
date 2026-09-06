#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'testkit/business/airflow-trs-batch-v1.json'

def req(n,a,e):
    if a!=e: raise AssertionError(f'{n}: expected {e!r}, got {a!r}')
    print(f'PASS {n}: {a}')

def main():
    x=json.loads(P.read_text())
    req('schema',x['schema'],'baudot.airflow-trs-batch@1')
    req('version',x['airflow']['version'],'3.3.1')
    req('commit',x['airflow']['releaseCommit'],'3adbbe1c58e4532df1964cb7794805e763816ee8')
    for k,v in x['authority'].items(): req(k,v,False)
    req('request owner',x['executionBoundary']['requestTimeIntegrationOwner'],'camel')
    req('batch owner',x['executionBoundary']['scheduledBatchOwner'],'airflow')
    forbidden=set(x['forbiddenTaskOutputs'])
    ids=set()
    for dag in x['dags']:
        did=dag['dagId']
        if did in ids: raise AssertionError(f'duplicate DAG {did}')
        ids.add(did)
        tasks={t['taskId']:t for t in dag['tasks']}
        if len(tasks)!=len(dag['tasks']): raise AssertionError(f'{did}: duplicate task')
        for tid,t in tasks.items():
            missing=set(t['dependsOn'])-set(tasks)
            if missing: raise AssertionError(f'{did}/{tid}: missing deps {missing}')
            if t['output'] in forbidden: raise AssertionError(f'{did}/{tid}: forbidden authority output')
        # acyclic Kahn
        done=set()
        while len(done)<len(tasks):
            ready=[tid for tid,t in tasks.items() if tid not in done and set(t['dependsOn'])<=done]
            if not ready: raise AssertionError(f'{did}: dependency cycle')
            done.update(ready)
        print(f'PASS DAG {did}: {len(tasks)} tasks')
    req('DAG set',ids,{'cdr_daily_projection','fund_daily_reconciliation','equipment_inventory_reconciliation','policy_audit_rollup','fund_monthly_close_candidate','synthetic_five_year_replay'})
    for k,v in x['claimBoundary'].items(): req(k,v,False)
    print('Airflow TRS batch contract: PASS')
if __name__=='__main__': main()
