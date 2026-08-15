# Runtime Stability and Dependency Recovery Evidence

## Open5GLoS forwarding correction

A dedicated write mutex was added to serialize NGAP writes toward each
gNB connection.

Validation:

- Go unit tests: PASS
- Go race tests: PASS
- Container image: open5glos:dasaco-serialized-writer
- 20-UE smoke test: 20/20 completed, zero broken pipes
- Ordered 50-UE forwarding test: 50/50 InitialUEMessages delivered,
  zero failed sends, zero broken pipes

## Dependency-chain diagnosis

Kubernetes readiness alone did not guarantee service usability.

Observed failures:

1. Missing UDR registration caused UDM HTTP 500 responses.
2. UDM failures caused AUSF HTTP 500 responses.
3. AUSF failures caused AMF Registration Reject messages.
4. Missing PCF registration stopped registration after authentication.
5. Stale AMF connections caused failed InitialUEMessage forwarding.

The verified dependency recovery order is:

NRF -> UDR -> UDM -> AUSF -> PCF -> AMF -> Open5GLoS

A final single-UE validation completed authentication, security mode,
registration acceptance, and configuration update successfully.

This evidence motivates dependency-aware health verification and guarded
recovery in the DA-SACO closed loop.
