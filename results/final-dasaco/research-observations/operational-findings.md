# DA-SACO Operational Findings

## NRF Scale-Down and Discovery Continuity

### Observation

NRF successfully scaled from one to two replicas. Both replicas became
Kubernetes Ready, returned identical NF discovery results, and served
requests through the Kubernetes Service.

Measured NRF request distribution:

- NRF replica 1: 22 requests
- NRF replica 2: 22 requests

Ten UE registrations completed successfully while two NRF replicas were
active:

- Registration Accepts: 10
- Configuration Update Completes: 10
- Registration Rejects: 0

### Failure Observed During Direct Scale-Down

After NRF was reduced from two replicas to one:

- The remaining NRF Pod was Kubernetes Ready.
- The shared MongoDB NfProfile collection contained zero profiles.
- NRF discovery returned:
  `{"validityPeriod":100,"nfInstances":null}`

Therefore, Kubernetes readiness did not imply NRF operational
continuity.

### Likely Lifecycle Mechanism

Both NRF replicas used the same MongoDB-backed NF profile store. During
termination or NF-profile lifecycle processing, deletion or expiration
affected the shared registration state.

The surviving NRF Pod remained healthy at the container and HTTP
readiness levels, but could not discover the required network
functions.

### Guarded Recovery

The following recovery sequence restored NRF discovery:

1. Restart AMF.
2. Restart AUSF.
3. Restart UDM.
4. Restart UDR.
5. Restart PCF.
6. Wait until every Deployment is Ready.
7. Restart Open5GLoS after the AMF lifecycle change.
8. Verify the MongoDB NfProfile collection.
9. Query NRF discovery and verify a REGISTERED AMF profile.

After this sequence, MongoDB contained five registered profiles:

- AMF
- AUSF
- PCF
- UDM
- UDR

### DA-SACO Policy Implication

NRF must not use generic Deployment scale-down logic.

Specialized NRF policy:

NRF pressure
→ temporary admission protection
→ NRF scale-out
→ Kubernetes readiness verification
→ direct discovery consistency verification
→ per-replica request-use verification

NRF recovery
→ reduce NRF replicas
→ force controlled NF re-registration
→ restart Open5GLoS if AMF identity changed
→ verify all required NF profiles
→ verify discovery continuity
→ restore admission to OPEN

Recovery must be marked complete only after the functional discovery
checks pass.

### Research Implication

The experiment demonstrates:

`Kubernetes Ready != NRF operational continuity`

A network function can remain Kubernetes Ready while its service-level
state is unusable. DA-SACO therefore requires function-specific
eligibility, readiness, consistency, and recovery guards rather than
treating all 5G Core functions as stateless Deployments.

## Evidence to Collect in Final Parallel DA-SACO Runs

Before automatic recovery and scale-down, each final run must preserve
the logs of every active replica.

Required per-replica evidence:

- AMF: unique UEs, InitialUEMessages, and completed registrations.
- AUSF: HTTP requests and unique SUPIs when available.
- UDM: HTTP requests and unique SUPIs when available.
- UDR: HTTP requests and unique UE identifiers when available.
- PCF: policy requests and unique UE identifiers when available.
- NRF: NFM and discovery requests per replica.
- Open5GLoS: gNB connections, InitialUEMessages, and AMF assignments.

This evidence will demonstrate that newly created replicas carried real
traffic and were not merely Kubernetes Ready.

## Open5GLoS Horizontal Scaling and SCTP Connection Ownership

### Observation

Open5GLoS successfully scaled from one to two replicas. Two independent
PacketRusher gNB workloads created separate SCTP associations, and
Kubernetes distributed one association to each Open5GLoS replica.

Measured per-replica behavior:

- Open5GLoS replica 1: one gNB connection, 10 Initial UE Messages,
  10 successful forwards, and one disconnected-gNB removal.
- Open5GLoS replica 2: one gNB connection, 10 Initial UE Messages,
  10 successful forwards, and one disconnected-gNB removal.
- Total Registration Accepts: 20.
- Total Configuration Update Completes: 20.
- Registration Rejects: 0.
- Broken pipes: 0.

### Operational Constraint

Kubernetes distributes complete SCTP associations between Open5GLoS
replicas. It does not redistribute individual UEs belonging to an
already established gNB association.

Therefore, creating additional Open5GLoS replicas provides useful
capacity only when new gNB SCTP associations are established.

### Scale-Down Constraint

An Open5GLoS replica owns local gNB connections, UE contexts, AMF
bindings, and NGAP identifier mappings. Blind Deployment scale-down
may terminate a Pod that still owns active associations.

Open5GLoS must therefore not use generic automatic scale-down while
active gNB connections exist.

### DA-SACO Policy Implication

Open5GLoS pressure
→ activate temporary admission protection
→ scale out up to the configured maximum
→ verify Kubernetes readiness
→ verify connection to the current AMF set
→ verify that new gNB associations use the added capacity

Open5GLoS recovery
→ stop assigning new connections to the selected replica
→ mark the replica as draining
→ wait until its active gNB count reaches zero
→ reduce the Deployment replica count
→ verify the remaining Open5GLoS endpoint
→ verify AMF discovery and Admission OPEN

### Research Implication

The experiment demonstrates:

`Kubernetes Ready != useful Open5GLoS capacity`

and:

`Replica scale-down safety depends on SCTP connection ownership`

DA-SACO therefore requires protocol-aware usefulness and draining
checks, rather than considering Deployment readiness and replica count
alone.

## MongoDB Protection-Only Validation

DA-SACO correctly classified persistent MongoDB pressure as a
protection-only condition.

Validated behavior:

- Strong admission protection was activated at 15 registrations/s
  with burst capacity 5.
- MongoDB was not scaled blindly.
- MongoDB remained at one desired and one Ready replica.
- Admission was restored to OPEN after recovery.
- The controller returned to IDLE.

Research implication:

MongoDB is treated as a constrained stateful dependency in this
testbed. DA-SACO protects it using temporary admission control rather
than unsafe generic horizontal scaling.

## Dependency-Ordered Recovery Validation

After Open5GLoS completed guarded recovery from five replicas to one,
a registration test initially experienced AUSF and PCF request
timeouts despite all network functions being Kubernetes Ready and
registered in NRF.

Operational recovery was performed from the deepest registration-path
dependency toward the ingress:

1. UDR
2. UDM
3. AUSF
4. PCF
5. AMF
6. Open5GLoS

After dependency-ordered recovery:

- Every required NF was Kubernetes Ready.
- AMF, AUSF, UDM, UDR, and PCF were registered in NRF.
- Open5GLoS discovered the new AMF identity.
- One UE completed registration successfully.
- A subsequent 10-UE wave achieved:
  - Registration Accepts: 10
  - Configuration Update Completes: 10
  - Registration Rejects: 0
- Open5GLoS returned to zero active gNB connections.

Research implication:

`Kubernetes Ready + NRF Registered != dependency-path responsiveness`

Recovery ordering is therefore part of DA-SACO correctness. Admission
must not return to OPEN until dependency-ordered recovery and an
end-to-end registration probe both succeed.

## AUSF Replica-Local Authentication State

During the five-replica integration test, the initial authentication
POST request reached one AUSF replica and created the SUCI-to-SUPI
mapping locally. The subsequent 5G-AKA confirmation PUT request reached
a different AUSF replica, where the mapping did not exist.

Observed result:

- Authentication creation POST: HTTP 201 on one AUSF replica.
- 5G-AKA confirmation PUT: HTTP 400 on another AUSF replica.
- Logged cause: `supiSuciPair does not exist`.
- The UE received the Authentication Request but did not complete
  registration.

Research implication:

`AUSF Ready + NRF Registered != authentication-session continuity`

AUSF horizontal scaling requires request affinity or shared
authentication-session state. DA-SACO must verify complete multi-step
procedure continuity rather than treating successful single-request
distribution as sufficient scaling eligibility.

## Gradual Multi-Function Recovery Policy

DA-SACO uses incremental recovery for every horizontally scalable
function:

5 → 4 → 3 → 2 → 1

After each reduction, the controller verifies the remaining capacity
before continuing.

Verification policy:

- Open5GLoS: mark one selected replica as draining, reject new gNB
  associations on that replica, wait for active gNB connections to
  reach zero, remove the drained replica, and verify AMF connectivity.
- AMF: verify Kubernetes readiness, the expected running Pod count, and
  discovery by Open5GLoS after every decrement.
- AUSF, UDM, UDR, and PCF: verify Kubernetes readiness and the expected
  NRF registration count after every decrement.
- Admission returns to OPEN only after the complete dependency-ordered
  recovery finishes successfully.

Research implication:

Gradual recovery avoids an abrupt capacity withdrawal while residual
traffic from the previous registration wave may still be present. It
also provides a verification boundary after every replica reduction,
making recovery failures observable and limiting their scope.

## First Real Automatic Parallel DA-SACO Run

Run identifier: auto-parallel-20260816-160715

Workload:

- Planned UEs: 100
- Inter-arrival time: 50 ms
- Test timeout: 240 seconds
- Initial replica count: one replica for every scalable function

Registration result:

- UEs started: 100
- Registration Accepts: 97
- Configuration Update Completes: 96
- Registration Rejects: 0

Automatic scaling decision:

- Persistent pressure was detected only on UDM.
- UDM scaled automatically from one to two replicas.
- No unnecessary scaling was performed for Open5GLoS, AMF, AUSF,
  UDR, or PCF.
- Pressure returned to NORMAL after the UDM capacity increment.
- UDM recovered automatically from two replicas to the baseline of one.

Final state:

- Open5GLoS: 1 desired, 1 Ready
- AMF: 1 desired, 1 Ready
- AUSF: 1 desired, 1 Ready
- UDM: 1 desired, 1 Ready
- UDR: 1 desired, 1 Ready
- PCF: 1 desired, 1 Ready
- Controller: IDLE
- Admission: OPEN

Research implication:

The maximum replica value is a safety limit rather than a target.
DA-SACO adds one replica per persistent-pressure decision and stops
scaling when the measured bottleneck is relieved. In this run, a
single UDM increment was sufficient, so scaling to three, four, or five
replicas was neither required nor performed.

The 97 Registration Accepts and 96 Configuration Update Completes also
show that Kubernetes readiness and selective scaling alone do not
guarantee perfect completion for every UE. The incomplete UE paths
must be examined separately and reported transparently.

### Replica-Use Verification

Per-replica UDM evidence showed:

- Original UDM replica:
  - HTTP requests: 1207
  - Unique SUPIs: 100
  - Generate-auth-data occurrences: 171
- Newly created UDM replica:
  - HTTP requests: 0
  - Unique SUPIs: 0
  - Generate-auth-data occurrences: 0

Therefore, the additional UDM replica became Kubernetes Ready and was
registered in NRF, but did not carry observable UE traffic during the
remaining workload interval.

This run must not be interpreted as proof that the UDM scale-out
provided useful additional capacity.

Research implication:

`Scaled + Ready + NRF Registered != traffic-useful capacity`

DA-SACO must verify replica use after every scaling action. Possible
causes include cached NF selection, direct NF-instance addressing,
connection reuse, insufficient workload remaining after readiness, or
service-routing behavior.

### Monitoring Normalization Finding

The monitoring adapter currently aggregates CPU usage across all Pods
of a function. The localizer divides this aggregate by the CPU request
of one replica.

After horizontal scaling, this can overestimate function utilization
because the denominator does not increase with replica count.

The normalized aggregate utilization should be calculated as:

total function CPU usage
/
(replica count × per-replica CPU request)

Per-replica maximum and average utilization should also be preserved
for bottleneck diagnosis.

Until CPU normalization and traffic-use verification are implemented,
this run is classified as an exploratory automatic-control run rather
than a final comparative result.

## Automatic Parallel Run 2: Idle Capacity and In-Wave Recovery

Run 2 produced:

- UEs started: 100
- Registration Accepts: 44
- Configuration Update Completes: 12
- Registration Rejects: 13
- AMF Status Indications: 1

AMF, UDM, and UDR scaled automatically from one to two replicas, but
the newly created replicas received no observable traffic during the
traffic-use verification window.

The controller subsequently initiated recovery while the original gNB
association and UE procedures were still active. AMF recovery produced
an AMF Status Indication and registration disruption.

Research implications:

- Ready capacity created late in a short registration wave may remain
  unused.
- A new AMF replica requires a new gNB association or subsequent traffic
  wave to demonstrate useful capacity.
- Recovery must not remove AMF capacity while active UE procedures or
  dependent gNB associations remain.
- Traffic-use verification should use a post-readiness workload wave.
- AMF Pod-count verification must wait for terminating Pods to disappear
  before declaring recovery failure.

Run 2 is classified as a diagnostic run and is excluded from final
comparative statistics.

## Automatic Parallel Run 3: Useful AMF Capacity and Premature Recovery

The second workload wave verified that the newly created AMF replica
carried real traffic:

- Registration-related events on the new AMF replica: 107
- Unique IMSIs handled by the new AMF replica: 35
- Traffic-use classification: CAPACITY_USE_VERIFIED

However, CPU pressure returned to NORMAL while the gNB association and
UE procedures were still active. The controller reduced AMF capacity
from two replicas to one during the active wave.

Observed workload result:

- UEs started: 100
- Registration Accepts: 14
- Configuration Update Completes: 0
- Registration Rejects: 0
- AMF Status Indications: 1

Research implication:

`Persistent CPU NORMAL != protocol-level recovery safety`

A function can become CPU-normal while active protocol sessions still
depend on the expanded capacity. DA-SACO must therefore combine
resource-level recovery evidence with protocol-level quiescence.

Final recovery guard:

- Block all parallel recovery while any Open5GLoS replica reports an
  active gNB association.
- Begin gradual dependency-ordered recovery only after the total active
  gNB connection count reaches zero.
- Preserve per-replica traffic-use evidence before removing capacity.

Run 3 is classified as a diagnostic run and is excluded from final
comparative statistics.

## Automatic Parallel Run 4: Recovery Guard Validation

Wave 1 completed successfully:

- UEs started: 100
- Registration Accepts: 100
- Configuration Update Completes: 100
- Registration Rejects: 0
- AMF Status Indications: 0

The newly created AMF replica carried real traffic:

- Registration-related events: 113
- Unique IMSIs: 36
- Traffic-use classification: CAPACITY_USE_VERIFIED

The protocol-aware recovery guard blocked recovery repeatedly while
Open5GLoS reported two and then one active gNB associations. Recovery
started only after the active gNB connection count reached zero.

No AMF Status Indication occurred, demonstrating that the active-gNB
recovery guard prevented the premature AMF removal observed in the
previous diagnostic run.

Wave 2 began when AMF desired replicas were two but only one replica
was Ready. Its result was therefore:

- UEs started: 100
- Registration Accepts: 12
- Configuration Update Completes: 3
- Registration Rejects: 0
- AMF Status Indications: 0

Research implication:

`Replica scale requested != capacity ready for a subsequent wave`

A post-scale workload must wait for desired replicas to equal Ready
replicas, completion of service-level verification, and replica-wide
Admission OPEN. Detecting only a desired replica count greater than one
is insufficient.

Run 4 is classified as a diagnostic run and excluded from final
comparative statistics.
