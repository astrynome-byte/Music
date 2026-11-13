choco install cmake --version=3.31.6 --allow-downgrade --yes --installargs 'ADD_CMAKE_TO_PATH=System'
if ($LASTEXITCODE -ne 0) { throw 'CMake installation failed' }
choco install ninja --version=1.11.1 --allow-downgrade --yes
if ($LASTEXITCODE -ne 0) { throw 'Ninja installation failed' }
choco install wixtoolset --version=3.14.1 --allow-downgrade --yes
if ($LASTEXITCODE -ne 0) { throw 'WiX installation failed' }
'C:\Program Files\CMake\bin' | Out-File -FilePath $env:GITHUB_PATH -Append
'C:\Program Files (x86)\WiX Toolset v3.14\bin' | Out-File -FilePath $env:GITHUB_PATH -Append

