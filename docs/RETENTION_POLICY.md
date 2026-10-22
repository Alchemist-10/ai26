# Sakshi retention windows

Sakshi applies these windows in its background maintenance task, including when
camera inference is paused. The defaults are deployment settings, not a legal
retention recommendation. Set the environment values before startup; increasing
a window cannot restore data that an earlier cleanup has already removed.

| Data | Default | Setting and accepted range | Expiry behavior |
| --- | --- | --- | --- |
| Observations, passages, candidate links, alerts, and source-frame/crop derivatives | 7 days | `AI26_OBSERVATION_RETENTION_DAYS`, 7–365 days | Old rows and unleased derivatives are removed. Evidence-report leases protect referenced derivatives until the report expires. |
| Live aggregate traffic buckets | 90 days | `AI26_TRAFFIC_RETENTION_DAYS`, 7–365 days | Old quarter-hour aggregate buckets are removed; replay inputs are not recorded as live traffic. |
| Evidence reports and their artifact leases | 24 hours | `AI26_REPORT_RETENTION_HOURS`, 1–720 hours | Expired report rows and leases are removed; raw source clips are not included in this window. |
| Authentication sessions | 8 hours | Fixed in `backend/auth.py` | Expired sessions are removed by maintenance. |
| Failed login-attempt records | 15 minutes | Fixed in `backend/repository.py` | Old attempt records are removed. |
| Hash-chained audit ledger | Indefinite | No setting | Rows are not pruned because deleting part of the chain would break verification. Retention reduction requires an independently signed archive format and approved policy. |
| Managed footage releases, upload receipts, and staging files | Separate operator policy | See `docs/SOURCE_IMPORT.md` | Dry-run-first cleanup requires an explicit retention period and confirmation. |

The observation setting also governs how long unleased image derivatives remain
readable, keeping retrieval and cleanup behavior aligned. A live evidence report
can extend protection for its referenced derivatives through its own expiry.
The Compose deployment passes all three configurable windows into the API
container; local deployments read the same variables directly.

Tests cover invalid bounds, configured report expiry, configured traffic-bucket
pruning, and retrieval of image derivatives inside an extended observation
window. These tests prove the configured behavior, not the deployment operator's
choice of retention period. Audit-ledger pruning and independently anchored
off-host archives remain unimplemented.
