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
