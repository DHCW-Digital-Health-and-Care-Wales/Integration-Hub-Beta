# Podman Compose Setup for Integration Hub - PHW to MPI Profile

## Overview

This document details the steps taken to successfully run the Integration Hub local development environment using `podman-compose` with the `phw-to-mpi` profile. Several issues were encountered and resolved during the process.

---

## Initial Attempt

### Command Used
```bash
just start phw-to-mpi
```

### Issue #1: `just` Command Uses `docker` Not `podman-compose`
**Problem**: The `just start` command failed with:
```
sh: docker: command not found
error: recipe `start` failed on line 122 with exit code 127
```

The `justfile` is configured to use `docker compose` commands, but this environment has `podman-compose` installed instead.

**Resolution**: Ran `podman-compose` directly:
```bash
podman-compose -f ./docker-compose.yml --profile phw-to-mpi up -d
```

---

## Build Issues and Resolutions

### Issue #2: Missing CA Certificates (`.crt` files)

**Problem**: Multiple service builds failed with:
```
ERROR: building at STEP "COPY --from=ca-certs ./*.crt /usr/local/share/ca-certificates/":
checking on sources under "/Users/gareth/Developer/DHCW/Integration-Hub-Beta/ca-certs":
Rel: can't make relative to /Users/gareth/Developer/DHCW/Integration-Hub-Beta/ca-certs;
copier: stat: globs [/*.crt] matched nothing
```

**Root Cause**:
1. The `ca-certs/` directory exists but only contains `corperate-ca.pem.cer`
2. All Dockerfiles expect `*.crt` files to be present (e.g., `COPY --from=ca-certs ./*.crt /usr/local/share/ca-certificates/`)
3. The `.gitignore` in `ca-certs/` explicitly ignores `*.crt` files (they're not committed to git)

**Resolution**:
```bash
cp /Users/gareth/Developer/DHCW/Integration-Hub-Beta/ca-certs/corperate-ca.pem.cer \
   /Users/gareth/Developer/DHCW/Integration-Hub-Beta/ca-certs/corperate-ca.crt
```

This converts the existing PEM certificate to a `.crt` file that the Docker builds can find.

**Note**: The `.gitignore` in `ca-certs/` contains:
```
*.pem
*.crt
```
This is intentional - certificates should be generated/added locally and not committed to version control.

---

### Issue #3: Missing `phw-hl7-transformer` Image

**Problem**: After fixing the CA certificates issue, the build completed for some services but the `phw-hl7-transformer` image was not created. The `podman-compose` command reported:
```
ERROR:podman_compose:Build command failed
ERROR:podman_compose:Prepare images failed
```

**Root Cause**: The multi-stage build process failed on one service (`phw-hl7-transformer`) but continued with others. When it failed, not all required images were built.

**Resolution**: Built the missing image individually:
```bash
podman-compose -f ./docker-compose.yml --profile phw-to-mpi build phw-hl7-transformer
```

This successfully built the `integration-hub_phw-hl7-transformer` image.

---

## Final Successful Deployment

### Command
```bash
podman-compose -f ./docker-compose.yml --profile phw-to-mpi up -d
```

### Services Deployed

| Service | Container Name | Status | Ports |
|---------|----------------|--------|-------|
| SQL Edge | `sqledge` | Up | 1433/tcp |
| SQL Server | `sqlserver` | Up | 0.0.0.0:1433 |
| Service Bus Emulator | `sb-emulator` | Up | 0.0.0.0:5672 |
| PHW HL7 Server | `phw-hl7-server` | **Healthy** | 0.0.0.0:2575 |
| PHW HL7 Transformer | `phw-hl7-transformer` | **Healthy** | - |
| MPI HL7 Sender | `mpi-hl7-sender` | **Healthy** | - |
| MPI HL7 Mock Receiver | `mpi-hl7-mock-receiver` | Up | 0.0.0.0:2576 |
| Bus Watch | `bus-watch-server` | Up | 127.0.0.1:8080 |
| Message Store Service | `message-store-service` | **Healthy** | - |

---

## Architecture for `phw-to-mpi` Profile

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Integration Hub - PHW to MPI                     │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
┌───────▼────────┐       ┌───────▼────────┐       ┌────────▼────────┐
│  phw-hl7-server │──────▶ phw-hl7-      │───────▶ mpi-hl7-       │
│   (Port 2575)   │       │ transformer    │       │ sender          │
└─────────────────┘       └────────────────┘       └────────┬────────┘
                                                              │
                                                              ▼
                                                    ┌─────────────────┐
                                                    │ mpi-hl7-mock-  │
                                                    │ receiver        │
                                                    │ (Port 2576)    │
                                                    └─────────────────┘

┌──────────────────┐
│ Infrastructure Services (Required by all profiles)           │
├──────────────────┤
│ • sb-emulator (Azure Service Bus Emulator)                  │
│ • sqledge (Azure SQL Edge)                                 │
│ • sqlserver (SQL Server)                                   │
│ • message-store-service                                     │
│ • bus-watch-server (http://localhost:8080)                │
└──────────────────┘
```

---

## Key Learnings

### 1. Profile Name Typo Susceptibility
The profile names in `docker-compose.yml` use abbreviations that may not be obvious:
- `phw` = Public Health Wales
- `pims` = Patient Information Management System

**Tip**: Always verify profile names using:
```bash
grep -E "^    - [a-z]+-to-" docker-compose.yml | sort -u
```

### 2. CA Certificates Must Be Generated Locally
The `ca-certs/` directory requires `.crt` files that are not committed to git (listed in `.gitignore`). If you see build errors about missing `.crt` files:

1. Check if `ca-certs/` contains any `.crt` files
2. If not, convert any existing `.pem` or `.cer` files:
   ```bash
   cp ca-certs/corperate-ca.pem.cer ca-certs/corperate-ca.crt
   ```

### 3. Podman vs Docker Compose Differences
The `justfile` uses `docker compose` commands. For `podman-compose`, you must:
- Run `podman-compose` directly instead of using `just` commands, OR
- Create an alias: `alias docker=podman` and `alias docker-compose=podman-compose`

### 4. Image Platform Warnings
You may see:
```
WARNING: image platform (linux/amd64) does not match the expected platform (linux/arm64)
```

This is expected on Apple Silicon Macs. The images will still run under Rosetta 2 emulation, but performance may be slightly impacted.

### 5. Build Failures May Be Partial
When using `podman-compose`, if one service fails to build, it may not fail the entire build process. Always verify all required images are built:
```bash
podman images | grep integration-hub
```

---

## Useful Commands

### Check Running Services
```bash
podman ps
```

### View Logs
```bash
podman-compose -f ./docker-compose.yml --profile phw-to-mpi logs -f [service-name]
```

### Stop All Services
```bash
podman-compose -f ./docker-compose.yml --profile phw-to-mpi down
```

### Rebuild a Specific Service
```bash
podman-compose -f ./docker-compose.yml --profile phw-to-mpi build [service-name]
```

### Send Test HL7 Message
```bash
mllp_send --loose --file ./sample_messages/phw-to-mpi.sample.hl7 --port 2575 127.0.0.1
```

---

## Conclusion

The Integration Hub `phw-to-mpi` profile is now running successfully with `podman-compose`. The main issues were:
1. Missing CA certificate files (resolved by converting `.cer` to `.crt`)
2. Incomplete image builds (resolved by building missing images individually)

The system is now ready for development and testing.

---

**Date**: 2026-07-11  
**Environment**: macOS (Apple Silicon), Podman 6.0.1, podman-compose 1.6.0
