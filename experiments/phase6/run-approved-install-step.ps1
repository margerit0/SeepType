# Run only after explicit user authorization. This wrapper does not self-elevate.
# The production scripts perform all identity, integrity and path validation.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateSet('install', 'uninstall')][string] $Action,
    [Parameter(Mandatory = $true)][string] $ResultDirectory,
    [switch] $ArchiveCopyFailure
)
$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$resultRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'results'))
$outputRoot = [IO.Path]::GetFullPath($ResultDirectory).TrimEnd('\')
if (-not $outputRoot.StartsWith($resultRoot.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Acceptance logs must stay below experiments/phase6/results.'
}
$version = (Get-Content -LiteralPath (Join-Path $repoRoot 'packaging/product.json') -Raw -Encoding UTF8 | ConvertFrom-Json).version
$installRoot = Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::ProgramFiles)) ('StudyIME/' + $version)
$packageRoot = Join-Path $repoRoot ('.cache/packaging/stage/StudyIME-' + $version)
$entry = if ($Action -eq 'install') { Join-Path $packageRoot 'Install.ps1' } else { Join-Path $installRoot 'Uninstall.ps1' }
$utf8 = New-Object Text.UTF8Encoding($false)
[void][IO.Directory]::CreateDirectory($outputRoot)
$result = [ordered]@{ action = $Action; entry = $entry; started_at = [DateTime]::UtcNow.ToString('o'); succeeded = $false }
try {
    if ($ArchiveCopyFailure) {
        if ($Action -ne 'uninstall') { throw 'Copy-failure recovery requires uninstall.' }
        . (Join-Path $installRoot 'scripts/Common.ps1')
        $ownedPackage = Get-StudyPackage $installRoot -ForUninstall
        $ownedReceipt = Get-StudyReceipt $ownedPackage
        if ($ownedReceipt.registered -or @('copying', 'copied') -notcontains $ownedReceipt.status) {
            throw 'This recovery is restricted to an unregistered copy-stage failure.'
        }
        $pendingPath = Resolve-StudyChild $installRoot 'install-receipt.json.tmp'
        $pendingReceipt = Get-Content -LiteralPath $pendingPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($pendingReceipt.product_id -ne $ownedReceipt.product_id -or
            $pendingReceipt.install_root -ne $ownedReceipt.install_root -or
            $pendingReceipt.manifest_sha256 -ne $ownedReceipt.manifest_sha256 -or $pendingReceipt.registered) {
            throw 'Pending recovery record does not belong to the failed installation.'
        }
    }
    & $entry -Apply -AllowDevelopment *>&1 | Out-File -LiteralPath (Join-Path $outputRoot ($Action + '.log')) -Encoding UTF8
    if ($ArchiveCopyFailure) {
        Assert-StudyNoReparse $installRoot
        $remaining = @(Get-ChildItem -LiteralPath $installRoot -Force)
        if ($remaining.Count -ne 1 -or $remaining[0].FullName -ne $pendingPath -or $remaining[0].PSIsContainer) {
            throw 'Unexpected files remain; preserve them for review.'
        }
        $archivedReceipt = Join-Path $outputRoot 'recovered-receipt-pending.json'
        Move-Item -LiteralPath $pendingPath -Destination $archivedReceipt
        Remove-Item -LiteralPath $installRoot
        $result.archived_pending_receipt = $archivedReceipt
    }
    $result.succeeded = $true
} catch {
    $result.error = $_.ToString()
    $result.script_stack = $_.ScriptStackTrace
} finally {
    $result.finished_at = [DateTime]::UtcNow.ToString('o')
    [IO.File]::WriteAllText((Join-Path $outputRoot ($Action + '-result.json')), ($result | ConvertTo-Json -Depth 8), $utf8)
}
if (-not $result.succeeded) { exit 1 }
