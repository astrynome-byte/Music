python -I -B "$env:GITHUB_WORKSPACE/driver/.cadence-studio/retained-2008-data-readback/read_existing_stage.py" `
  --work "$env:RUNNER_TEMP/retained-data-work" --output "$env:RUNNER_TEMP/retained-data-originals"
if ($LASTEXITCODE -ne 0) { throw 'Original partial-stage authentication failed' }
python -I -B "$env:GITHUB_WORKSPACE/driver/.cadence-studio/retained-2008-resume/Restore-RetainedRuntime.py" `
  --reader-root "$env:GITHUB_WORKSPACE/driver/.cadence-studio/retained-2008-data-readback" `
  --data-work "$env:RUNNER_TEMP/retained-data-work" --data-output "$env:RUNNER_TEMP/retained-data-originals" `
  --bundle "$env:RUNNER_TEMP/cadence-stage-delivery" --stage "$env:RUNNER_TEMP/stage-cadence" `
  --report "$env:RUNNER_TEMP/retained-restoration.json"
if ($LASTEXITCODE -ne 0) { throw 'Exact 2712-file runtime restoration failed' }

