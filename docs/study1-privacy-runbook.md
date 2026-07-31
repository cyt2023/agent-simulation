# Study 1 Privacy Runbook

## Data Separation

- Analysis exports must not include direct identifiers.
- Identity vault data is governed separately from Study 1 analysis data.
- Raw media access requires the researcher `read_raw_media` scope.
- Retention purge requires dry-run manifest confirmation and a second approval.

## Access Rules

- Participants can only access materials for their signed role.
- P cannot access delegated Proxy meeting audio or transcript while isolated.
- X receives only P-authorized material and Proxy configuration, never T1/T2
  private material.
- Transcript and recording replay access must be phase- and scope-authorized.

## Withdrawal and Purge

1. Create a retention dry run.
2. Review affected analysis rows, media rows, and tombstone output.
3. Confirm the manifest checksum.
4. Execute the purge through A so B receives the authorized purge command.
5. Preserve non-identifying tombstones for audit.

## Incident Handling

Record a coded incident for privacy or permission failures. Stop the session if
private material, raw media, or delegated meeting content crosses a forbidden
role boundary.
