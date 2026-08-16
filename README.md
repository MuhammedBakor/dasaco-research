# DA-SACO

Dependency-Aware Scaling and Admission Control Orchestrator for
cloud-native 5G Core registration workloads.

DA-SACO is an external Kubernetes controller developed and evaluated
using free5GC, Open5GLoS, PacketRusher, Kind, Kubernetes, and Metrics
Server. DA-SACO observes the selected registration path, localizes
persistent pressure, scales eligible network functions, verifies
readiness and traffic use, protects active gNB associations during
recovery, and returns the system to a stable baseline.

## Research Objective

The project investigates whether coordinated and dependency-aware
control can address legitimate registration bursts more safely and
meaningfully than isolated mechanisms such as:

- a static 5G Core;
- CPU-based AMF Horizontal Pod Autoscaling;
- static NGAP-aware AMF distribution through Open5GLoS;
- fixed admission regulation.

The primary registration path studied is:

    UE/gNB -> Open5GLoS -> AMF -> AUSF -> UDM -> UDR

MongoDB provides subscriber and authentication persistence.

## Implemented DA-SACO Capabilities

DA-SACO implements:

- registration-path pressure observation;
- persistent-pressure validation;
- affected-function localization;
- per-function scaling eligibility;
- parallel selective scale-out;
- Kubernetes readiness verification;
- NRF registration verification for SBI functions;
- Open5GLoS discovery verification for AMF replicas;
- NGAP-aware UE distribution;
- UE-to-AMF affinity preservation;
- temporary admission-policy support;
- pending-action protection;
- per-replica traffic collection;
- new-replica traffic-use verification;
- active-gNB recovery protection;
- hysteresis and cooldown;
- coordinated scale-in;
- final-state verification.

A scaling request is not considered operationally successful merely
because Kubernetes accepted the desired replica count. DA-SACO records
one of the following capacity-use outcomes:

    CAPACITY_USE_VERIFIED
    CAPACITY_IDLE

## Primary Evaluation

The primary DA-SACO comparison used:

- 100 planned UEs;
- 50-ms inter-arrival time;
- registration only;
- no PDU-session establishment;
- a 240-second PacketRusher limit;
- one initial replica per managed function;
- three independently prepared clean runs.

Final accepted results:

| Repetition | Started | Completed | Completion | Reject events |
|---|---:|---:|---:|---:|
| 1 | 100 | 100 | 100% | 0 |
| 2 | 100 | 99 | 99% | 2 |
| 3 | 100 | 98 | 98% | 4 |

Aggregate result:

- planned registrations: 300;
- completed registrations: 297;
- mean completion rate: 99.00%;
- sample standard deviation: 1.00 percentage point;
- AMF Status Indications: 0;
- unknown RAN UE errors: 0;
- infrastructure-invalid final repetitions: 0.

A valid run is not required to achieve perfect service. Experimental
validity and measured service performance are separated. A run is
accepted when the planned workload starts, no defined infrastructure
failure occurs, no unknown RAN UE context failure occurs, evidence
collection completes, and the controller restores a safe final state.

## Supplementary Scalability Evidence

Two 150-UE experiments were conducted separately from the primary
comparison.

### Rapid 150-UE Burst

Parameters:

- 150 UEs;
- 50-ms inter-arrival;
- approximate arrival duration: 7.5 seconds.

Result:

- completed UEs: 148;
- completion rate: 98.67%;
- scaled functions: AMF, AUSF, UDM, and UDR;
- all new replicas became Ready;
- new replicas remained traffic-idle;
- final controller state: IDLE.

The rapid arrival wave mostly completed before the newly created
capacity became operationally useful.

### Sustained 150-UE Arrival

Parameters:

- 150 UEs;
- 500-ms inter-arrival;
- approximate arrival duration: 75 seconds.

Result:

- completed UEs: 146;
- completion rate: 97.33%;
- scaled functions: AMF and UDR;
- the new AMF processed 70 unique UEs;
- the new UDR processed requests associated with 53 unique UEs;
- both new replicas received CAPACITY_USE_VERIFIED;
- AMF Status Indications: 0;
- unknown RAN UE errors: 0;
- final controller state: IDLE.

This experiment confirms both scaling execution and operational use of
newly created capacity. The supplementary experiments are not included
in the primary 100-UE comparative statistics.

## Repository Structure

    baselines/
        Baseline-specific resources and configurations.

    cluster/
        Kind cluster configuration.

    configs/packetrusher/
        PacketRusher configurations used by documented experiments.

    dasaco-controller/
        Active DA-SACO controller implementation and experiment runners.

    docs/
        Architecture, experiment, environment, and reproducibility
        documentation.

    monitoring/
        Metrics Server and monitoring resources.

    results/
        Baseline results, accepted DA-SACO results, summaries, and local
        exploratory evidence.

    scripts/experiment/
        Organized copies of the reproducible experiment scripts.

    versions/
        Captured platform and tool-version information.

## Important Files

Primary controller and policy:

    dasaco-controller/parallel_controller_loop.sh
    dasaco-controller/multi_pressure_localizer.py
    dasaco-controller/parallel_action_executor.py
    dasaco-controller/replica_use_verifier.py
    dasaco-controller/action_executor.py
    dasaco-controller/config.yaml

Primary experiment:

    dasaco-controller/run_clean_dasaco_once.sh
    configs/packetrusher/dasaco-100ue.yml

Supplementary experiments:

    dasaco-controller/run_dasaco_stress_150ue.sh
    dasaco-controller/run_dasaco_sustained_150ue.sh
    configs/packetrusher/dasaco-150ue.yml

Evidence tools:

    dasaco-controller/collect_replica_traffic.sh
    dasaco-controller/analyze_replica_traffic.py
    dasaco-controller/capture_experiment_environment.sh

Accepted primary results:

    results/final-dasaco/final-accepted-runs/
    results/final-dasaco/dasaco-final-three-repetition-summary.txt

Supplementary summaries:

    results/exploratory-stress-dasaco/150ue-scalability-summary.txt
    results/exploratory-sustained-dasaco/150ue-500ms-capacity-use-summary.txt

Verified environment manifest:

    docs/reproducibility/environment-and-versions.txt

## Verified Platform Summary

- Ubuntu 22.04.5 LTS;
- Linux kernel 6.8.0-136-generic;
- VMware virtual machine;
- x86_64 architecture;
- 6 allocated vCPUs;
- approximately 10 GiB RAM;
- 100-GB disk;
- VMware NAT networking;
- Kind 0.32.0;
- Kubernetes server 1.36.1;
- Docker 29.7.2;
- Metrics Server 0.9.0;
- free5GC network functions 4.2.3;
- Python 3.10.12;
- Helm 3.21.3.

Exact commits, image versions, and executable hashes are recorded in:

    docs/reproducibility/environment-and-versions.txt

## Prerequisites

The documented environment uses:

- Ubuntu 22.04.5 LTS;
- Docker and containerd;
- Kind and kubectl;
- Helm;
- Python 3.10 or later;
- MongoDB tools available inside the MongoDB Pod;
- PacketRusher built at the recorded commit;
- the adapted Open5GLoS runtime image;
- free5GC v4.2.3 network-function images;
- passwordless cached sudo access during workload execution.

The exact tested versions and source commits are listed in:

    docs/reproducibility/environment-and-versions.txt

## External Source Components

The local experimental environment contains three source trees:

    free5gc/free5gc-helm/
    open5glos/repo/
    packetrusher/repo/

The tested commits are:

    free5GC Helm:
    6f67ec11512e8c6b4eb6b3237f46e71fec5bdda2

    Open5GLoS:
    55994ae45ac66e00722460fad4902a481dac6f68

    PacketRusher:
    194ae987ee2bacfae2cf57d435b475e54076679e

The experimental PacketRusher executable has SHA-256:

    3f5b7adbd9428d5882c45995c1644f0aa73d7489f40edaa6caa37b69289d421b

Private keys, local nested Git metadata, database backups, and raw
supplementary logs are intentionally excluded from the primary
repository.

## Required Runtime State

Before running an experiment, verify that:

- the Kubernetes namespace is `free5gc`;
- Open5GLoS is one desired and one Ready replica;
- AMF is one desired and one Ready replica;
- AUSF is one desired and one Ready replica;
- UDM is one desired and one Ready replica;
- UDR is one desired and one Ready replica;
- PCF is one desired and one Ready replica;
- each eligible SBI function has one NRF registration;
- Open5GLoS has discovered the running AMF;
- Open5GLoS reports zero active gNB connections;
- Open5GLoS is not draining;
- admission mode is OPEN;
- the DA-SACO Controller state is IDLE;
- no previous PacketRusher, collector, or Controller process remains.

A compact process check is:

    pgrep -af \
    'parallel_controller_loop|run_dasaco|packetrusher|collect_replica_traffic' \
    || echo "[OK] No experiment processes are running"

Deployment readiness can be inspected with:

    kubectl get deployment \
    -n free5gc \
    open5glos \
    free5gc-free5gc-amf-amf \
    free5gc-free5gc-ausf-ausf \
    free5gc-free5gc-udm-udm \
    free5gc-free5gc-udr-udr \
    free5gc-free5gc-pcf-pcf \
    -o custom-columns='NAME:.metadata.name,DESIRED:.spec.replicas,READY:.status.readyReplicas'

## Subscriber Requirements

The primary experiment requires 100 consistently provisioned
subscribers:

    imsi-208930000018001
    through
    imsi-208930000018100

The supplementary experiments require 150 consistently provisioned
subscribers:

    imsi-208930000018001
    through
    imsi-208930000018150

The experiment runner resets authentication sequence numbers before the
workload. Provisioning documents must exist consistently in the
relevant authentication, access and mobility, session-management,
selection, and policy collections.

Transient authentication-status and AMF-context documents are not
cloned when adding subscribers.

Local MongoDB backups are stored under:

    backups/

The backup directory and archive files are intentionally excluded from
Git.

## Primary 100-UE Experiment

The primary reproducible runner is:

    dasaco-controller/run_clean_dasaco_once.sh

Run it from the repository root:

    cd dasaco-controller
    sudo -v
    sudo -n true || exit 1
    ./run_clean_dasaco_once.sh

The runner automatically:

1. creates a fresh control-plane state;
2. waits for Kubernetes rollout completion;
3. verifies the clean baseline;
4. captures the environment and versions;
5. cleans current experiment logs;
6. resets the 100 subscriber sequence numbers and transient state;
7. starts the DA-SACO parallel Controller;
8. starts the per-replica traffic collector;
9. runs one 100-UE PacketRusher workload;
10. waits for protocol-safe recovery;
11. copies Controller evidence before traffic analysis;
12. analyzes traffic for every original and new replica;
13. calculates service results and run qualification;
14. stores the final Controller state and evidence.

Results are written below:

    results/final-dasaco/automatic-runs/

Final accepted repetitions are stored below:

    results/final-dasaco/final-accepted-runs/

## Primary Run Qualification

The experiment separates infrastructure validity from service
performance.

A run is classified as:

    VALID_RUN

when the planned workload starts, no defined infrastructure failure
occurs, no unknown RAN UE context error is observed, evidence collection
completes, protocol-safe recovery completes, and the final state is
stable.

A valid run may still have:

    full_completion=false
    perfect_service=false

This preserves genuine service outcomes such as 99 or 98 completed UEs
instead of selectively repeating the experiment until a perfect result
is obtained.

A run is classified as:

    INVALID_INFRASTRUCTURE_RUN

when a defined external or infrastructure condition invalidates the
measurement, such as failure to start the planned workload or unknown
RAN UE context contamination.

Infrastructure-invalid runs are excluded from statistical aggregation
and retained only as diagnostic evidence.

## Rapid 150-UE Experiment

The rapid supplementary runner is:

    dasaco-controller/run_dasaco_stress_150ue.sh

Run it with:

    cd dasaco-controller
    sudo -v
    sudo -n true || exit 1
    ./run_dasaco_stress_150ue.sh

Parameters:

    planned UEs: 150
    inter-arrival time: 50 ms
    approximate arrival duration: 7.5 seconds
    PDU sessions: 0

The result is classified as:

    EXPLORATORY_STRESS_RUN

It is not included in the primary comparison.

## Sustained 150-UE Experiment

The sustained-arrival runner is:

    dasaco-controller/run_dasaco_sustained_150ue.sh

Run it with:

    cd dasaco-controller
    sudo -v
    sudo -n true || exit 1
    ./run_dasaco_sustained_150ue.sh

Parameters:

    planned UEs: 150
    inter-arrival time: 500 ms
    approximate arrival duration: 75 seconds
    PDU sessions: 0

The result is classified as:

    EXPLORATORY_SUSTAINED_RUN

This experiment demonstrated operational use of the new AMF and UDR
replicas. It is supplementary evidence and is not included in the
primary 100-UE comparison.

## Per-Replica Traffic Interpretation

The per-replica analysis records:

- function name;
- Pod name;
- original or new role;
- number of observed unique UE identifiers;
- runtime admission count where applicable;
- request-event count;
- whether the replica was used;
- the evidence source.

Important evidence sources include:

    unique-identifiers-in-pod-log
    request-events-in-pod-log
    runtime-admission-counter
    controller-capacity-idle

A new replica is marked:

    CAPACITY_USE_VERIFIED

when the Controller confirms that the new capacity processed traffic.

A new replica is marked:

    CAPACITY_IDLE

when the replica became operational but no genuine UE-associated use was
observed.

Per-Pod unique UE counts for downstream functions can overlap because
requests associated with one UE may be handled by different replicas.
Downstream per-replica counts must therefore not be summed as additional
UEs.

## Evidence Stored Per Run

A complete run can contain:

    summary.txt
    packetrusher-100ue.log or packetrusher-150ue.log
    controller-actions.jsonl
    controller-state.json
    controller-console.log
    monitoring.jsonl
    parallel-localizer-decisions.jsonl
    per-replica-traffic.csv
    per-replica-traffic.txt
    per-replica-analysis-console.log
    replica-snapshots/
    pod-logs/
    environment/

The environment directory records:

    host.txt
    system-details.txt
    software-versions.txt
    kubernetes.txt
    deployments.txt
    services.txt
    pods.txt
    container-images.tsv
    repository-version.txt
    workload-parameters.txt
    packetrusher-config-used.yml
    packetrusher-config.sha256
    packetrusher-version.txt
    evidence-sha256.txt

## Accepted Result Locations

Primary three-run summary:

    results/final-dasaco/dasaco-final-three-repetition-summary.txt

Primary accepted runs:

    results/final-dasaco/final-accepted-runs/

Rapid 150-UE summary:

    results/exploratory-stress-dasaco/150ue-scalability-summary.txt

Sustained 150-UE capacity-use summary:

    results/exploratory-sustained-dasaco/150ue-500ms-capacity-use-summary.txt

Raw supplementary evidence is retained locally and excluded from normal
Git tracking. Raw evidence may be distributed separately through a
release archive or research-data repository.

## Stable Final State

A successfully recovered experiment returns to:

- one desired and Ready replica for each managed function;
- admission mode OPEN;
- zero active gNB associations;
- Open5GLoS not draining;
- Controller phase IDLE;
- no pending action;
- no recorded Controller error.

Scale-in is blocked while Open5GLoS reports an active gNB association.

## Common Operational Issues

### Shell Prompt Text Was Pasted

Do not paste terminal prompts or command output back into the shell.
Text such as:

    moba@moba-vm:~/dasaco-research$

is not part of a command.

### Secondary Shell Prompt Appears

A prompt containing only:

    >

usually indicates an unclosed quote or unfinished heredoc. Press
Ctrl+C, return to the normal shell prompt, and rerun the complete
command.

### Sudo Is Not Cached

Before PacketRusher execution, run:

    sudo -v
    sudo -n true

The second command must exit successfully.

### Interrupted Control-Plane Restart

If a run is interrupted during rollout, wait for every managed
Deployment to complete rollout and verify the clean baseline before
starting another experiment.

### PacketRusher Timeout Message

The documented runner intentionally uses a 240-second timeout.
Reaching the timeout does not by itself indicate experiment failure.
The runner continues with safe recovery and qualification.

### Event Counts Exceed UE Counts

Registration Accept and Reject values are event counts. Retransmissions
or retries can produce more events than unique UEs. Primary completion
is based on unique completed UEs, not event totals alone.

### New Replica Is Ready but Idle

A Ready Pod is not necessarily useful capacity. Short bursts can finish
before new capacity becomes usable. DA-SACO therefore records both
readiness and actual traffic use.

## Git References

Primary three-run evaluation:

    dasaco-final-3run-v1

Supplementary scalability experiments:

    dasaco-supplementary-scalability-v1

The tags must remain unchanged because they identify the exact code and
documentation states associated with the recorded experiments.

## Security and Data Handling

The repository excludes:

- database backups;
- archive files;
- private keys;
- local kubeconfig files;
- environment files;
- credentials and tokens;
- nested repository metadata;
- large raw supplementary logs.

The subscriber credentials used in the laboratory are test-only values.
Production credentials must never be stored in the repository.

## Current Research Interpretation

The primary evidence supports the following conclusions:

1. DA-SACO completed 297 of 300 planned primary registrations.
2. DA-SACO achieved a 99.00% mean completion rate.
3. No AMF Status Indications were observed in the accepted primary runs.
4. No unknown RAN UE context errors were observed.
5. DA-SACO executed selective and multi-function scale-out.
6. DA-SACO verified Kubernetes, NRF, and Open5GLoS readiness.
7. DA-SACO prevented unsafe recovery during an active gNB association.
8. DA-SACO restored the system to a stable single-replica baseline.
9. The rapid supplementary burst showed successful replica creation but
   no useful new-replica traffic.
10. The sustained supplementary arrival showed that the new AMF
    processed 70 unique UEs and the new UDR processed requests
    associated with 53 unique UEs.

The evidence does not support a claim that DA-SACO outperformed every
baseline in every metric. Latency and resource-cost analysis must be
completed before making an overall performance claim.

## Additional Documentation

Detailed environment and version manifest:

    docs/reproducibility/environment-and-versions.txt

Detailed reproducibility notes:

    docs/reproducibility/README.md

Supplementary experiment protocol:

    docs/experiments/150ue-stress-test.md

## Fresh Repository Setup

Clone the repository with the Open5GLoS submodule:

    git clone --recurse-submodules REPOSITORY_URL
    cd dasaco-research

If the repository was cloned without submodules:

    git submodule update --init --recursive

Fetch the verified free5GC Helm and PacketRusher source revisions:

    ./scripts/setup/fetch_dependencies.sh

The setup script checks out:

- Open5GLoS at the Gitlink recorded by this repository;
- free5GC Helm at commit
  6f67ec11512e8c6b4eb6b3237f46e71fec5bdda2;
- PacketRusher at commit
  194ae987ee2bacfae2cf57d435b475e54076679e.

The PacketRusher executable must then be built according to its upstream
build instructions. The executable used in the recorded experiments had
the following SHA-256:

    3f5b7adbd9428d5882c45995c1644f0aa73d7489f40edaa6caa37b69289d421b

The dependency setup script does not deploy the Kubernetes environment,
provision subscribers, or run experiments. Those operations remain
explicit experimental steps.
