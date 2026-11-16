# Repository maintenance requirements

Owner instruction confirmed on 2026-11-16:

- Use the existing dedicated local Windows GitHub Actions runner for future
  feature updates, verification, and packaging. Keep the paid Actions budget at
  zero. Do not switch back to paid hosted runners without explicit authorization.
- Read [the runner maintenance guide](docs/ci-runner.md) before changing CI.
  Bring older feature branches' workflow configuration up to date before use.
- The production website, cloud BOT receiver, alerts, and phone push services
  must continue running on their cloud server independently of this computer.
  Do not move production services onto the local runner or make their operation
  depend on its uptime.
- Build and test separately from production. For authorized deployments, retain
  the working version and rollback path, preserve bindings and notification
  rules, avoid unnecessary service interruptions, and verify affected website
  and BOT/push paths after the change. Do not send real test notifications unless
  the user has authorized them.
