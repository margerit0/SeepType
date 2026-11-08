# Authorized recovery for a receipt left by the earlier script-only installer.
# Reuses the production cleanup function; does not change installed manifests.
param([Parameter(Mandatory = $true)][string] $ResultDirectory, [switch] $RetryUninstall)
$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$resultBase = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'results')).TrimEnd('\')
$outputRoot = [IO.Path]::GetFullPath($ResultDirectory).TrimEnd('\')
if (-not $outputRoot.StartsWith($resultBase + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Recovery evidence must stay below experiments/phase6/results.'
}
. (Join-Path $repoRoot 'packaging/windows/Common.ps1')
$version = (Get-Content -LiteralPath (Join-Path $repoRoot 'packaging/product.json') -Raw -Encoding UTF8 | ConvertFrom-Json).version
$package = Get-StudyPackage (Get-StudyTarget $version) -ForUninstall
Assert-StudyApplyRequirements $package -AllowDevelopment
$receipt = Get-StudyReceipt $package
$result = [ordered]@{
    started_at = [DateTime]::UtcNow.ToString('o'); succeeded = $false;
    install_root = $package.Root; manifest_sha256 = $package.ManifestHash;
    common_sha256 = Get-StudyHash (Join-Path $repoRoot 'packaging/windows/Common.ps1');
    initial_receipt_status = $receipt.status
}
try {
    Remove-StudyEmptyTipKeys $package
    $result.succeeded = $true
    if ($RetryUninstall) {
        foreach ($relative in @('Uninstall.ps1', 'scripts/Common.ps1')) {
            $entry = @($package.Manifest.files | Where-Object { $_.path -eq $relative })[0]
            if ((Get-StudyHash (Resolve-StudyChild $package.Root $relative)) -ne $entry.sha256) {
                throw "Installed retry script changed: $relative"
            }
        }
        [void][IO.Directory]::CreateDirectory($outputRoot)
        try {
            & (Join-Path $package.Root 'Uninstall.ps1') -Apply -AllowDevelopment *>&1 |
                Out-File -LiteralPath (Join-Path $outputRoot 'uninstall-retry.log') -Encoding UTF8
            $result.uninstall_retry_succeeded = $true
        } catch {
            $result.uninstall_retry_succeeded = $false
            $result.uninstall_retry_error = $_.ToString()
        }
    }
} catch {
    $result.succeeded = $false
    $result.error = $_.ToString()
    $result.script_stack = $_.ScriptStackTrace
} finally {
    $result.finished_at = [DateTime]::UtcNow.ToString('o')
    [void][IO.Directory]::CreateDirectory($outputRoot)
    [IO.File]::WriteAllText((Join-Path $outputRoot 'empty-tip-cleanup.json'), ($result | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
}
if (-not $result.succeeded) { exit 1 }
