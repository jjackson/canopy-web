# Canopy cloud runner on EC2 (ephemeral)

Stand up a throwaway EC2 box that runs a **`kind=cloud`** canopy runner: it pairs
with canopy-web, claims harness `Turn`s whose target is in its `RUNNER_CAPS`, runs
`claude -p` on the turn's prompt, streams the assistant/tool output into the
`TurnEvent` ledger, and finishes the turn. Spin it **up**, **set it up**, use it,
then **spin it down**.

This is the first real **canopy cloud runner** (Wave 4 SP2b) — the deployed
counterpart to the in-process stub executor. It executes agent/project turns; wiring
chat-`Session` turns to cloud runners (harness `claim_next_turn` routing) is the
follow-on.

## Files
- `up.sh` — launch the instance (Ubuntu 24.04, t3.medium, us-east-1, labs account). Writes `.state.json`.
- `runner.env.example` → copy to `runner.env` and fill in the two secrets.
- `setup.sh` — install the claude CLI on the box, drop the runner, start it as a systemd service (with a claude auth smoke test).
- `down.sh` — terminate the instance + delete the SG/key, remove local state.
- `cloud_runner.py` — the self-contained (stdlib-only) headless runner that runs on the box.

`.state.json`, `runner.env`, and `*.pem` are gitignored — they hold instance ids and secrets.

## Prerequisites
- AWS access to the labs account. **You must log in interactively first** (SSO):
  ```
  aws sso login --profile labs
  ```
- Two secrets for `runner.env`:
  1. **`CANOPY_TOKEN`** — a canopy-web PAT (mint with `/canopy:canopy-web-pat-mint`, or `manage.py create_token`).
  2. **`CLAUDE_CODE_OAUTH_TOKEN`** — copy ace-web's current value, or mint a fresh `ace@dimagi-ai.com` token (`claude setup-token`) and paste it.

## Run
```bash
cd deploy/ec2-runner
aws sso login --profile labs          # you, once
./up.sh                               # launch (~2 min for status-ok)
cp runner.env.example runner.env      # then edit: set CANOPY_TOKEN + CLAUDE_CODE_OAUTH_TOKEN
./setup.sh                            # provision + start; prints a claude smoke-test result
```
Watch it work:
```bash
ssh -i canopy-cloud-runner-key.pem ubuntu@<ip> 'journalctl -u canopy-runner -f'
```

## Prove it end to end
With the runner online, enqueue a turn it can claim (target must be in `RUNNER_CAPS`;
the default caps are `{"projects":["canopy-web"]}`):
```bash
curl -sS -X POST "$CANOPY_BASE_URL/api/harness/turns/" \
  -H "Authorization: Bearer $CANOPY_TOKEN" -H 'Content-Type: application/json' \
  -d '{"project":"canopy-web","workspace":"<your-ws>","origin":"api","prompt":"Reply with a one-line hello.","idempotency_key":"ec2-smoke-1"}'
```
The runner claims it, runs claude, and the turn's events + result land at
`GET /api/harness/turns/<id>` and stream live over the SP1 realtime `turn.{id}` socket.

## Tear down (do this when done — it's billed hourly)
```bash
./down.sh
```

## Notes
- **Cost/security:** ephemeral by design. The box holds the claude token in
  `/etc/canopy-runner.env` (chmod 600); terminating it (`./down.sh`) is the cleanest
  revocation. SSH is locked to your IP at launch.
- **Runner identity:** on first `setup.sh` the runner pairs and caches its id in
  `~/.canopy-cloud-runner.json` on the box, so a restart reuses the same runner row.
- **Deleting the pairing user bricks the runner's tenant** (see the harness docs) —
  this runner is paired by whoever owns `CANOPY_TOKEN`.
