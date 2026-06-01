param(
    [string]$PackageDir = "dist\meeting-system-offline",
    [string]$ImageName = "meeting-system:offline",
    [string]$ZipPath = "dist\meeting-system-offline.zip",
    [switch]$SkipDocker
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$PackagePath = Join-Path $Root $PackageDir

if (Test-Path $PackagePath) {
    Remove-Item -Recurse -Force $PackagePath
}

New-Item -ItemType Directory -Force $PackagePath | Out-Null

$items = @(
    "app.py",
    "models.py",
    "ad_service.py",
    "requirements.txt",
    "rooms.json",
    "meeting.db",
    "Dockerfile",
    ".dockerignore",
    "README.md",
    "README_OFFLINE.md",
    "templates",
    "scripts"
)

foreach ($item in $items) {
    Copy-Item -Path (Join-Path $Root $item) -Destination $PackagePath -Recurse -Force
}

New-Item -ItemType Directory -Force (Join-Path $PackagePath "wheelhouse") | Out-Null

& (Join-Path $Root ".venv\Scripts\python.exe") -m pip download `
    --dest (Join-Path $PackagePath "wheelhouse") `
    --only-binary=:all: `
    --platform manylinux2014_x86_64 `
    --python-version 310 `
    --implementation cp `
    --abi cp310 `
    -r (Join-Path $Root "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "pip download failed" }

$DockerTar = Join-Path $PackagePath "meeting-system-docker.tar"
if (-not $SkipDocker) {
    $dockerAvailable = $false
    try {
        cmd /c "docker info >NUL 2>NUL"
        $dockerAvailable = ($LASTEXITCODE -eq 0)
    } catch {
        $dockerAvailable = $false
    }
    if ($dockerAvailable) {
        docker build -t $ImageName $Root
        if ($LASTEXITCODE -ne 0) { throw "docker build failed" }
        docker save -o $DockerTar $ImageName
        if ($LASTEXITCODE -ne 0) { throw "docker save failed" }
    } else {
        @"
Docker daemon 当前不可用，因此本次未生成 meeting-system-docker.tar。

处理方式：
1. 在开发机启动 Docker Desktop / Docker Engine。
2. 回到项目目录运行：
   powershell -ExecutionPolicy Bypass -File scripts\package_offline.ps1

或者在 Linux Docker 环境中运行：
   ./scripts/docker_build_save.sh
"@ | Set-Content -Encoding UTF8 (Join-Path $PackagePath "DOCKER_IMAGE_NOT_BUILT.txt")
        Write-Warning "Docker daemon unavailable; skipped docker image build."
    }
}

if (Test-Path (Join-Path $Root $ZipPath)) {
    Remove-Item -Force (Join-Path $Root $ZipPath)
}

Compress-Archive -Path (Join-Path $PackagePath "*") -DestinationPath (Join-Path $Root $ZipPath)

Write-Host "离线包已生成：$PackagePath"
Write-Host "压缩包已生成：$(Join-Path $Root $ZipPath)"
