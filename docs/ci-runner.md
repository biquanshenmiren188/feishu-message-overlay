# GitHub-hosted builds

On 2026-11-23 the owner restored GitHub-hosted execution and kept the paid
Actions budget at zero. Windows builds and version-tagged desktop releases
use `windows-latest`. Cloud reader authorization tests use `ubuntu-latest`.
These workflows can run while the owner's computer is offline.

## Triggers and artifacts

Feature branches run checks on pull requests within this repository. Pushes
to `main` run checks for applicable paths. Both verification workflows also
support manual dispatch. Superseded automatic runs are cancelled. Windows
builds and releases have a 30-minute timeout, and cloud reader checks have
a 15-minute timeout.

Windows builds upload successful packages on explicit request during manual
dispatch. Diagnostic artifacts are retained for three days. Release tags use
the existing publication workflow. Production website, BOT and phone push
services continue to run separately on the cloud server.

## Troubleshooting

For failed jobs, check the run's annotations and step logs. If GitHub blocks
a job before it starts for billing reasons, review the account's included
minutes and billing status. Keep the paid budget at zero unless the owner
explicitly changes it. Update older branches with the current workflows
before running their checks.
