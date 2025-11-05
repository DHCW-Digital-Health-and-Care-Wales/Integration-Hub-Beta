# Checkbox-Based Pipeline Selection

## Overview

This document describes the checkbox-based approach for selecting applications and environments in Azure DevOps pipelines.

## ⚠️ Important Note

**Azure DevOps YAML pipelines do not support native multi-select checkbox parameters.** The only available parameter types are:
- `string` - Text input or dropdown
- `number` - Numeric input  
- `boolean` - Single checkbox (true/false)
- `object` - Complex object

## Available Approaches

### Approach 1: Individual Boolean Checkboxes ⭐ (Recommended for UX)

**Files:**
- `pipeline-ado/release-apps-checkboxes.yml`
- `pipeline-ado/templates/dynamic-stages-checkbox-template.yml`

**Pros:**
- ✅ Best user experience - true checkboxes
- ✅ Clear visual interface
- ✅ Easy to select multiple items
- ✅ No typing required

**Cons:**
- ❌ Long parameter list (18 checkboxes: 13 apps + 5 environments)
- ❌ More maintenance when adding new apps/environments
- ❌ Longer pipeline YAML file

**When to Use:**
- When user experience is the top priority
- When the number of apps/environments is relatively stable
- When users prefer clicking over typing

---

### Approach 2: Comma-Separated String ⭐ (Recommended for Maintainability)

**Files:**
- `pipeline-ado/release-apps-improved.yml`
- `pipeline-ado/templates/dynamic-stages-template.yml`

**Pros:**
- ✅ Compact parameter list (2 text fields)
- ✅ Easy to maintain and extend
- ✅ Shorter pipeline YAML
- ✅ Flexible - can select any combination

**Cons:**
- ❌ Requires typing (no visual checkboxes)
- ❌ Need to remember app/environment names
- ❌ Slight learning curve

**When to Use:**
- When maintainability is important
- When you frequently add new apps/environments
- When users are comfortable with command-line-style inputs

---

## Using the Checkbox Approach

### 1. Selecting Applications

The pipeline provides 14 checkboxes for application selection:

```yaml
✓ Deploy ALL Applications          # Master switch - deploys all apps
☐ PHW HL7Server
☐ PIMS HL7Server
☐ Paris HL7Server
☐ Chemocare HL7Server
☐ MPI HL7Server
☐ HL7 Phw Transformer
☐ HL7 Chemo Transformer
☐ HL7 Pims Transformer
☐ HL7 Sender
☐ PIMS HL7 Sender
☐ Chemocare HL7 Sender
☐ HL7 Mock Receiver
```

### 2. Selecting Environments

The pipeline provides 6 checkboxes for environment selection:

```yaml
✓ Deploy to ALL Environments       # Master switch - deploys to all environments
☐ Development (dev)
☐ DTE
☐ Test (tst)
☐ Pre-Production (ppd)
☐ Production (prd)
```

### 3. Dependencies

```yaml
☐ Maintain environment dependencies (dev→dte→tst→ppd→prd)?
```

- **Checked**: Stages run sequentially (dev completes before dte starts, etc.)
- **Unchecked**: All selected stages run in parallel

---

## Usage Examples

### Example 1: Deploy Single App to Single Environment

**Selections:**
- ✓ PHW HL7Server
- ✓ Development (dev)
- ☐ Maintain dependencies (doesn't matter for single env)

**Result:** Deploys PHW HL7Server to dev only

---

### Example 2: Deploy Multiple Apps to Production

**Selections:**
- ✓ PHW HL7Server
- ✓ HL7 Phw Transformer
- ✓ HL7 Sender
- ✓ Production (prd)
- ☐ Maintain dependencies (doesn't matter for single env)

**Result:** Deploys all 3 apps to production in parallel

---

### Example 3: Deploy All Apps to Dev and Test

**Selections:**
- ✓ Deploy ALL Applications
- ✓ Development (dev)
- ✓ Test (tst)
- ✓ Maintain dependencies

**Result:** 
1. All apps deploy to dev first
2. After dev completes, all apps deploy to tst

---

### Example 4: Deploy Specific Apps Across All Environments

**Selections:**
- ✓ PIMS HL7Server
- ✓ HL7 Pims Transformer
- ✓ PIMS HL7 Sender
- ✓ Deploy to ALL Environments
- ✓ Maintain dependencies

**Result:**
1. PIMS apps → dev
2. PIMS apps → dte (after dev completes)
3. PIMS apps → tst (after dte completes)
4. PIMS apps → ppd (after tst completes)
5. PIMS apps → prd (after ppd completes)

---

### Example 5: Parallel Deployment to Multiple Environments

**Selections:**
- ✓ Deploy ALL Applications
- ✓ Development (dev)
- ✓ Test (tst)
- ✓ Pre-Production (ppd)
- ☐ Maintain dependencies (unchecked)

**Result:** All apps deploy to dev, tst, and ppd simultaneously (no waiting)

---

## Implementation Details

### How It Works

1. **Parameter Definition**: Each app and environment gets its own boolean parameter
2. **Master Switches**: `deployAllApps` and `deployToAllEnvironments` override individual selections
3. **Template Logic**: Uses `${{ or() }}` expressions to check if deployment should happen:
   ```yaml
   ${{ if or(eq(parameters.deployAllApps, true), eq(parameters[app.paramName], true)) }}:
   ```
4. **Dependency Management**: Respects `maintainDependencies` flag for sequential vs parallel execution

### Adding New Applications

To add a new application, you need to update **3 locations**:

1. **Add checkbox parameter** in `release-apps-checkboxes.yml`:
   ```yaml
   - name: deployMyNewApp
     displayName: '☐ My New App'
     type: boolean
     default: false
   ```

2. **Add to appConfig** in `release-apps-checkboxes.yml`:
   ```yaml
   - name: 'My New App'
     paramName: 'deployMyNewApp'
     appName: 'mynewapp'
     appFunctionMidfix: ''
     buildPipeline: 'My New App - Build'
   ```

3. **Add parameter to template** in `dynamic-stages-checkbox-template.yml`:
   ```yaml
   - name: deployMyNewApp
     type: boolean
   ```

4. **Pass parameter to template** in `release-apps-checkboxes.yml`:
   ```yaml
   deployMyNewApp: ${{ parameters.deployMyNewApp }}
   ```

### Adding New Environments

Similar process - add checkbox, add to environments config, add to template parameters, pass to template.

---

## Comparison: Checkboxes vs Comma-Separated

| Feature | Checkboxes | Comma-Separated |
|---------|-----------|-----------------|
| **User Experience** | ⭐⭐⭐⭐⭐ Excellent | ⭐⭐⭐ Good |
| **Maintainability** | ⭐⭐ Fair | ⭐⭐⭐⭐⭐ Excellent |
| **Pipeline Length** | ~220 lines | ~200 lines |
| **Setup Complexity** | Medium | Low |
| **Adding New Items** | 4 changes required | No changes needed |
| **Learning Curve** | None | Slight |
| **Typing Required** | None | Yes |
| **Visual Clarity** | Excellent | Moderate |

---

## Recommendation

**Choose Checkbox Approach if:**
- User experience is paramount
- Your list of apps/environments is stable
- Users prefer clicking over typing
- You don't mind the maintenance overhead

**Choose Comma-Separated Approach if:**
- You frequently add/remove apps or environments
- You prefer concise pipeline definitions
- Users are comfortable with comma-separated values
- Maintainability is a priority

**Hybrid Approach:**
You could also use **checkboxes for environments** (stable - only 5 items) and **comma-separated for apps** (growing - 13+ items).

---

## Migration Between Approaches

To switch from comma-separated to checkboxes:
1. Replace `release-apps-improved.yml` with `release-apps-checkboxes.yml`
2. Update pipeline definition in Azure DevOps

To switch from checkboxes to comma-separated:
1. Replace `release-apps-checkboxes.yml` with `release-apps-improved.yml`  
2. Update pipeline definition in Azure DevOps

Both approaches are fully functional and production-ready!

---

## Questions?

See also:
- `MULTI_SELECT_GUIDE.md` - Comma-separated string approach
- `PIPELINE_IMPROVEMENTS.md` - Overall pipeline architecture
- `QUICK_START.md` - Getting started guide
