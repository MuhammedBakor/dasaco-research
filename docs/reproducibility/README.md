# DA-SACO Reproducibility Guide

## Experimental Objective

Evaluate dependency-aware and protocol-aware automatic scaling for a
free5GC control plane under a 100-UE registration workload.

## Tested Functions

- Open5GLoS
- AMF
- AUSF
- UDM
- UDR
- PCF

## Workload

- Simulated UEs: 100
- Inter-arrival time: 50 ms
- PDU sessions: disabled
- PacketRusher timeout: 240 seconds
- Initial replicas: one per scalable function
- Maximum replicas: five per function
- Controller interval: five seconds

## Clean-State Requirement

Every final repetition begins with a restart of Open5GLoS, AMF, AUSF,
UDM, UDR, and PCF to remove in-memory UE, NGAP, discovery, and
connection state.

A run must not begin until:

- Every scalable Deployment is 1/1 Ready.
- AMF, AUSF, UDM, UDR, and PCF each have one NRF registration.
- Open5GLoS has discovered the running AMF.
- Open5GLoS reports zero active gNB associations.
- Open5GLoS is not draining.
- Admission mode is OPEN.
- The DA-SACO Controller state is IDLE.
- Subscriber SQN and transient registration contexts are reset.

## Run Command

From the repository root:

    cd dasaco-controller
    sudo -v
    ./run_clean_dasaco_once.sh

## Final Acceptance Criteria

A repetition is accepted only when:

- Started equals 100.
- Registration Accepts equal 100.
- Configuration Update Completes equal 100.
- Registration Rejects equal 0.
- AMF Status Indications equal 0.
- Unknown RAN UE errors equal 0.
- All functions return to one desired and one Ready replica.
- Admission returns to OPEN.
- Controller returns to IDLE.

## Repetition Requirement

Three independent accepted repetitions are required before DA-SACO is
included in the final comparison.

Diagnostic runs are excluded from statistical aggregation.

## Evidence Stored Per Accepted Run

- PacketRusher log
- Monitoring snapshots
- Localizer decisions
- Controller actions
- Final Controller state
- Summary and qualification
