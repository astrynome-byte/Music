$msi="$env:GITHUB_WORKSPACE/driver/.cadence-studio/retained-2008-msi"
& "$msi/Package-Retained2008.ps1" `
  -StagePath "$env:RUNNER_TEMP/stage-cadence" -ApplicationSource "$env:GITHUB_WORKSPACE/cadence-src" `
  -SourceProfilePath "$env:GITHUB_WORKSPACE/driver/.cadence-studio/combined-2008-source/source.json" `
  -ArtifactDirectory "$env:RUNNER_TEMP/cadence-stage-delivery" `
  -RuntimeInventoryPath "$msi/known-evidence/runtime-inventory.MEASURED.json" `
  -ReadbackReceiptPath "$msi/known-evidence/dataonly-console-receipt.projection.json" `
  -PackageBindingsPath "$env:RUNNER_TEMP/retained-package-bindings.MEASURED.json" `
  -QualificationReportPath "$env:RUNNER_TEMP/retained-qa-evidence/retained-qualification.json" `
  -QualificationEvidenceRoot "$env:RUNNER_TEMP/retained-qa-evidence" `
  -CorrespondingSourceBundle "$env:RUNNER_TEMP/cadence-stage-delivery/corresponding-sources" `
  -BuildRecipeDirectory "$env:RUNNER_TEMP/selected-build-recipe" `
  -OutputDirectory "$env:RUNNER_TEMP/retained2008-package"

