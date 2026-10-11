# Changelog

Release notes are not written by hand in this file. Pushing a `v*` tag runs
[`.github/workflows/release.yml`](.github/workflows/release.yml), which creates a
GitHub Release and lets GitHub generate the notes from the pull requests and
commits between the previous tag and the new one. Read them on the repository's
[Releases page](https://github.com/Hexaware-HnI/velocityai/releases).

- A tag with a suffix such as `v1.2.0-rc.1` is published as a pre-release.
- A `v*` tag also triggers the production Deploy workflow. The release and the
  deploy run independently: the release does not wait for the deploy and does not
  report its outcome.
- Who may create a `v*` tag is governed by the tag ruleset in
  `.github/rulesets/tags.json`.
- No history from before the first generated release is reconstructed here.

CI/CD status, pins and the rollback runbook: [`.github/CI_STATUS.md`](.github/CI_STATUS.md).
