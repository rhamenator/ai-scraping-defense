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

## Installer Bundles

Tagged releases also publish versioned installer bundles for operators that want
to download a release artifact instead of cloning the repository first.

Because the Linux, Windows, and macOS installer entrypoints orchestrate Docker
Compose from the repository root, these are full repository bundles rather than
native `.exe`, `.msi`, or `.pkg` installers.

Each tagged release publishes:

- `ai-scraping-defense-<version>-bundle.zip`
- `ai-scraping-defense-<version>-bundle.zip.sha256`
- `ai-scraping-defense-<version>-bundle.tar.gz`
- `ai-scraping-defense-<version>-bundle.tar.gz.sha256`

Use the `.zip` bundle on Windows and the `.tar.gz` bundle on Linux or macOS.
After extraction, run the documented platform entrypoint from the extracted
repository root:

- Windows: `./scripts/windows/install.ps1`
- macOS: `./scripts/macos/install.zsh`
- Linux: `./scripts/linux/install.sh`

The bundle workflow manages only its own installer-bundle section in the GitHub
Release body. Manual release notes outside that managed section are preserved on
reruns.

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

Verify a release bundle checksum on Linux or macOS:

```bash
sha256sum -c ai-scraping-defense-<version>-bundle.tar.gz.sha256
```

Verify a release bundle checksum on Windows:

```powershell
$expected = (Get-Content .\ai-scraping-defense-<version>-bundle.zip.sha256).Split(' ')[0]
$actual = (Get-FileHash .\ai-scraping-defense-<version>-bundle.zip -Algorithm SHA256).Hash.ToLowerInvariant()
if ($expected -ne $actual) { throw 'Checksum mismatch.' }
```

## Upgrade Path

Recommended operator behavior:

1. Track release notes and changelog entries for the target version.
2. Pull and verify the released image by digest, not just by mutable tag.
3. For production, pin deployments to the verified digest.
4. Roll forward within the same major version unless release notes explicitly state otherwise.
5. Keep the previous verified digest available for rollback.

## Third-Party Image Pins

The repository pins floating third-party images in `docker-compose.yaml` and
builder images in `Dockerfile` to immutable digests. Refresh those pins only as
an intentional change after reviewing the upstream release notes and rerunning
the repo's compose, security-scan, and release validations.
