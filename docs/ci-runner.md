# Local GitHub Actions runner

The repository uses the dedicated Windows runner `SHENMIREN001-feishu` with
labels `self-hosted`, `Windows`, `X64`, and `feishu-overlay`.

On 2026-11-16, GitHub-hosted jobs were rejected before starting because the
account's included compute allowance was exhausted and its paid Actions budget
was zero. The owner chose local execution without adding a payment method or
increasing that budget.

## Operation

- Install directory: `C:\actions-runner\feishu-message-overlay`.
- Windows service:
  `actions.runner.biquanshenmiren188-feishu-message-overlay.SHENMIREN001-feishu`.
- The service starts automatically (delayed start), recovers after failure, and
  runs as `NT AUTHORITY\NETWORK SERVICE`, not Administrator.
- Keep the computer powered on and connected to the internet. Jobs queue while
  it is offline. One runner executes one job at a time.
- Python 3.12.10 is preinstalled in the runner's tool cache. `setup-python`
  reuses it without requiring the service to install software system-wide.
- PowerShell, Git, and GitHub CLI are installed in the runner's own `tools`
  directory. Its service PATH is separate from the interactive user's tools.
- .NET and Node are managed by setup actions; Python test dependencies use a
  temporary virtual environment. npm keeps its local cache; CI does not upload
  it to GitHub cache storage.
- Successful Windows packages are uploaded only when explicitly requested via
  workflow dispatch. Diagnostic artifacts retain the existing three-day policy.

## Trust and triggers

This runner is registered only to this private repository. Windows and Python
jobs reject pull requests from other repositories, including forks. Checkout
does not persist its GitHub token. Do not give untrusted contributors repository
write access or change this repository to public while using a personal machine
as its runner.

Feature branches run through pull-request checks, and `main` runs after pushes.
The same feature push no longer starts both push and PR builds. New changes
cancel obsolete automatic runs; manual runs are kept separate. Windows builds
have a 30-minute timeout, and cloud-reader checks have a 15-minute timeout.
Documentation-only changes do not start the Windows workflow on `main`.

Both verification workflows support manual dispatch. Release tags use the same
runner, but release publication still requires the existing version-tag flow.
Older branches must incorporate the updated workflow files before their checks
will use this runner.

## Troubleshooting

Check the runner's online/busy state in the repository's **Settings > Actions >
Runners**, or inspect its Windows service. Runner diagnostics are in `_diag`
under the install directory. For test failures, read the workflow job log before
changing application code. Do not expose runner credential files or diagnostic
logs containing credentials.

Do not fix quota errors by disabling tests or reporting skipped builds as passed.
Keep the Actions paid budget at zero unless the owner explicitly chooses paid
GitHub-hosted execution in the future.
