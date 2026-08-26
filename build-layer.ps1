# Builds the shared dependency layer for ARQEDIA Lambdas.
# Docker, so the wheels match Lambda's runtime rather than this machine.

$ErrorActionPreference = "Stop"
$root  = $PSScriptRoot
$build = Join-Path $root "build"
$zip   = Join-Path $build "layer-docprocessing.zip"

if (Test-Path $build) { Remove-Item $build -Recurse -Force }
New-Item -ItemType Directory -Force -Path "$build\python" | Out-Null

Copy-Item "$root\lambda\layers\docprocessing\requirements.txt" $build

docker run --rm `
  --entrypoint /bin/sh `
  -v "${build}:/out" `
  public.ecr.aws/lambda/python:3.12 `
  -c "pip install -r /out/requirements.txt -t /out/python --quiet && chmod -R 755 /out/python"

if ($LASTEXITCODE -ne 0) { throw "docker build failed" }

Remove-Item "$build\requirements.txt"

Get-ChildItem "$build\python" -Recurse -Directory |
  Where-Object { $_.Name -eq "__pycache__" } |
  Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Compress-Archive -Path "$build\python" -DestinationPath $zip -Force
Write-Host "built $zip ($([math]::Round((Get-Item $zip).Length/1MB,1)) MB)" -ForegroundColor Green

