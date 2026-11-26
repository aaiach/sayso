# sayso

Let AI agents use your passwords, one-time codes and payment cards **without ever seeing
them**. The agent drives the web page; a separate broker types the secret; you approve each
use, from your phone, with a tap, a PIN or an authenticator code.

> **Alpha.** Filling works on Linux (X11) with Chrome and a terminal approver. Phone approval
> (self-hosted relay + Home Screen web app) and the MCP tool are designed, not built yet.

## How it works

- **Agent points, broker writes.** The agent finds the login, 2FA or checkout step and asks the
  broker to fill it. The broker checks the site (HTTPS, certificate fingerprint, frame rules),
  gets your approval, and types the secret as real keystrokes. The agent only gets a status.
- **Secrets come from where they already are:** Google Password Manager and Google Pay cards
  through Chrome's own autofill, or typed by you at approval time (SMS codes, CVC).
- **Nothing is ever submitted** by the broker. Pressing Log in or Pay stays a separate step.
- **Open by design (Kerckhoffs's principle):** the code, protocol and relay are public;
  security rests only on keys each instance generates for itself.

Phone approval protocol: [`PROTOCOL.html`](PROTOCOL.html).

## Try it (Linux, X11, Chrome)

```bash
sudo apt install xdotool tesseract-ocr
pip install -e .            # playwright, mss, qrcode
cp .env.example .env        # set your browser's CDP endpoint and profile directory
```

Start Chrome with `--remote-debugging-port=9222 --user-data-dir=<profile>`, open a login or
checkout page, then (dry run first, add `--fill` to fill):

```bash
python -m broker.cli google-password --site app.example.com --username user@example.com
python -m broker.cli otp --site bank.example.com --approval validate --fill
```

Approval methods: `--approval validate` (one key), `pin` (`setup-pin` first) or `otp`
(`setup-otp` first, scan the QR with any authenticator app).

## Use it from an agent (MCP)

```bash
claude mcp add --scope user sayso -e PYTHONPATH=$PWD -- python -m broker.mcp_server
```

The agent gets three tools: `sayso_check` (dry run: is the target right?), `sayso_fill` (one
secret into one field, after your approval) and `sayso_status`. It passes where the field is
(a selector, the frame, "the focused field", or split code boxes) and which secret (a Chrome-saved
password or card, or one you type when approving), never a value, never code. Until phone
approval exists, the approval appears in a terminal window on the desktop.

## Security notes

- Never commit `.env` or anything from the state directory; the repo's `.gitignore` covers both.
- Like desktop password managers, sayso runs as your user and doesn't defend against hostile
  code running as you. The terminal approver is a safeguard; phone approval (in progress) moves
  the approval to a separate device.
