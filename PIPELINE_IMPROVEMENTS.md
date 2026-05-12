# Integration-Hub-Beta — Pipeline Improvement Plan

> **Date:** 2026-05-11
> **Branch:** INTHUB-588006-REFACTOR
> **Status:** Items 1–4 completed, remaining items listed below

---

## Completed Improvements ✅

| # | Improvement | Commit |
|---|-------------|--------|
| ✅ | Docker layer caching (`--cache-from`/`--cache-to` in docker-build-push-template.yml) | `b47d311` |
| ✅ | UV tool & package caching (`Cache@2` in code-quality-template.yml) | `b47d311` |
| ✅ | Consolidated `build-apps.yml` — all 11 containers in one pipeline | `5f17ad9`, `1fff070` |
| ✅ | PR validation consolidated from 16 jobs → 1 job (~25 min → ~5-7 min) | `ef4a643` |

---

## Remaining Improvements

### 🔴 Critical

#### 1. Release Pipeline Missing 2 Apps
**File:** `pipeline-ado/release-apps.yml`
**Impact:** HIGH | **Effort:** SMALL

`messagestoreservice` and `messagereplayjob` both have build pipelines and are included in `build-apps.yml` and PR validation, but are **not configured in the release pipeline**. These apps can be built but never released.

**Fix:**
- Add both apps to the `resources.pipelines` section
- Add corresponding entries to `appConfig` in the dynamic stages template
- Verify the `appImageName` matches the Docker image name used in the build pipeline

---

#### 2. Network Test App Missing CodeQuality Stage
**File:** `pipeline-ado/networktestapp-build.yml`
**Impact:** HIGH | **Effort:** SMALL

The only app without a CodeQuality stage in its individual build pipeline. All other 10 apps run code quality checks before building. Code quality IS checked in `build-apps.yml` and `pr-validation.yml`, but the individual pipeline bypasses it entirely.

**Fix:**
- Add a CodeQuality stage before the BuildAndPush stage, following the pattern from other `*-build.yml` files

---

### 🟠 High Priority

#### 3. BusWatch — Orphan in PR Validation
**File:** `pipeline-ado/pr-validation.yml`
**Impact:** MEDIUM | **Effort:** SMALL

`buswatch` is included in PR validation (code quality + tests run) but has **no build pipeline** and is **not in the release pipeline**. Code is validated but never built or released.

**Action Required:**
- Confirm with the team: is BusWatch still maintained?
- If yes → create `buswatch-build.yml` and add to `release-apps.yml`
- If no → remove from `pr-validation.yml` and path triggers

---

#### 4. Trivy Scanning is Non-Blocking
**File:** `pipeline-ado/templates/docker-build-push-template.yml` (line ~168)
**Impact:** MEDIUM | **Effort:** SMALL

The Trivy container vulnerability scan uses `continueOnError: true` and `--exit-code 0`, meaning vulnerabilities **never block a build**. Critical vulnerabilities can be pushed to ACR undetected.

**Recommendation:**
- Add a template parameter `blockOnCriticalVulnerabilities` (default: `true`)
- When enabled, use `--exit-code 1 --severity CRITICAL` so builds fail on critical CVEs
- Keep `continueOnError: true` for non-critical severities

---

#### 5. Trivy Version Not Pinned
**File:** `pipeline-ado/templates/docker-build-push-template.yml` (line ~81)
**Impact:** MEDIUM | **Effort:** SMALL

Trivy is installed via `sudo apt-get install -y trivy` which always pulls the latest version. This makes builds non-deterministic — scanning behaviour can change without any code changes.

**Fix:**
- Pin to a specific version: `sudo apt-get install -y trivy=0.XX.X`
- Or use a versioned container: `docker run aquasec/trivy:0.XX.X`

---

### 🟡 Medium Priority

#### 6. No Test Result Publishing
**Files:** All pipeline files with test steps
**Impact:** MEDIUM | **Effort:** MEDIUM

Unit tests run (pytest/unittest) but results are **not published to ADO**. Test results are only visible in raw logs, not in the ADO Tests tab. No coverage reports are generated or tracked.

**Fix:**
- Add `--junitxml=test-results.xml` to pytest / use `xmlrunner` for unittest
- Add `PublishTestResults@2` task after test execution
- Optionally add `PublishCodeCoverageResults@2` for coverage tracking

---

#### 7. No Scheduled Security Scans
**Files:** None (missing capability)
**Impact:** MEDIUM | **Effort:** MEDIUM

Trivy scans only run during builds. Released container images in ACR are **never re-scanned** for newly discovered vulnerabilities. Dependency audits (`uv audit`, plus `pip-audit` in the per-app code-quality template) also only run during builds.

**Recommendation:**
- Create `nightly-security-scan.yml` with a cron schedule
- Scan all released images in ACR for CRITICAL/HIGH vulnerabilities
- Send notifications on new findings

---

#### 8. ACR Cleanup Could Be Optimised
**File:** `pipeline-ado/templates/docker-build-push-template.yml` (lines ~218-248)
**Impact:** MEDIUM | **Effort:** SMALL

Current cleanup retains 50 images and deletes excess tags one-at-a-time. Issues:
- Sequential deletion is slow for large image sets
- No check whether a tag is currently deployed in production
- The `buildcache` tag accumulates and is never cleaned

**Recommendations:**
- Batch-delete old tags instead of looping
- Query Container Apps to exclude currently-deployed tags
- Add periodic `buildcache` tag cleanup

---

#### 9. No Timeouts on Build Stages
**Files:** `pipeline-ado/build-apps.yml`, individual `*-build.yml` files
**Impact:** MEDIUM | **Effort:** SMALL

PR validation has `timeoutInMinutes: 30` but build stages have **no explicit timeout**. A hung Docker build could block the pipeline indefinitely.

**Fix:**
- Add `timeoutInMinutes: 45` to all build jobs
- Add `cancelTimeoutInMinutes: 5` for cleanup

---

#### 10. build-apps.yml Parallel CQ Stages Duplicate Work
**File:** `pipeline-ado/build-apps.yml`
**Impact:** MEDIUM | **Effort:** SMALL

When building all apps, 10 CodeQuality stages run in parallel — each independently installs Python, uv, ruff, bandit, mypy, pip-audit, and all 7 shared libraries. That's 10× the same setup work.

**Recommendation:**
- Add a shared `Prerequisites` stage that installs tools and caches them
- Make all CodeQuality stages `dependsOn: Prerequisites`
- Or consolidate CQ into a single job (like pr-validation.yml) with a loop

---

### 🟢 Low Priority

#### 11. No Test-Only Pipeline
**Files:** None (missing capability)
**Impact:** LOW | **Effort:** SMALL

To run just code quality and tests without building Docker images, developers must use the PR pipeline or modify `build-apps.yml`. A dedicated test-only pipeline would provide faster feedback (~3-5 min vs ~20+ min).

---

#### 12. Individual `*-build.yml` Files Are Redundant
**Files:** 10 individual `*-build.yml` files
**Impact:** LOW | **Effort:** LARGE

With `build-apps.yml` now available, the 10 individual build files are partially redundant. They remain useful for per-path CI triggers (auto-build on push to specific app directories), but maintaining 10 near-identical files is a burden.

**Options:**
1. Keep as-is for per-path CI triggers (current state)
2. Set all to `trigger: none` and use only `build-apps.yml`
3. Deprecate gradually as team adopts consolidated pipeline

---

#### 13. Variable Naming Inconsistency
**Files:** Multiple pipeline and template files
**Impact:** LOW | **Effort:** SMALL

The `appName` parameter means different things in different contexts:
- In `code-quality-template.yml`: directory name (e.g., `hl7_server`)
- In `docker-build-push-template.yml`: Docker image name (e.g., `hl7server`)

This works but is confusing. Consider renaming to `appDirName` and `appImageName` for clarity.

---

## Already Optimised ✓

| Area | Status |
|------|--------|
| Python version (3.13) | Consistent across all pipelines |
| Pool names | Consistent (`UKS-DHCW-IH-DEV-ADOManagedPool`) |
| fetchDepth | Set to 1 (shallow clone) everywhere |
| Dashboard service connection | Intentionally different (`DEV-MonitoringDashboard`) |
| Docker layer caching | Implemented via ACR registry cache |
| UV tool caching | Implemented via Cache@2 |
| PR validation speed | Consolidated to single job |
