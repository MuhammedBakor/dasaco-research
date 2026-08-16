# DA-SACO Reproducibility Guide

## Documentation

Complete project guide:

    README.md

Verified environment and versions:

    docs/reproducibility/environment-and-versions.txt

## Primary Workload

- Planned UEs: 100
- Inter-arrival time: 50 ms
- PDU sessions: 0
- Timeout: 240 seconds
- Subscriber range: imsi-208930000018001 to
  imsi-208930000018100
- Required valid repetitions: 3

## Clean Baseline

Before each run, the runner restarts Open5GLoS, AMF, AUSF, UDM, UDR,
and PCF.

The workload starts only after verifying:

- one desired and Ready replica per managed function;
- one expected NRF registration per eligible SBI function;
- the running AMF is discovered by Open5GLoS;
- zero active gNB connections;
- Open5GLoS is not draining;
- admission mode is OPEN;
- Controller phase is IDLE;
- subscriber SQN and transient contexts are reset;
- no old experiment process remains.

## Primary Command

From the repository root:

    cd dasaco-controller
    sudo -v
    sudo -n true || exit 1
    ./run_clean_dasaco_once.sh

## Qualification Rules

Experimental validity and service performance are separate.

A run is classified as:

    VALID_RUN

when all planned UE attempts start, no defined infrastructure failure
occurs, no unknown RAN UE context error occurs, evidence collection
completes, protocol-safe recovery completes, and the system returns to
a stable final state.

A valid run may have:

    full_completion=false
    perfect_service=false

This preserves genuine outcomes such as 99 or 98 completed UEs.

A run is classified as:

    INVALID_INFRASTRUCTURE_RUN

when an external or infrastructure condition invalidates the
measurement. Such runs are excluded from statistical aggregation and
retained only for diagnosis.

## Capacity-Use Verification

A new replica is classified as:

    CAPACITY_USE_VERIFIED

when genuine traffic is observed on the replica.

A new replica is classified as:

    CAPACITY_IDLE

when the replica becomes Ready but does not process genuine
UE-associated traffic.

Kubernetes Ready state alone is not proof of useful capacity.

## Primary Results

Accepted runs:

    results/final-dasaco/final-accepted-runs/

Aggregate summary:

    results/final-dasaco/dasaco-final-three-repetition-summary.txt

Recorded results:

- repetition 1: 100 of 100 completed;
- repetition 2: 99 of 100 completed;
- repetition 3: 98 of 100 completed;
- aggregate: 297 of 300 completed;
- mean completion: 99.00%;
- sample standard deviation: 1.00 percentage point;
- AMF Status Indications: 0;
- unknown RAN UE errors: 0.

Primary Git tag:

    dasaco-final-3run-v1

## Supplementary Experiments

Rapid 150-UE experiment:

    dasaco-controller/run_dasaco_stress_150ue.sh

Sustained 150-UE experiment:

    dasaco-controller/run_dasaco_sustained_150ue.sh

Rapid experiment summary:

    results/exploratory-stress-dasaco/150ue-scalability-summary.txt

Sustained experiment summary:

    results/exploratory-sustained-dasaco/150ue-500ms-capacity-use-summary.txt

The sustained experiment verified that the new AMF processed 70 unique
UEs and the new UDR processed requests associated with 53 unique UEs.

Supplementary Git tag:

    dasaco-supplementary-scalability-v1

The supplementary experiments must not be included in the primary
three-run statistical comparison.

## Evidence Per Run

A complete run can contain:

- summary and qualification;
- PacketRusher log;
- Controller actions and final state;
- monitoring and localizer evidence;
- per-replica traffic CSV and text summary;
- replica timeline;
- Pod logs;
- environment, version, configuration, and checksum evidence.

## Stable Final State

A recovered run must return to:

- one desired and Ready replica per managed function;
- admission mode OPEN;
- zero active gNB connections;
- Open5GLoS not draining;
- Controller phase IDLE;
- no pending Controller action;
- no recorded Controller error.
