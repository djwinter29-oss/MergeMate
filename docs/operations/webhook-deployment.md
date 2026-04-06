# Webhook Deployment Runbook

## Purpose

This runbook covers a minimal self-hosted deployment for MergeMate in Telegram webhook mode. It assumes one application instance, local SQLite state, and TLS terminated by a reverse proxy in front of the Python process.

## Recommended Topology

- Run MergeMate as a user-space service on a private listen address and port.
- Put Nginx or Caddy in front of it for TLS termination.
- Expose a public `https` URL that matches `telegram.webhook_public_base_url`.
- Keep the Python webhook listener bound to a local or private interface whenever possible.
- Expose the built-in readiness endpoint only on a local or private interface.

## Required Environment

Set at least these environment variables before starting the service:

```bash
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_WEBHOOK_SECRET=...
export OPENAI_API_KEY=...
```

Use a long random value for `TELEGRAM_WEBHOOK_SECRET`. The runtime passes it to Telegram webhook registration and validates it on incoming requests.

## Example MergeMate Config

```yaml
telegram:
  bot_token_env: TELEGRAM_BOT_TOKEN
  mode: webhook
  webhook_listen_host: 127.0.0.1
  webhook_listen_port: 8080
  webhook_public_base_url: https://bot.example.com
  webhook_path: /telegram/webhook
  webhook_secret_token_env: TELEGRAM_WEBHOOK_SECRET
    webhook_healthcheck_enabled: true
    webhook_healthcheck_listen_host: 127.0.0.1
    webhook_healthcheck_listen_port: 8081
    webhook_healthcheck_path: /healthz
```

Operational notes:

- `webhook_public_base_url` must be an absolute URL.
- Non-loopback public URLs must use `https`.
- `webhook_path` must start with `/` and must not include query or fragment components.
- `webhook_healthcheck_path` must start with `/` and must not include query or fragment components.
- The healthcheck listener must not reuse a conflicting webhook bind host and port.
- MergeMate registers the final webhook URL as `<webhook_public_base_url><webhook_path>`.

## Preflight Validation

Validate the config before exposing ingress:

```bash
mergemate validate-config --config ~/.config/mergemate/config.yaml
```

Start the bot only after validation succeeds:

```bash
mergemate run-bot --config ~/.config/mergemate/config.yaml
```

On startup, MergeMate logs the config path, database path, Telegram mode, the resolved public webhook URL when webhook mode is enabled, and whether webhook secret-token validation is active. The secret value itself is not logged.

When `telegram.webhook_healthcheck_enabled` is true, MergeMate also starts a small local readiness server. It returns:

- `503` with `{"status": "starting"}` before the Telegram application finishes startup
- `200` with `{"status": "ready"}` while the webhook runtime is ready to receive traffic
- `503` with `{"status": "stopping"}` during shutdown

## Nginx Example

```nginx
server {
    listen 443 ssl http2;
    server_name bot.example.com;

    ssl_certificate /etc/letsencrypt/live/bot.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/bot.example.com/privkey.pem;

    location /telegram/webhook {
        proxy_pass http://127.0.0.1:8080/telegram/webhook;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;
    }

    location = /healthz {
        proxy_pass http://127.0.0.1:8081/healthz;
        access_log off;
    }
}
```

## Caddy Example

```caddy
bot.example.com {
    reverse_proxy 127.0.0.1:8080

    handle_path /healthz {
        reverse_proxy 127.0.0.1:8081
    }
}
```

If you use a custom webhook path, keep the public route and the MergeMate config aligned.

## User Service Example

Example `systemd --user` unit:

```ini
[Unit]
Description=MergeMate Telegram webhook bot
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=%h/src/MergeMate
Environment=TELEGRAM_BOT_TOKEN=...
Environment=TELEGRAM_WEBHOOK_SECRET=...
Environment=OPENAI_API_KEY=...
ExecStart=%h/src/MergeMate/.venv/bin/mergemate run-bot --config %h/.config/mergemate/config.yaml
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

Prefer `EnvironmentFile=` or a secret manager instead of inline secrets in a real deployment.

## Deployment Checklist

- Create or update the config file with webhook mode enabled.
- Set the required environment variables.
- Run `mergemate validate-config`.
- Confirm the reverse proxy serves the same public hostname and path configured in MergeMate.
- Start the MergeMate service.
- Probe the local readiness endpoint and wait for `{"status": "ready"}` before considering the instance healthy.
- Confirm Telegram can reach the public webhook URL.
- Send a test message and verify you receive the immediate acknowledgement and follow-up planning message.

## Remaining Gaps

This runbook covers the initial self-hosted deployment path. It does not yet add:

- multi-instance webhook coordination
- external queue or database deployment guidance
- automated certificate rotation guidance beyond the reverse-proxy examples