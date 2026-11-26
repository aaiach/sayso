# sayso relay

Keyless and stateless: serves the phone app and forwards encrypted messages between your broker
and your paired phone through short-lived mailboxes. It holds no keys and can't read or approve
anything (see `../PROTOCOL.html`). Host your own: it needs HTTPS (phones require it for the app,
its crypto and notifications) and no configuration.

- **Railway:** new service from this repo, root directory `relay/` (it builds the Dockerfile).
  Then generate a domain, and put `https://<your-domain>` in your broker's `.env` as `BROKER_RELAY_URL`.
- **Docker anywhere:** `docker build -t sayso-relay relay/ && docker run -p 8080:8080 sayso-relay`
  behind any HTTPS proxy.
- **Locally (tests):** `uvicorn relay.app:app --port 8787` from the repo root.
