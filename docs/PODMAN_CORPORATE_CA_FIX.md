# Podman: Fixing x509 TLS Certificate Error on Corporate Networks

## Problem

When running `just --justfile justfile.podman run <profile>` (or any `podman pull` /
`podman-compose build`), the build fails immediately with:

```
Error: creating build container: unable to copy from source docker://python:3.13-slim-bookworm:
  initializing source docker://python:3.13-slim-bookworm:
    fetching manifest 3.13-slim-bookworm in docker.io/library/python:
      pinging container registry registry-1.docker.io:
        Get "https://registry-1.docker.io/v2/":
          tls: failed to verify certificate: x509: certificate signed by unknown authority
```

The same error appears for any registry — Docker Hub (`docker.io`), GitHub Container Registry
(`ghcr.io`), or the Microsoft package registry (`packages.microsoft.com`).

### Why This Happens

DHCW's corporate network uses **SSL inspection** (a transparent HTTPS proxy). Every outbound
HTTPS connection is intercepted and re-encrypted using the corporate CA certificate. Podman's
daemon (which is a Go binary running inside a Linux WSL distribution) does not trust this CA
by default, so it rejects every HTTPS connection to external registries.

---

## Environment

| Component | Detail |
|---|---|
| Host OS | Windows |
| Container runtime | Podman for Windows (Podman Desktop or `winget install RedHat.Podman`) |
| Podman backend | `podman-machine-default` — a **Fedora** WSL2 distribution |
| Corporate CA cert location | `ca-certs/corperate-ca.crt` in the Integration Hub repo |

---

## Diagnosis

### Step 1 — Confirm the error is TLS-related

```powershell
podman pull python:3.13-slim-bookworm
```

If the output contains `x509: certificate signed by unknown authority`, the corporate CA is
the cause.

### Step 2 — Confirm which WSL distribution Podman uses

```powershell
wsl --list --verbose
```

Expected output includes:
```
  podman-machine-default    Running    2
```

### Step 3 — Confirm the CA cert file exists

```powershell
Get-ChildItem C:\path\to\Integration-Hub-Beta\ca-certs\
```

You should see at least one of:
- `corperate-ca.crt`
- `corperate-ca.pem.cer`

If only `corperate-ca.pem.cer` exists (no `.crt`), see **Appendix A** below.

---

## Fix

The fix has two parts:

1. Install the corporate CA cert into the Podman machine's trust store.
2. Restart the Podman machine so its running service daemon picks up the new cert.

### Part 1 — Install the cert inside the Podman WSL machine

The Windows filesystem is accessible inside WSL at `/mnt/c/`. Run the following from a
PowerShell terminal, adjusting the path to your repo clone:

```powershell
wsl -d podman-machine-default -- bash -c "
  sudo cp /mnt/c/path/to/Integration-Hub-Beta/ca-certs/corperate-ca.crt \
    /etc/pki/ca-trust/source/anchors/corperate-ca.crt && \
  sudo update-ca-trust extract && \
  echo 'CA trust updated successfully'
"
```

Example with the default clone location:

```powershell
wsl -d podman-machine-default -- bash -c "sudo cp /mnt/c/Users/$env:USERNAME/source/repos/Integration-Hub-Beta/ca-certs/corperate-ca.crt /etc/pki/ca-trust/source/anchors/corperate-ca.crt && sudo update-ca-trust extract && echo 'CA trust updated successfully'"
```

Expected output: `CA trust updated successfully`

#### Verify the cert was installed

```powershell
# Test that curl inside WSL can now reach Docker Hub
wsl -d podman-machine-default -- bash -c "curl -s https://registry-1.docker.io/v2/ && echo 'TLS OK'"
```

Expected output (a 401 is correct — it means TLS succeeded, auth is a separate step):
```json
{"errors":[{"code":"UNAUTHORIZED","message":"authentication required","detail":null}]}
TLS OK
```

### Part 2 — Restart the Podman machine

The Podman daemon (`podman system service`) is a long-running Go process. Go caches the
system CA bundle on first use, so the running daemon will **not** pick up the newly installed
cert without a restart.

```powershell
podman machine stop
podman machine start
```

Expected output:
```
Machine "podman-machine-default" stopped successfully
Starting machine "podman-machine-default"
...
Machine "podman-machine-default" started successfully
```

### Part 3 — Verify the fix

```powershell
podman pull python:3.13-slim-bookworm
```

Expected output:
```
Trying to pull docker.io/library/python:3.13-slim-bookworm...
Getting image source signatures
Copying blob sha256:...
...
sha256:<digest>
```

If the pull succeeds, you are ready to run the full stack:

```powershell
cd C:\path\to\Integration-Hub-Beta\local
just --justfile justfile.podman run phw-to-mpi
```

---

## Persistence

**The cert survives WSL restarts** — it is stored in the WSL filesystem and `update-ca-trust`
has already written it into the extracted bundle. You do not need to re-run the fix after
rebooting.

**The cert does NOT survive `podman machine rm`** — if the Podman machine is deleted and
recreated (e.g. after `podman machine rm podman-machine-default && podman machine init`),
you must repeat Part 1 and Part 2 above.

---

## Appendix A — Only `.pem.cer` exists in `ca-certs/`

The `.gitignore` in `ca-certs/` deliberately excludes `*.crt` files. If a colleague's
machine only has `corperate-ca.pem.cer`, they must create the `.crt` file locally before
running the fix:

```powershell
# In the repo root:
Copy-Item ca-certs\corperate-ca.pem.cer ca-certs\corperate-ca.crt
```

The file contents are identical — it is just a rename. The `.crt` extension is what the
Dockerfiles expect for the `COPY --from=ca-certs ./*.crt` instruction.

---

## Appendix B — Why the cert is not committed to git

The `.gitignore` in `ca-certs/` contains:

```
*.pem
*.crt
```

This is intentional. Certificates should be distributed through a controlled, trusted channel
(e.g. company device management, onboarding documentation) rather than a public git repository.
The `corperate-ca.pem.cer` file is retained as a reference copy only.

---

## Appendix C — Full summary of related Podman issues

For a broader guide to local development with Podman (profile names, first-run issues, etc.),
see [PODMAN_COMPOSE_SETUP.md](PODMAN_COMPOSE_SETUP.md).

---

## Quick Reference Card

```powershell
# 1. Install cert into Podman machine
wsl -d podman-machine-default -- bash -c "sudo cp /mnt/c/Users/$env:USERNAME/source/repos/Integration-Hub-Beta/ca-certs/corperate-ca.crt /etc/pki/ca-trust/source/anchors/corperate-ca.crt && sudo update-ca-trust extract"

# 2. Restart Podman machine
podman machine stop; podman machine start

# 3. Verify
podman pull python:3.13-slim-bookworm

# 4. Run the stack
cd C:\Users\$env:USERNAME\source\repos\Integration-Hub-Beta\local
just --justfile justfile.podman run phw-to-mpi
```
