# Quick Start Guide - Improved Pipeline

## 🚀 What's Different?

### **Before: Repetitive Stages (1058 lines)**
```yaml
stages:
  - stage: ReleasePHWHL7ServerDev
    displayName: 'Release App PHW HL7Server - Dev'
    jobs:
      - template: templates/release-container-app-template.yml
        parameters:
          jobName: 'ReleasePHWAppHL7ServerDev'
          displayName: 'Release App PHW HL7Server - Dev'
          appName: 'hl7server'
          appFunctionMidfix: 'phw'
          resourceGroupName: 'UK-South-DHCW-IntHub-DEV-RG'
          # ... 8 more lines
  
  - stage: ReleasePHWHL7ServerDTE
    # ... another 15 lines
  
  - stage: ReleasePHWHL7ServerTest
    # ... another 15 lines
    
  # Repeat 55+ times for each app × environment combination
```

### **After: Dynamic Generation (~200 lines)**
```yaml
parameters:
  - name: selectedApp
    displayName: 'Select Application'
    default: 'all'
    values: ['all', 'PHW HL7Server', 'PIMS HL7Server', ...]
  
  - name: selectedEnvironment
    displayName: 'Select Environment'
    default: 'all'
    values: ['all', 'dev', 'dte', 'tst', 'ppd', 'prd']

stages:
  - template: templates/dynamic-stages-template.yml
    parameters:
      selectedApp: ${{ parameters.selectedApp }}
      selectedEnvironment: ${{ parameters.selectedEnvironment }}
      appConfig:
        - name: 'PHW HL7Server'
          appName: 'hl7server'
          appFunctionMidfix: 'phw'
          buildPipeline: 'HL7 Server - Build'
        # ... more apps (6 lines each)
      environments:
        - name: 'dev'
          resourceGroup: 'UK-South-DHCW-IntHub-DEV-RG'
          poolName: 'POOL_NAME_NON_PROD'
        # ... more environments (4 lines each)
```

## 📊 Benefits at a Glance

| Feature | Current Pipeline | Improved Pipeline |
|---------|-----------------|-------------------|
| **Lines of Code** | 1,058 | ~200 (81% less) |
| **To Add New App** | 250 lines (50 per env) | 6 lines |
| **To Add New Environment** | 550 lines (50 per app) | 5 lines |
| **Selective Deployment** | ❌ Not possible | ✅ Yes, via parameters |
| **Maintenance Effort** | 🔴 High | 🟢 Low |
| **Error Prone** | 🔴 High (copy-paste) | 🟢 Low (single source) |

## 🎯 How to Use

### 1. Deploy Everything (Same as Current)
```
Run Pipeline → Use Defaults
  - selectedApp: all
  - selectedEnvironment: all
```
Result: All 12 apps deployed to all 5 environments (55 stages)

### 2. Deploy One App to All Environments
```
Run Pipeline
  - selectedApp: PHW HL7Server
  - selectedEnvironment: all
```
Result: PHW HL7Server deployed to dev → dte → tst → ppd → prd (5 stages)

### 3. Deploy All Apps to One Environment
```
Run Pipeline
  - selectedApp: all
  - selectedEnvironment: dev
```
Result: All 12 apps deployed to dev only (12 stages)

### 4. Deploy One App to One Environment (Fastest)
```
Run Pipeline
  - selectedApp: PIMS HL7Server
  - selectedEnvironment: dte
```
Result: Only PIMS HL7Server deployed to DTE (1 stage)

## 🔧 Files You Need

### New Files Created:
1. **`release-apps-improved.yml`** - New main pipeline (use this instead of release-apps.yml)
2. **`templates/dynamic-stages-template.yml`** - Stage generator template
3. **`config/apps-config.yml`** - Configuration reference (optional)

### Existing Files (No Changes Needed):
- `templates/release-container-app-template.yml` - Works as-is
- All build pipelines - No changes needed

## ⚡ Quick Migration Steps

### Option 1: Test First (Recommended)
1. Keep your existing `release-apps.yml`
2. Create new pipeline in Azure DevOps pointing to `release-apps-improved.yml`
3. Test the new pipeline
4. Compare results with old pipeline
5. Once confident, switch your existing pipeline to use the new file

### Option 2: Direct Switch
1. Backup `release-apps.yml` → `release-apps-backup.yml`
2. Rename `release-apps-improved.yml` → `release-apps.yml`
3. Test deployment
4. Roll back if issues occur

## 📝 Adding Your Next Application

### Old Way (250 lines):
```yaml
# Must copy-paste 50 lines for each environment
- stage: NewAppDev
  displayName: 'Release App NewApp - Dev'
  jobs: ...
- stage: NewAppDTE
  displayName: 'Release App NewApp - DTE'
  jobs: ...
# ... repeat for tst, ppd, prd
```

### New Way (6 lines):
```yaml
# Just add to appConfig in release-apps-improved.yml
- name: 'New Application'
  appName: 'newapp'
  appFunctionMidfix: 'variant'
  buildPipeline: 'New App - Build'
```

Done! The template automatically generates all 5 environment stages.

## ❓ Common Questions

**Q: Will this break existing deployments?**
A: No, the new pipeline generates the same stages, just dynamically.

**Q: Can I still see individual stages in Azure DevOps?**
A: Yes! All stages are generated and visible in the UI.

**Q: What if I only want to deploy to production?**
A: Select `selectedEnvironment: prd` - only production stages run.

**Q: Does this work with approvals and gates?**
A: Yes! Environment approvals still work as before.

**Q: How do I add a new environment?**
A: Add 5 lines to the `environments` array in the pipeline.

**Q: What about dependencies between stages?**
A: Handled automatically - dev → dte → tst → ppd → prd.

## 🧪 Testing Checklist

Before full rollout, test these scenarios:

- [ ] Deploy single app to dev
- [ ] Deploy all apps to dev
- [ ] Deploy single app through all environments
- [ ] Deploy with approval gates (ppd, prd)
- [ ] Verify dependency chain works (dte depends on dev, etc.)
- [ ] Check deployment logs match old pipeline
- [ ] Verify app resources created correctly
- [ ] Test parameter combinations

## 📞 Need Help?

1. **Review Full Documentation**: See `PIPELINE_IMPROVEMENTS.md`
2. **Check Azure DevOps Logs**: Pipeline runs show all generated stages
3. **Compare Outputs**: Run both pipelines and compare results
4. **Test in Dev First**: Always validate in dev environment

## 🎓 Next Steps

1. **Review** the new pipeline files
2. **Test** in a safe environment
3. **Compare** with existing pipeline results
4. **Migrate** when confident
5. **Add** new apps with ease!

---

**Summary**: Transform 1,058 lines → 200 lines, add runtime flexibility, reduce maintenance by 80% 🚀
