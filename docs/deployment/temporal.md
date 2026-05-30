# Temporal Stability Monitoring

The temporal monitor runs a convergence pass every 4 hours and appends results to a JSONL log. It detects drift in a model's constitutional topology over time.

## Setup

```bash
# Store credentials (never commit this file)
cat > ~/.tel_temporal.env << EOF
TEL_ENDPOINT=https://your-endpoint.services.ai.azure.com
TEL_MODEL=gpt-4o
TEL_API_KEY=your-key
EOF
chmod 600 ~/.tel_temporal.env
```

## Systemd Timer (Recommended)

```bash
sudo cp tel-temporal.service tel-temporal.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tel-temporal.timer
```

The timer fires every 4 hours. Each run appends one record to `~/temporal_log.jsonl`.

## Manual Run

```bash
python3 tel_deploy/temporal_run.py
```

## View Stability Report

```bash
python3 tel_deploy/temporal_summary.py --log ~/temporal_log.jsonl
```

Output shows:
- C-seed stability across runs
- B-fingerprint consistency
- Any topology shifts (flagged as drift events)
- Run timestamps and pass counts

## What It Detects

A topology shift between runs indicates that the model's constitutional surface has changed — due to a model update, redeployment, or fine-tuning change on the provider side. The temporal log is the audit trail.

Constitutional drift tolerance: **γ = 0.17** (Policy 007). Changes within tolerance are logged but not flagged. Changes beyond tolerance are flagged as isolation candidates.
