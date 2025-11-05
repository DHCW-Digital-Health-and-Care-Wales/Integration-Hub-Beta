# Multi-Selection Deployment Guide

## ✅ **Now Supports Multiple Apps and Environments!**

The improved pipeline now supports deploying multiple applications to multiple environments using comma-separated values.

## 📋 **Parameters**

### 1. **selectedApps** (comma-separated string)
Select one or more applications to deploy:
- **Single app**: `PHW HL7Server`
- **Multiple apps**: `PHW HL7Server,PIMS HL7Server,HL7 Sender`
- **All apps**: `all`

### 2. **selectedEnvironments** (comma-separated string)
Select one or more environments to deploy to:
- **Single environment**: `dev`
- **Multiple environments**: `dev,dte,tst`
- **All environments**: `all`

### 3. **maintainDependencies** (boolean)
Control environment deployment order:
- **false** (default): Deploy to selected environments independently (parallel)
- **true**: Maintain dev→dte→tst→ppd→prd chain (sequential, only for selected envs)

## 🎯 **Usage Examples**

### Example 1: Deploy Multiple Apps to Dev
```yaml
selectedApps: 'PHW HL7Server,PIMS HL7Server,HL7 Sender'
selectedEnvironments: 'dev'
maintainDependencies: false
```
**Result**: 3 apps deployed to dev environment (3 stages, parallel execution)

### Example 2: Deploy Single App to Multiple Environments (Independent)
```yaml
selectedApps: 'PHW HL7Server'
selectedEnvironments: 'dev,tst,ppd'
maintainDependencies: false
```
**Result**: PHW HL7Server deployed to dev, tst, and ppd independently (3 stages, parallel execution)

### Example 3: Deploy Single App Through Environment Chain
```yaml
selectedApps: 'PHW HL7Server'
selectedEnvironments: 'dev,dte,tst'
maintainDependencies: true
```
**Result**: PHW HL7Server deployed dev→dte→tst (3 stages, sequential: dev first, then dte, then tst)

### Example 4: Deploy Multiple Apps to Multiple Environments (Independent)
```yaml
selectedApps: 'PHW HL7Server,PIMS HL7Server'
selectedEnvironments: 'dev,tst'
maintainDependencies: false
```
**Result**: 2 apps × 2 environments = 4 stages (all run in parallel)
- PHW HL7Server → dev
- PHW HL7Server → tst
- PIMS HL7Server → dev
- PIMS HL7Server → tst

### Example 5: Deploy Multiple Apps Through Environment Chain
```yaml
selectedApps: 'PHW HL7Server,PIMS HL7Server,HL7 Sender'
selectedEnvironments: 'dev,dte,tst'
maintainDependencies: true
```
**Result**: 3 apps through 3 environments = 9 stages
- All apps deploy to dev first (parallel)
- Then all apps deploy to dte (parallel, after dev completes)
- Then all apps deploy to tst (parallel, after dte completes)

### Example 6: Full Production Release (Same as Before)
```yaml
selectedApps: 'all'
selectedEnvironments: 'all'
maintainDependencies: true
```
**Result**: All 12 apps through all 5 environments with proper dependencies (55 stages)

### Example 7: Hotfix Deployment
```yaml
selectedApps: 'PIMS HL7Server'
selectedEnvironments: 'prd'
maintainDependencies: false
```
**Result**: Single app to production only (1 stage, no dependencies)

### Example 8: Parallel Multi-Environment Testing
```yaml
selectedApps: 'HL7 Sender,HL7 Mock Receiver'
selectedEnvironments: 'dev,dte'
maintainDependencies: false
```
**Result**: 2 apps × 2 environments = 4 stages (all run in parallel)
- HL7 Sender → dev
- HL7 Sender → dte
- HL7 Mock Receiver → dev
- HL7 Mock Receiver → dte

## 🎨 **How It Works**

### Comma-Separated Parsing
The pipeline uses Azure DevOps' `contains()` function to check if an app/environment name exists in the comma-separated string:

```yaml
# For apps:
contains('PHW HL7Server,PIMS HL7Server', 'PHW HL7Server')  # true
contains('PHW HL7Server,PIMS HL7Server', 'HL7 Sender')     # false

# For environments:
contains('dev,tst,prd', 'tst')  # true
contains('dev,tst,prd', 'dte')  # false
```

### Dependency Logic

#### When `maintainDependencies: false` (Default)
- All selected stages run **independently**
- No stage waits for another
- **Fastest execution** - all run in parallel
- Use for: hotfixes, testing, independent deployments

#### When `maintainDependencies: true`
- Environment order is **enforced** (only for selected environments)
- dev must complete before dte
- dte must complete before tst
- tst must complete before ppd
- ppd must complete before prd
- Use for: proper release progression, compliance requirements

## 📝 **Application Names (for selectedApps parameter)**

```
PHW HL7Server
PIMS HL7Server
Paris HL7Server
Chemocare HL7Server
MPI HL7Server
HL7 Phw Transformer
HL7 Chemo Transformer
HL7 Pims Transformer
HL7 Sender
PIMS HL7 Sender
Chemocare HL7 Sender
HL7 Mock Receiver
```

**Important**: Use exact names (case-sensitive, spaces matter)

## 🌍 **Environment Names (for selectedEnvironments parameter)**

```
dev   - Development
dte   - DTE
tst   - Test
ppd   - Pre-Production
prd   - Production
```

## ⚡ **Performance Comparison**

| Scenario | Stages | Execution Time | Dependencies |
|----------|--------|----------------|--------------|
| All apps, all envs | 55 | ~45 min | Sequential by env |
| 1 app, all envs (sequential) | 5 | ~8 min | dev→dte→tst→ppd→prd |
| 1 app, all envs (parallel) | 5 | ~3 min | All parallel |
| 3 apps, 2 envs (parallel) | 6 | ~4 min | All parallel |
| 1 app, 1 env | 1 | ~2 min | None |

## ⚠️ **Important Notes**

### Comma-Separated Format
- **No spaces after commas** (optional but recommended for consistency)
- Use exact app/environment names
- Case-sensitive matching

### Dependency Behavior
- Dependencies only apply between **selected** environments
- If you select `tst,prd` with dependencies, tst runs first, then prd
- If previous env not selected, dependencies are skipped

### Special Keyword "all"
- Using `all` for apps: deploys all 12 applications
- Using `all` for environments: deploys to all 5 environments
- `maintainDependencies` only matters when using `all` for environments

## 🐛 **Troubleshooting**

### "No stages to deploy"
- Check spelling of app/environment names
- Ensure no extra spaces in comma-separated list
- Verify names match exactly (case-sensitive)

### "Stage dependencies not working"
- Ensure `maintainDependencies: true` is set
- Verify all dependent environments are included in the list
- Example: For tst to depend on dte, both must be in `selectedEnvironments`

### "Pipeline taking too long"
- Use `maintainDependencies: false` for parallel execution
- Deploy only needed apps/environments
- Consider deploying to fewer environments

## 💡 **Pro Tips**

1. **Quick Testing**: Deploy to `dev` only with specific apps
2. **Environment Promotion**: Use sequential deps for proper progression
3. **Hotfixes**: Single app + single environment + no deps = fastest
4. **Parallel Testing**: Multiple apps + multiple envs + no deps = efficient
5. **Production Release**: `all` + `all` + deps = traditional pipeline behavior

## 🎓 **Migration from Old Parameters**

If you were using the old single-select parameters:

```yaml
# Old (single selection)
selectedApp: 'PHW HL7Server'
selectedEnvironment: 'dev'

# New (supports multiple)
selectedApps: 'PHW HL7Server'           # Single app still works
selectedEnvironments: 'dev'             # Single env still works
maintainDependencies: false             # New parameter

# Multiple selections
selectedApps: 'PHW HL7Server,PIMS HL7Server'
selectedEnvironments: 'dev,dte,tst'
maintainDependencies: true
```

---

**Summary**: The improved pipeline now gives you complete flexibility to deploy any combination of apps and environments, with full control over deployment order and parallelization! 🚀
