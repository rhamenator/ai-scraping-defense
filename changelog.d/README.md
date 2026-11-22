# Changelog fragments

Each change adds one small file here instead of editing `CHANGELOG.md`, so two pull requests never touch the same
lines and stop conflicting with each other. The release step combines the fragments into `CHANGELOG.md`.

## Adding a fragment

Create `changelog.d/<id>.<category>.md`:

- `<id>` is the issue or pull request number, or a short slug (`1903`, `captcha-follow-up`). Use letters, digits, `-`, `_`.
- `<category>` is one of `security`, `added`, `changed`, `fixed`, `deprecated`, `removed`.
- The file holds the entry as plain Markdown: a sentence or short paragraph. A leading `* ` is optional.

Example, `changelog.d/1903.security.md`:

```
The built-in CAPTCHA no longer leaks its answer (#1903). Challenges are now random ids kept on the server ...
```

More than one entry for the same issue: `1903.security.md`, `1903-2.fixed.md`.

## Checking and releasing

```bash
python scripts/changelog_fragments.py check       # every fragment is named and formatted correctly
python scripts/changelog_fragments.py assemble    # add them under [Unreleased] in CHANGELOG.md and delete them
python scripts/changelog_fragments.py assemble --keep   # same, but leave the files in place
```

`assemble` appends each entry to the matching `### <Category>` heading under `## [Unreleased]` (creating the heading if
it is missing), in file-name order, so the result is the same however the files were added.
