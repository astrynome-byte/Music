$recipe="$env:RUNNER_TEMP/selected-build-recipe"
[void][IO.Directory]::CreateDirectory($recipe)
foreach ($name in @('combined-2008-source','retained-2008-resume','retained-2008-data-readback')) {
  Copy-Item -LiteralPath "$env:GITHUB_WORKSPACE/driver/.cadence-studio/$name" -Destination "$recipe/$name" -Recurse
}

