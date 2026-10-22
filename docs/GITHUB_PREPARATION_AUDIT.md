# GitHub preparation audit

Audit date: 2026-10-23. Intended target: private `Campus-Sentinel` repository.
No staging, commits, repository creation, publication or push was performed.

## Changes reviewed

- Both flagged mail usernames occur in documentation configuration examples,
  not contact sections. They now use the explicitly labeled `info@example.com`
  placeholder authorized by the project owner.
- Replaced shipped credential defaults in backend configuration and the
  environment template with explicit placeholders. Production documentation
  uses placeholders, too. The private `.env` was left unchanged.
- Removed database/Redis password fallbacks that matched local credentials
  from Compose, Alembic example configuration and native provisioning.
  Compose requires explicitly supplied database, Redis and Grafana passwords.
- `ai-engine/` is the single Git source tree. The existing Windows junction at
  `backend/ai_engine` is preserved and ignored. `scripts/link_ai_engine.py`
  provides safe setup on fresh clones and refuses to replace conflicting files.
- Python Dockerfiles, Compose and CI use a repository-root build context and
  copy the canonical AI source directly. Root, backend and frontend Docker
  ignore rules exclude secrets, student records, spreadsheets, databases,
  environments, dependencies, downloaded/trained weights and generated output.
- CI image publication and production deployment require explicit repository
  variable opt-in. No workflows were run remotely.
- `REPOSITORY_SETUP.md` documents native import setup, model sources, paths,
  container provisioning and private-weight handling. No models were downloaded.

## Validation

- Existing alias, fresh alias creation, repeated setup and conflicting-directory
  refusal passed. Temporary alias tests did not alter the project source.
- Development and combined production Compose configuration validate with
  synthetic validation credentials. Resolved secret-bearing output was not shown.
- The current local environment lacks `GRAFANA_PASSWORD`; supply it privately
  before using the updated Compose configuration.
- Backend unit tests: **344 passed**, with `DEBUG=false` set only for the test
  process. Initial collection failed because the existing local DEBUG value
  could not be parsed as a boolean; private configuration was not changed.
- No eligible file exceeds 100 MiB. Eligible files are UTF-8 text.
- Signature scanning and comparison against nonempty local credential values
  found no remaining matches in the intended Git files. Common test fixtures
  and documentation credential examples remain; scanning is not a proof that
  every possible secret or personal detail is absent.
- A diagnostic accidentally displayed one password default during preparation.
  Treat it as exposed and rotate it privately before deployment. Its value is
  not reproduced in this report, and matching source defaults were removed.

## Intended contents and remaining actions

`INTENDED_GIT_FILES.txt` records the complete eligible file list for review;
it is not a staged-file list. Source, migrations, tests, documentation,
dependency lockfiles, CI and required configuration remain eligible.
Student images, QR records, spreadsheets, local environments, caches, logs,
databases and weights remain local and excluded.

Before deployment, configure real credentials privately and replace all
`REPLACE_WITH_` placeholders. The backend placeholders are configuration
examples, not deployable credentials. Model volumes and runtime bind mounts
must be provisioned separately; Docker ignore rules do not filter bind mounts.

No Docker image build or end-to-end deployment was performed. Build-context
and Dockerfile changes were reviewed statically and Compose was validated;
image construction still requires a separate check before deployment.

The next Git operation requires project-owner approval. Recheck status and the
sensitive-file scan immediately before staging. Review the staged diff before
any commit; creating or pushing a repository requires separate authorization.

## Agent junction staging correction

Confirmed `agents/` as canonical: `backend/agents` resolves to that directory,
all 13 aliased files match, and Dockerfiles copy the root source directly.
Removed only those 13 duplicate entries from the index, preserved both source
and junction, and ignored the alias in Git and Docker build contexts. The local
import setup script now prepares both aliases on fresh clones. The intended
manifest contains 289 files. This correction stages the reviewed changes only;
no commit or publication was performed.
