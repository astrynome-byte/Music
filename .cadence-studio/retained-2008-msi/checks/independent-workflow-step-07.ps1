$probe="$env:RUNNER_TEMP/combined-ui-probe"
[void][IO.Directory]::CreateDirectory($probe)
Push-Location $probe
try {
  & cl.exe /nologo /std:c++17 /utf-8 /EHsc /MD `
    "$env:GITHUB_WORKSPACE/driver/.cadence-studio/combined-2008-source/UiReadyProbe.cpp" `
    /Fe:UiReadyProbe.exe /link ole32.lib oleaut32.lib user32.lib uuid.lib
  if ($LASTEXITCODE -ne 0) { throw 'Standalone SDK observer did not compile' }
} finally { Pop-Location }

