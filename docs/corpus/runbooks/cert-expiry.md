# Runbook: TLS Certificate Expiry

**Service:** edge / ingress · **Severity when firing:** P1 if serving cert, P2 if internal · **Owning team:** Platform

Fires when a TLS certificate is within 7 days of expiry, or when clients start
seeing `certificate has expired`. Related alert: `CertExpiringSoon`
(`probe_ssl_earliest_cert_expiry - time() < 7*86400`). An expired public cert is
a full outage for every HTTPS client.

## Triage
1. Which cert and where: `echo | openssl s_client -connect host:443 -servername host 2>/dev/null | openssl x509 -noout -dates -subject`.
2. Is it the edge/ingress cert (user-facing → P1) or an internal service-to-service cert (→ P2)?
3. How is it issued: cert-manager (ACME/Let's Encrypt), a corporate CA, or a manually-uploaded cert? The renewal path differs.

## Mitigation
- **cert-manager (ACME).** Check the `Certificate`/`CertificateRequest`/`Order` objects: `kubectl describe certificate <name>`. A stuck renewal is usually a failing ACME HTTP-01/DNS-01 challenge (blocked path, wrong DNS record). Fix the challenge; cert-manager retries automatically.
- **Manual cert.** Reissue from the CA and roll out the new cert + key to the ingress secret, then reload the ingress. Keep the private key out of logs and tickets.
- **Clock skew.** A node with a wrong clock can report a valid cert as expired (or vice versa). Verify NTP if the cert dates look fine but clients still fail.

## Prevention
- The `CertExpiringSoon` alert must page while there is still time to renew (7 days), not at expiry. If it fired late, fix the alert threshold as a follow-up.

## Escalation
If a user-facing cert is expired or will expire within the hour and automated renewal is stuck, page Platform on-call immediately — this is a P1.
