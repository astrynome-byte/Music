python -I -B "$env:GITHUB_WORKSPACE/driver/.cadence-studio/retained-2008-msi/Restore-QualifiedQaEvidence.py" `
  --selection "$env:GITHUB_WORKSPACE/driver/.cadence-studio/retained-2008-msi/qa-artifact.selection.json" `
  --reader-root "$env:GITHUB_WORKSPACE/driver/.cadence-studio/retained-2008-data-readback" `
  --work "$env:RUNNER_TEMP/retained-qa-work" --output "$env:RUNNER_TEMP/retained-qa-evidence" `
  --bindings-template "$env:GITHUB_WORKSPACE/driver/.cadence-studio/retained-2008-msi/package-bindings.json" `
  --bindings-output "$env:RUNNER_TEMP/retained-package-bindings.MEASURED.json"
if ($LASTEXITCODE -ne 0) { throw 'Actual successful QA evidence is unavailable or differs' }

