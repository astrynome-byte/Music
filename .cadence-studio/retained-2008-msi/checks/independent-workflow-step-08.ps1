$msi="$env:GITHUB_WORKSPACE/driver/.cadence-studio/retained-2008-msi"
& "$msi/installer-test/Test-Retained2008Installer.ps1" `
  -MsiPath "$env:RUNNER_TEMP/retained2008-package/deliverables/CadenceStudio-4.7.6-cadence.2008-x86_64.msi" `
  -StageBuildResultPath "$env:RUNNER_TEMP/cadence-stage-delivery/cadence-build-result.json" `
  -RetainedStageExecutablePath "$env:RUNNER_TEMP/stage-cadence/bin/CadenceStudio4.exe" `
  -StageNoticeReportPath "$env:RUNNER_TEMP/retained-qa-evidence/qa-stage-notices/stage-notices-report.json" `
  -OutputDirectory "$env:RUNNER_TEMP/retained2008-installer-qa" `
  -GuiWrapperPath "$env:GITHUB_WORKSPACE/cadence-src/scripts/windows/Run-CleanGuiProbe.ps1" `
  -GuiProbePath "$env:GITHUB_WORKSPACE/driver/.cadence-studio/combined-2008-source/Test-ReadyGui.ps1" `
  -RequireGui

