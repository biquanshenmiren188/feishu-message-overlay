# Repository maintenance requirements

Owner instructions updated on 2026-11-23:

- Run verification and packaging on standard GitHub-hosted runners. Keep
  the paid Actions budget at zero.
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
