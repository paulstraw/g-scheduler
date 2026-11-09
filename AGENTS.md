# g-scheduler

An agent skill that finds meeting times inside each attendee's Google Calendar working hours, distributed through skills.sh.

## Layout

- `skills/g-scheduler/` is what ships to users: `SKILL.md`, `SETUP.md`, and `scripts/`. Keep only shipped files here.
- `scripts/slots.py` is pure: JSON in, ranked slots out, no network. All time math lives here.
- `scripts/gcal.py` wraps the `gws` CLI (check, gather, invite). It calls `gws` with argument lists, never through a shell.
- `tests/` and `.github/` stay at the repo root so they don't ship.

## Rules

- Python 3.10+, standard library only. `tzdata` is the only optional extra (Windows).
- Scripts must work on macOS, Linux, and Windows.
- No organization-specific details (domains, emails, vault links) and never an OAuth client file in the repo.
- Never write to anyone's working hours. `invite` is the only write, and it always uses `sendUpdates=all`.
- Tests that depend on DST must use zones whose rules are stable (for example, `America/Los_Angeles`), not ones that recently changed (`America/Vancouver`).

## Testing

```bash
python3 -m unittest discover -s tests -v
```

CI runs this on Ubuntu, macOS, and Windows with Python 3.10 and the latest 3.x.

## Commits

Use [Conventional Commits](https://www.conventionalcommits.org/): `type(scope): summary`, with types such as `feat`, `fix`, `docs`, `test`, `ci`, `chore`, and `refactor`. Keep each commit to one logical change.
