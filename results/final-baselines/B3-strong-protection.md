# B3 Strong Protection Final Clean Results

## Experimental configuration

- Workload: 100 UEs
- Inter-arrival: 50 ms
- AMF replicas: 1
- Admission rate: 15 registrations/second
- Token-bucket capacity: 5
- Scope: registration only
- Official repetitions: Run 2, Run 3, and Run 4

## Run selection

- Run 2, IMSI 7001-7100: valid
- Run 3, IMSI 8001-8100: valid
- Run 4, IMSI 9001-9100: valid
- Pilot, IMSI 5001-5100: development evidence, excluded
- Run 1, IMSI 6001-6100: invalid infrastructure run, excluded

## Clean results

| Run | Completed | Success | P50 ms | P95 ms | P99 ms | Failed sends | Broken pipes |
|---|---:|---:|---:|---:|---:|---:|---:|
| Run 2 | 100/100 | 100% | 2579.650 | 6551.155 | 9511.778 | 0 | 0 |
| Run 3 | 100/100 | 100% | 3075.054 | 5658.209 | 6339.992 | 0 | 0 |
| Run 4 | 100/100 | 100% | 3182.515 | 4887.054 | 5333.889 | 0 | 0 |

## Aggregate statistics

| Metric | Mean | Sample SD | 95% CI |
|---|---:|---:|---:|
| Success, percent | 100.000 | 0.000 | 100.000 to 100.000 |
| P50, ms | 2945.740 | 321.564 | 2146.867 to 3744.613 |
| P95, ms | 5698.806 | 832.793 | 3629.867 to 7767.745 |
| P99, ms | 7061.886 | 2180.490 | 1644.811 to 12478.962 |

## Acceptance criteria

A clean run requires:

1. Exactly 100 Initial UE Messages received.
2. Exactly 100 successful InitialUEMessage sends.
3. Zero failed InitialUEMessage sends.
4. Zero broken-pipe errors during the observation window.
5. Exactly 100 unique registrations started and completed.
6. Zero automatically executed DA-SACO actions.
7. Final AMF replica count equal to one.

## Interpretation

Strong Protection completed 300 of 300 planned UE registrations across
three clean runs. No InitialUEMessage send failure or broken-pipe event
was observed. Admission protected the registration path but did not add
processing capacity. These results form the final B3 baseline and must
not be presented as complete DA-SACO results.
