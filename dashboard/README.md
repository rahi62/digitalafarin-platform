# WP Agent Dashboard

Private multi-site administration UI for `wp-agent.digitalafarin.ir`.

## Security model

- Single administrator session in phase 1.
- WordPress Application Passwords are encrypted at rest with AES-256-GCM.
- A connection must pass `users/me?context=edit` before it can be saved.
- The UI never returns or renders a stored credential.
- Every state-changing site operation creates an audit record.

## Local development

```bash
cp .env.example .env.local
npm install
npm run dev
```

The PostgreSQL schema is created idempotently on the first authenticated dashboard request.
