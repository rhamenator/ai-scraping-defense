# Release Artifacts

This document defines the release artifact policy for the Python-based AI Scraping Defense stack.

The default release image and Python environment do not bundle the optional
`llama-cpp-python` native dependency. Operators that need the `llamacpp://`
adapter can install [requirements-local-llm.txt](../requirements-local-llm.txt)
on top of the base environment.

## Registry

Tagged releases publish container images to GitHub Container Registry:

```text
ghcr.io/<owner>/ai-scraping-defense
```

The release workflow is implemented in [release-images.yml](../.github/workflows/release-images.yml) and runs on Git tags that match `v*`.

## Tagging Policy

For a stable release tag such as `v1.2.3`, the workflow publishes:

- `ghcr.io/<owner>/ai-scraping-defense:v1.2.3`
- `ghcr.io/<owner>/ai-scraping-defense:1.2.3`
- `ghcr.io/<owner>/ai-scraping-defense:1.2`
- `ghcr.io/<owner>/ai-scraping-defense:latest`

For a prerelease tag such as `v1.2.3-rc.1`, the workflow publishes only:

- `ghcr.io/<owner>/ai-scraping-defense:v1.2.3-rc.1`
- `ghcr.io/<owner>/ai-scraping-defense:1.2.3-rc.1`

This keeps prereleases from mutating `latest` or the rolling minor tag.

## Release Metadata

Each tagged build publishes:

- an OCI image in GHCR
- OCI labels for source repository, revision, and version
- a Sigstore keyless signature over the pushed image digest
- a GitHub build-provenance attestation pushed to the registry
- a BuildKit SBOM attestation from the image build step

## Verification

Verify GitHub provenance:

```bash
gh attestation verify \
  oci://ghcr.io/<owner>/ai-scraping-defense:v1.2.3 \
  --repo <owner>/ai-scraping-defense
```

Verify the Sigstore keyless signature for a released digest:

```bash
cosign verify \
  ghcr.io/<owner>/ai-scraping-defense@sha256:<digest> \
  --certificate-identity https://github.com/<owner>/ai-scraping-defense/.github/workflows/release-images.yml@refs/tags/v1.2.3 \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

## Upgrade Path

Recommended operator behavior:

1. Track release notes and changelog entries for the target version.
2. Pull and verify the released image by digest, not just by mutable tag.
3. For production, pin deployments to the verified digest.
4. Roll forward within the same major version unless release notes explicitly state otherwise.
5. Keep the previous verified digest available for rollback.
