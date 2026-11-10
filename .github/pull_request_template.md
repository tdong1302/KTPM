## Scope

- Linked task/issue:
- What this pull request changes:
- What is intentionally out of scope:

## Impact

- [ ] No architectural impact
- [ ] Architectural impact is described below and documentation is updated
- [ ] No database migration
- [ ] Migration added and verified from an empty disposable PostgreSQL database
- [ ] No API contract change
- [ ] API contract change is documented

Architectural, migration or API notes:

## Security and data safety

- [ ] Authentication/authorization impact reviewed
- [ ] Logs and errors contain no secrets, JWTs, passwords or complete connection URLs
- [ ] No `.env`, credential or generated local artifact is committed
- [ ] Destructive tests target only a disposable database

## Verification

Commands run and results:

```text
Paste reproducible commands and concise results here.
```

- [ ] Ruff check passed
- [ ] Ruff format check passed
- [ ] Unit/integration tests passed
- [ ] Coverage remains at or above 95%
- [ ] Alembic has exactly one head, when applicable
- [ ] PostgreSQL concurrency tests passed with zero relevant skips, when applicable
- [ ] Docker Compose/container smoke passed, when applicable

## Documentation and evidence

- [ ] Relevant API/architecture/testing/setup documentation updated
- [ ] Frontend screenshot or demo evidence attached, when applicable
- [ ] Responsive/accessibility behavior checked, when applicable

## Reviewer notes

Risks, follow-up work or specific areas requiring review:

