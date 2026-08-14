# DA-SACO Pre-Protected Coordinated Profile

## Scope

This profile evaluates coordinated admission protection and usable AMF
capacity. Strong Protection and two Ready AMF replicas were established
before each workload. Open5GLoS discovery of both AMFs was verified
before PacketRusher started.

This profile does not represent successful mid-burst dynamic adaptation.

## Official runs

| Run | Completed | Success | P50 ms | P95 ms | P99 ms | AMF assignment |
|---|---:|---:|---:|---:|---:|---:|
| P3 | 98/100 | 98% | 3011.590 | 8357.542 | 9623.992 | 13 / 87 |
| P4 | 100/100 | 100% | 3032.033 | 5889.325 | 6955.214 | 58 / 42 |
| P5 | 100/100 | 100% | 2550.320 | 5416.894 | 8297.754 | 61 / 39 |

## Aggregate results

- Completed registrations: 298 of 300
- Mean completion ratio: 99.333%
- Mean P50: 2864.648 ms
- Mean P95: 6554.587 ms
- Mean P99: 8292.320 ms
- Failed InitialUEMessage sends: 0
- Broken-pipe errors: 0
- Both AMF replicas received traffic in every run

## Run validity

P3, P4, and P5 are valid performance runs.

P3 includes one UDM SYSTEM_FAILURE and one Registration Reject. This is
retained as a real system outcome rather than excluded.

P1 is excluded as a reaction-time calibration because protection was
activated after all registrations passed admission.

P2 is excluded as a dynamic-switch diagnostic because switching policy
during the active gNB burst coincided with repeated broken-pipe failures.

## Interpretation

The coordinated profile achieved 298 of 300 completed registrations.
Readiness and Open5GLoS discovery checks ensured that both AMF replicas
were usable before workload injection. The experiments support claims
about pre-protected coordination, but not full mid-burst adaptation.
