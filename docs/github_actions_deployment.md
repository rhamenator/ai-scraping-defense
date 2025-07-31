# GitHub Actions Runner Deployment

The repository provides several workflows that demonstrate how a deployment step
can run entirely in GitHub Actions. The simplest example is located at
`.github/workflows/linux-stack.yml` and launches the stack directly on the
runner. Trigger it manually from the **Actions** tab to observe the stack coming
online and uploading a small deployment artifact to the workflow run.

For a full-stack test, the `iis-deploy.yml` workflow spins up the Windows-based
IIS configuration using the `quick_iis.ps1` helper script. On Linux runners, the
`linux-stack.yml` workflow builds and launches the Docker Compose stack so the
entire system comes online automatically. These pipelines serve as starting
points—you can extend them to push Docker images or apply Kubernetes manifests
once you have the necessary credentials.
