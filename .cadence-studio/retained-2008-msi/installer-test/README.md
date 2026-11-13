# Retained2008 installer qualification — prepared, not executed

The wrapper does not build an application or rewrite its historical build
result. It invokes `upstream/Test-MsiInstall.ps1`, copied byte-for-byte from
source `a2b7abaf045a8f3cb84ec2953d9e0e51b9e78903`, SHA256
`77c25db2996ddf85f302ef59f78ca842580c695abe5a75692b4d94d85c7f6a4c`.
The original helper is self-contained PowerShell and Windows Installer COM;
it needs no Python, CMake, compiler, source tree, or Qt SDK for installation QA.
This preparation has parsed PowerShell and audited source locally; it has not
installed an MSI or launched Windows here.

The wrapper first requires disposable hosted Windows x64. It checks original
CI source95cebb22fe6cbde22919c94f2b480bd14c3eb8de, clean Build.ps1 result, and the
retained EXE SHA256
`13cd4e6d2f408d2e64b187d4c3bff1188ff4192ac7b670d3a12373bbeb37f6cd`.
The unchanged producer result's historical executable path is kept as data;
the explicit RetainedStageExecutablePath supplies its relocated, hash-matched
file. Input/output paths remain local, without reparse points, under
RUNNER_TEMP. Output must be new.

Before installation, read-only MSI COM checks product4.7.6.2008, x64, Cadence
ProductName, ProductCode `{CA4AC56B-9ED9-568F-9F5A-0D9475D4CC26}` and UpgradeCode
`{319B992F-470A-465B-9A79-6B0CBFC7D6C7}`. ProductCode is the RFC4122 UUIDv5 of
namespace `2e899094-116c-4518-8f13-94847281ff71` and exact name
`CadenceStudio-4.7.6.2008`. The original source helper separately refuses any
already-installed Cadence product before attempting the new installation.
It uninstalls only the exact ProductCode that it has attempted to install.

A genuine read-only stage notice report must have passed for the same EXE.
The source helper verifies every listed installed notice against that original
report, verifies installed EXE identity and independent MSI identity, checks
there is no installed bin/icuuc.dll, runs the installed CLI with SDK paths
removed, and uninstalls the exact new product. The outer wrapper requires
install0/CLI0/uninstall0 and no reboot request; a source-helper acceptance of
3010 does not qualify this stricter wrapper. Original MSI/build-result/notice
report/retained EXE hashes must stay unchanged. Exact original JSON copies and
the complete inner report are retained with the wrapper receipt.

## Installed GUI dependencies

For the installed GUI observation, pass both:

- `GuiWrapperPath`: byte-exact sourcea2b7 `scripts/windows/Run-CleanGuiProbe.ps1`,
  SHA256 `8a5f7d237c4ebf452ca347fab7c5dfc612bc7b457036e541cbd5df635902c68d`.
- `GuiProbePath`: reviewed driver `Test-ReadyGui.ps1`, SHA256
  `c3c3223e9dcb676db7da2df5502232d919ebeecc1f53dc43c7607b1d9a8e737f`.

`Test-ReadyGui.ps1` expects the separately compiled Windows SDK observer at
`RUNNER_TEMP/combined-ui-probe/UiReadyProbe.exe`. Its source is `UiReadyProbe.cpp`
from the reviewed driver, compiled only for QA with MSVC2022/SDK26100 and
ole32/oleaut32/user32/uuid. The source and generated observer are QA inputs;
they are not expected in installed/bin. The wrapper sets the expected EXE
SHA environment only for the test and restores its previous value afterward.
The original Run-CleanGuiProbe starts a separate PowerShell process and
restricts PATH to installed/bin plus System32 before executing the probe.
The observer is identified by its actual SHA in the retained report.

GUI success requires the original report's real startup observation and clean
close0, with no forced app or observer. This covers Home/Intro only, with the
profile scope reported by the source probe. It is not a first-launch wizard,
editing, MIDI, musical playback, human listening, or consumer Windows test.

```powershell
& "$recipe/installer-test/Test-Retained2008Installer.ps1" `
  -MsiPath $realMsi `
  -StageBuildResultPath $originalBuildResult `
  -RetainedStageExecutablePath "$restoredStage/bin/CadenceStudio4.exe" `
  -StageNoticeReportPath $actualNoticeReport `
  -OutputDirectory "$env:RUNNER_TEMP/retained2008-installer-qa" `
  -GuiWrapperPath "$restoredSource/scripts/windows/Run-CleanGuiProbe.ps1" `
  -GuiProbePath "$reviewedDriver/Test-ReadyGui.ps1" `
  -RequireGui
```

Without the two GUI parameters, the result can only be
`passed-retained2008-msi-CLI-only-GUI-unqualified`; experimental installer
qualification remains false. `-RequireGui` refuses that omission before any
install. Even an installed-GUI success always leaves final_gift_qualified=false:
that decision also needs the wider project qualification. Recipients install
the MSI through Windows; they do not run these developer/CI scripts or need
their tools.

Keep this namespace's `.gitattributes` when publishing the recipe so Windows
checkout cannot change the byte-pinned original helper's line endings.
