# Dependency-Aware Cloud Task Orchestrator

Runnable P77 implementation: DAG validation, concurrent-ready scheduling, retries, dependency blocking, JWT/RBAC, AES-256-GCM encrypted payloads, metrics, audit events, Docker deployment, and load testing.

Run: `cp .env.example .env && docker compose up --build`

Docs: `http://localhost:8000/docs`; metrics: `/metrics`.

Security boundary: ciphertext is stored and returned nowhere in plaintext. The worker decrypts only at execution time using the master key. For strict zero-knowledge E2EE, use a cloud KMS/HSM plus confidential workers; tasks cannot execute without a trusted decrypting boundary.
