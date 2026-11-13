$driver="$env:GITHUB_WORKSPACE/driver/.cadence-studio/combined-2008-source"
& "$driver/Restore-Binaries.ps1" -Root $driver
& "$driver/Bootstrap.ps1" -DriverPath $driver -SourcePath "$env:GITHUB_WORKSPACE/cadence-src" -ResultPath "$env:RUNNER_TEMP/cadence-new-bootstrap.json"
python -I -B "$env:GITHUB_WORKSPACE/driver/.cadence-studio/retained-2008-resume/Bind-OriginalCiSource.py" `
  --source-root "$env:GITHUB_WORKSPACE/cadence-src" --bootstrap "$env:RUNNER_TEMP/cadence-new-bootstrap.json" `
  --output "$env:RUNNER_TEMP/retained-source-binding.json"
if ($LASTEXITCODE -ne 0) { throw 'Exact original compiled CI95 binding failed' }

