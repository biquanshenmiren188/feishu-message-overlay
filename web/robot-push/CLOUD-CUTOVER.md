# Cloud candidate: not yet activated

The protected configuration endpoint is deployed. The Windows input window sends a user-entered App Secret directly over HTTPS, with a signature from the existing dedicated publisher key. Tools must not read the input, submit it for the user, or copy the existing Feishu credential. Saving only prepares the configuration; it does not open a Feishu connection.

Server storage is a service-owned directory with mode 0700 and a credential file with mode 0600. This is filesystem access protection, not encryption at rest. Configuration and control requests are excluded from nginx access logs and have bounded in-memory request buffers. No credential is part of the source archive.

## Prepared candidate

- `bridge/cloud-main.mjs`: official SDK, joined-group discovery, bot-only gate, synchronous bounded event projection, private IPC only. It does not request message history or new scopes.
- `publisher/cloud_receiver.py`: one owned SDK child, bounded IPC queue, persistent bounded dedup IDs, independent pinned message, bounded ordinary snapshot, reconnect backoff, single state writer.
- `CloudMessageSource.cs`: signed cloud snapshot/control reads, duplicate suppression, original timestamps, separate pin, explicit offline state; no local SDK fallback.
- `CloudMode.cs`: separate nonsecret mode marker. It does not rewrite appearance preferences or existing Feishu credentials.
- `cloud-mode.service.conf`: candidate service limits. These limits and Linux runtime behavior still require activation measurements; local synthetic tests do not prove production throughput.

The current card projection preserves API-provided title, text and HTTP(S) buttons. It does not reproduce image pixels or interactive callbacks. No REST enrichment is awaited in the SDK event acknowledgment path.

## Controlled cutover — not executed by preparation

1. Wait for the input window's nonsecret `configured=true, phase=prepared` receipt. Do not inspect the credential file.
2. Finish candidate tests and stage its Python/Node files and nginx control route. Keep the existing desktop and publisher running until this is ready.
3. Normally exit the desktop, preserve settings, and verify its owned local SDK child has exited. Do not start cloud while a local long connection remains.
4. Use the candidate executable's `--cloud-source-mode on` to persist the mode marker. Do not invoke this against an untested candidate or while the old desktop is running.
5. Install the staged cloud service override and start the one cloud receiver. The cloud service rejects legacy desktop publish requests. Verify fresh membership/connection metadata, then start the desktop candidate through the established shortcut. It must read cloud state and must have no local SDK child.
6. Verify a natural new bot message, card/links, independent pin, duplicate suppression, sound coalescing and unchanged reading/appearance preferences. No test messages are sent to real groups.

Cloud mode requires the existing dedicated desktop signing key for authenticated group metadata and pin controls. Anonymous visitors can only read the public feed; they cannot change global pin selection. Ordinary snapshots loaded at desktop startup retain their old timestamps and must not replay sound alerts.

## Rollback order

Stop the cloud service first; systemd `KillMode=control-group` stops its SDK child. Verify it is stopped before restoring the old publisher-only override. Then run `--cloud-source-mode off` and restore the previous desktop executable. Only then restart the local desktop SDK. Never run cloud and local SDK concurrently. There may be a short cutover gap; no historical replay is promised or requested.

## Validation boundary

Build, synthetic card/filter tests, Python configuration/state tests and desktop cloud-source contract tests have passed. The prepared server Node/SDK installation was verified separately. No real cloud long connection, desktop cloud-mode UI session, cloud pin change or Linux resource ceiling has yet been accepted. The production desktop remains the source until the controlled cutover is explicitly performed.
