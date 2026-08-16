# DA-SACO 150-UE Exploratory Stress Test

## Classification

This experiment is a supplementary scalability demonstration. It is
not included in the primary 100-UE baseline comparison or in the
reported three-repetition DA-SACO completion average.

## Purpose

The primary 100-UE repetitions demonstrated successful scale-out and
protocol-safe scale-in. However, newly created AMF replicas remained
traffic-idle because the short registration wave mostly completed
before the added capacity became operationally useful.

The 150-UE experiment evaluates whether a longer registration wave:

- triggers selective coordinated scale-out;
- allows newly created replicas to process UE traffic;
- preserves NGAP and UE-context continuity;
- prevents premature recovery while a gNB remains active;
- returns all managed functions to one replica;
- returns admission control to OPEN;
- returns the DA-SACO Controller to IDLE.

## Workload

- Planned UEs: 150
- Inter-arrival time: 50 ms
- PDU sessions: 0
- PacketRusher limit: 240 seconds
- First subscriber: imsi-208930000018001
- Last subscriber: imsi-208930000018150
- Included in primary comparison: no

## Experimental Validity

The run is experimentally valid when:

- all 150 planned UE attempts start;
- no unknown RAN UE context error occurs;
- no external execution or evidence-collection failure occurs;
- DA-SACO completes protocol-safe recovery;
- all managed functions return to one desired and Ready replica;
- admission returns to OPEN;
- the Controller returns to IDLE.

Full UE completion is measured separately and is not required for
experimental validity.

## Measurements

The run records:

- started and completed UEs;
- Registration Accept and Reject events;
- AMF Status Indications;
- unknown RAN UE errors;
- functions selected for scale-out;
- replica readiness and recovery actions;
- UE identifiers and request events per replica;
- whether newly created replicas processed traffic;
- final Controller and admission state.

## Execution

From the repository root:

    cd dasaco-controller
    sudo -v
    ./run_dasaco_stress_150ue.sh

## Output

Valid or pending runs are stored under:

    results/exploratory-stress-dasaco/

Infrastructure-invalid runs are moved under:

    results/exploratory-stress-dasaco/diagnostic-runs/

## Reporting Rule

The result may be reported as supplementary scalability evidence. It
must not be combined with the three 100-UE repetitions when calculating
the primary comparative completion rate, latency statistics, or other
primary comparison results.
