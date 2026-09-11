# Review: Conditional/Selectable Release Apps Pipeline (Spike)

## Verdict: Correct and safe

The core mechanism is sound. The job template at `templates/release-container-app-template.yml` does:

```yaml
- download: ${{ parameters.resourcePipelineName }}
  artifact: imageTag
```

A `download` only works if that pipeline is declared under `resources.pipelines`. The
dynamic-stages template only generates a stage for the selected app, and that stage downloads
*only* its own `buildPipeline`. So the invariant that matters is: **every build pipeline that a
generated stage could download must be declared for that same `selectedApp`.** The conditional
`resources` block satisfies this exactly.

## Mapping verified complete

All 17 distinct `buildPipeline` values in `appConfig` were checked against the grouped resource
conditions — every app lands in the correct group, and no app is missing:

| Build pipeline | Apps in the `in(...)` group | Matches appConfig |
|---|---|---|
| HL7 Server - Build | PHW, PIMS, Paris, Chemocare, MPI, WDS, Mosaiq (7) | Yes |
| HL7 Subscription Sender - Build | MPI, SWW Chemo, BCU Chemo, PHW, PMS (5) | Yes |
| HL7 Sender - Build | HL7 Sender, PIMS, Chemocare (3) | Yes |
| REST Server - Build | REST Server, WPAS (2) | Yes |
| HL7 SOAP Server - Build | LIMS, PMS (2) | Yes |
| The 12 single-app pipelines | each 1:1 | Yes |

`in()` is valid ADO expression syntax, conditional insertion of `- pipeline:` items into a
sequence is the documented pattern, and the block can never resolve to empty (any selection
yields at least one resource).

## Why it's safe

- **No behavioural change to deployments.** For a given `selectedApp`/`selectedEnvironment`, the
  generated stages, service connections, approvals, environments, and image-import logic are
  identical to `release-apps.yml`. Only which resources are *declared* has been narrowed.
- The only effective difference is the intended one: releasing a healthy single app no longer
  fails validation because some *unrelated* build pipeline never had a successful run.
- `selectedEnvironment` correctly does **not** factor into the resources block — environment
  choice doesn't change which image artifact is needed.

## Minor risks to note (not blockers)

1. **Duplicated mapping.** The app→buildPipeline relationship now lives twice (in `appConfig` and
   in the `resources` groups). If someone adds an app to `appConfig` but forgets the matching
   `resources` group, selecting that app (or `all`) will fail at `download:` with an
   undeclared-resource error. The comment documents this well — the right mitigation for a static
   `resources` block.
2. **`all` still needs every build green at least once** — unchanged limitation, correctly
   documented.

## Incidental improvements over `release-apps.yml`

- The original declares **`REST Server - Build` twice**; this version declares it once.
- The original's `appConfig` includes **Message Store Service** but its `resources` block omits
  `Message Store Service - Build` — so an `all` or Message-Store release would hit an undeclared
  `download`. The spike adds that resource group, closing a latent gap.

## Before merging

Confirm that a **`Message Store Service - Build`** pipeline actually exists in ADO. If it doesn't
yet exist, declaring it will make `selectedApp: 'all'` fail validation — but that gap is already
latent in the current `appConfig`, so this spike surfaces it rather than causing it.
