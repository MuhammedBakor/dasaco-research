# DA-SACO Active Scaling Readiness Test

Date: 2026-08-14

## Procedure

1. Initial AMF replicas: 1
2. Requested AMF replicas: 2
3. Waited for Kubernetes readiness
4. Verified two Running AMF Pods
5. Verified Open5GLoS discovery of both current AMF Pods
6. Rolled back AMF replicas from 2 to 1
7. Verified final readiness

## Result

- Scale-out 1 to 2: PASS
- Kubernetes readiness 2/2: PASS
- Open5GLoS AMF discovery: PASS
- Rollback 2 to 1: PASS
- Final state 1/1 Ready: PASS

## Qualification

This was a controlled readiness and discovery test without PacketRusher
workload. It validates the active scaling infrastructure but is not a
DA-SACO performance experiment.
