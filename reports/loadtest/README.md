# Locust raw results

- `p5-20260728-baseline_*`: 5 users, 1 user/s spawn rate, 30 seconds, zero-error baseline.
- `p5-20260728_*`: initial 10-user overload run that exposed the Nginx rate-limit status issue.
- `p5-20260728-rate-limit_*`: post-fix 10-user, 10-second follow-up after returning 429 for rate limits.

Credentials and authorization headers are not written to these CSV files. The interpreted results and machine configuration are recorded in `docs/test-report.md`.
