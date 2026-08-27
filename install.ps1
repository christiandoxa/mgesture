[CmdletBinding()]
param(
    [string]$Release = $env:MGESTURE_RELEASE,
    [switch]$Uninstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
if ([string]::IsNullOrWhiteSpace($Release)) { $Release = "latest" }
$Repository = if ($env:MGESTURE_GITHUB_REPOSITORY) { $env:MGESTURE_GITHUB_REPOSITORY } else { "christiandoxa/mgesture" }
$Base = $env:MGESTURE_RELEASE_BASE_URL
$Root = if ($env:MGESTURE_INSTALL_DIR) { $env:MGESTURE_INSTALL_DIR } else { Join-Path $env:LOCALAPPDATA "Programs\Mgesture" }
$Bin = if ($env:MGESTURE_BIN_DIR) { $env:MGESTURE_BIN_DIR } else { Join-Path $Root "bin" }
$Temp = Join-Path ([System.IO.Path]::GetTempPath()) ("mgesture-install-" + [Guid]::NewGuid().ToString("N"))

function Fail([string]$Message) { throw "mgesture installer: $Message" }
function Get-Download([string]$Source, [string]$Destination) {
    if ($Source.StartsWith("file://")) { Copy-Item -LiteralPath $Source.Substring(7) -Destination $Destination; return }
    if (Test-Path -LiteralPath $Source) { Copy-Item -LiteralPath $Source -Destination $Destination; return }
    Invoke-WebRequest -UseBasicParsing -Uri $Source -OutFile $Destination
}
function Get-Digest([string]$Path) { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Get-Expected([string]$Path, [string]$Asset) {
    foreach ($Line in Get-Content -LiteralPath $Path) {
        if ($Line -match "^([0-9a-fA-F]{64})\s+\*?$([regex]::Escape($Asset))$") { return $Matches[1].ToLowerInvariant() }
    }
    Fail "SHA256SUMS has no checksum for $Asset"
}
function Remove-Install {
    if (Test-Path -LiteralPath $Root) { Remove-Item -LiteralPath $Root -Recurse -Force }
    $Command = Join-Path $Bin "mgesture.cmd"
    if (Test-Path -LiteralPath $Command) { Remove-Item -LiteralPath $Command -Force }
    Write-Host "Removed releases from $Root; configuration and cache preserved."
}

if ($Uninstall -or $args -contains "--uninstall") { Remove-Install; exit 0 }
if ($Release -cne "latest" -and $Release -notmatch "^\d+\.\d+\.\d+(?:[+-][0-9A-Za-z.-]+)?$") { Fail "release must be latest or x.y.z" }
$Architecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
if ($Architecture -eq "X64") { $Target = "x86_64-pc-windows-msvc" } elseif ($Architecture -eq "Arm64") { $Target = "aarch64-pc-windows-msvc" } else { Fail "unsupported Windows architecture: $Architecture" }
if ([string]::IsNullOrWhiteSpace($Base)) {
    if ($Release -eq "latest") { $Base = "https://github.com/$Repository/releases/latest/download" }
    else { $Base = "https://github.com/$Repository/releases/download/v$Release" }
}

try {
    New-Item -ItemType Directory -Path $Temp | Out-Null
    Get-Download "$($Base.TrimEnd('/'))/SHA256SUMS" (Join-Path $Temp "SHA256SUMS")
    Get-Download "$($Base.TrimEnd('/'))/release-manifest.json" (Join-Path $Temp "release-manifest.json")
    Get-Download "$($Base.TrimEnd('/'))/release-manifest.tsv" (Join-Path $Temp "release-manifest.tsv")
    $Manifest = Get-Content -Raw -LiteralPath (Join-Path $Temp "release-manifest.json") | ConvertFrom-Json
    if ($Manifest.schema_version -ne 1) { Fail "unsupported JSON manifest schema" }
    $TargetEntry = $Manifest.targets.PSObject.Properties[$Target].Value
    if ($null -eq $TargetEntry -or [string]::IsNullOrWhiteSpace([string]$TargetEntry.asset)) { Fail "release has no matching target $Target" }
    $Asset = [string]$TargetEntry.asset
    if ($Asset -cnotmatch "^mgesture-$([regex]::Escape($Target))\.zip$") { Fail "release manifest asset mismatch for $Target" }
    $Tsv = Get-Content -LiteralPath (Join-Path $Temp "release-manifest.tsv")
    $Version = ($Tsv | Where-Object { $_ -like "# version`t*" } | Select-Object -First 1).Split("`t")[1]
    if ($Release -cne "latest" -and $Version -cne $Release) { Fail "requested release differs from manifest version" }
    $Commit = ($Tsv | Where-Object { $_ -like "# commit`t*" } | Select-Object -First 1).Split("`t")[1]
    if ($Commit -notmatch "^[0-9a-fA-F]{40}$") { Fail "manifest commit is not a full SHA" }
    if ((Get-Expected (Join-Path $Temp "SHA256SUMS") "release-manifest.json") -ne (Get-Digest (Join-Path $Temp "release-manifest.json"))) { Fail "JSON manifest checksum mismatch" }
    if ((Get-Expected (Join-Path $Temp "SHA256SUMS") "release-manifest.tsv") -ne (Get-Digest (Join-Path $Temp "release-manifest.tsv"))) { Fail "TSV manifest checksum mismatch" }
    $ExpectedAssetDigest = Get-Expected (Join-Path $Temp "SHA256SUMS") $Asset
    if ($TargetEntry.sha256.ToLowerInvariant() -ne $ExpectedAssetDigest) { Fail "manifest asset checksum does not match SHA256SUMS" }
    Get-Download "$($Base.TrimEnd('/'))/$Asset" (Join-Path $Temp $Asset)
    if ($ExpectedAssetDigest -ne (Get-Digest (Join-Path $Temp $Asset))) { Fail "asset checksum mismatch" }

    $Stage = Join-Path $Temp "stage"
    Expand-Archive -LiteralPath (Join-Path $Temp $Asset) -DestinationPath $Stage
    $StagedRoot = Join-Path $Stage "mgesture"
    $Binary = Join-Path $StagedRoot "bin\mgesture.exe"
    if (-not (Test-Path -LiteralPath $Binary)) { Fail "archive missing mgesture/bin/mgesture.exe" }
    $NativeLibrary = Join-Path $StagedRoot "runtime\mojo\mgesture_mojo.dll"
    if (-not (Test-Path -LiteralPath $NativeLibrary)) { Fail "archive missing runtime/mojo/mgesture_mojo.dll" }
    $VersionLine = (& $Binary --version).Trim()
    if ($VersionLine -notmatch "^mgesture ") { Fail "staged executable did not report mgesture" }
    if ($VersionLine.Substring(9) -cne $Version) { Fail "binary version differs from manifest" }
    $OldRoot = $env:MGESTURE_BUNDLE_ROOT
    try {
        $env:MGESTURE_BUNDLE_ROOT = $StagedRoot
        & $Binary self-test --headless --fake-input --engine mojo | Out-Null
        if ($LASTEXITCODE -ne 0) { Fail "staged native Mojo self-test failed" }
        & $Binary doctor --runtime --json | Out-Null
        if ($LASTEXITCODE -ne 0) { Fail "staged runtime diagnostics failed" }
    } finally { $env:MGESTURE_BUNDLE_ROOT = $OldRoot }

    New-Item -ItemType Directory -Force -Path (Join-Path $Root "releases"), $Bin | Out-Null
    $StagedRelease = Join-Path $Root "releases\.$Version.$PID"
    Move-Item -LiteralPath $StagedRoot -Destination $StagedRelease
    $Shim = Join-Path $Bin "mgesture.cmd"
    Set-Content -LiteralPath $Shim -Encoding ASCII -Value "@echo off`r`n`"$Root\current\bin\mgesture.exe`" %*`r`n"
    $Current = Join-Path $Root "current"
    $Backup = Join-Path $Root "current.previous"
    if (Test-Path -LiteralPath $Backup) { Remove-Item -LiteralPath $Backup -Recurse -Force }
    if (Test-Path -LiteralPath $Current) { Move-Item -LiteralPath $Current -Destination $Backup }
    try { Move-Item -LiteralPath $StagedRelease -Destination $Current } catch { if (Test-Path -LiteralPath $Backup) { Move-Item -LiteralPath $Backup -Destination $Current }; throw }
    $UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($env:MGESTURE_NO_PATH_UPDATE -notmatch "^(?i:1|true|yes)$" -and -not (($UserPath -split ';') -contains $Bin)) { [Environment]::SetEnvironmentVariable("Path", (($UserPath.TrimEnd(';') + ';' + $Bin).Trim(';')), "User") }
    Write-Host "mgesture $Version installed successfully."
    Write-Host "Open a new PowerShell, then start it with: mgesture"
    Write-Host "The first launch includes a safe interactive tutorial."
    Write-Host "Optional calibration: mgesture calibrate"
} finally {
    if (Test-Path -LiteralPath $Temp) { Remove-Item -LiteralPath $Temp -Recurse -Force }
}
