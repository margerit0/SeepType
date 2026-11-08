param(
    [string] $Common,
    [string] $Output
)
$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
if (-not $Common) { $Common = Join-Path $repoRoot 'packaging/windows/Common.ps1' }
if (-not $Output) { $Output = Join-Path $repoRoot 'experiments/phase6/results/receipt-io.json' }
. $Common
$testBase = Join-Path $repoRoot ('.cache/packaging/verification/receipt-' + [guid]::NewGuid().ToString('N'))
$testRoot = Join-Path $testBase ([string][char]0x6536 + [char]0x636e + ' path')
[void][IO.Directory]::CreateDirectory($testRoot)
$checks = New-Object 'System.Collections.Generic.List[object]'
$result = [ordered]@{
    recorded_at = [DateTime]::UtcNow.ToString('o'); powershell = $PSVersionTable.PSVersion.ToString();
    common_sha256 = Get-StudyHash $Common; test_directory = $testRoot; checks = $checks;
    system_install_executed = $false; tsf_registration_executed = $false
}
function Assert-Receipt([string] $Name, [bool] $Pass) {
    $checks.Add([ordered]@{ name = $Name; passed = $Pass })
    if (-not $Pass) { throw $Name }
}
$locked = $null
try {
    $receipt = [PSCustomObject]@{ schema_version = 1; status = 'copying'; registered = $false; failed = $false }
    $path = Join-Path $testRoot 'install-receipt.json'
    $pending = $path + '.tmp'
    Write-StudyReceipt $testRoot $receipt
    $read = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-Receipt 'create first receipt in a Unicode path with spaces' ($read.status -eq 'copying' -and -not (Test-Path -LiteralPath $pending))
    $receipt.status = 'copied'
    Write-StudyReceipt $testRoot $receipt
    $read = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-Receipt 'atomically replace an existing receipt without a backup path' ($read.status -eq 'copied' -and -not (Test-Path -LiteralPath $pending))
    $before = Get-StudyHash $path
    $locked = [IO.File]::Open($path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    $receipt.status = 'registration-pending'
    $receipt.failed = $true
    $rejected = $false
    try { Write-StudyReceipt $testRoot $receipt } catch { $rejected = $true }
    Assert-Receipt 'failed replacement preserves the last durable receipt' ($rejected -and (Get-StudyHash $path) -eq $before -and (Test-Path -LiteralPath $pending))
    $locked.Dispose()
    $locked = $null
    Write-StudyReceipt $testRoot $receipt
    $read = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-Receipt 'retry after a sharing violation persists failure state and consumes the pending file' ($read.status -eq 'registration-pending' -and $read.failed -and -not (Test-Path -LiteralPath $pending))
} catch {
    $result.error = $_.ToString()
    $result.script_stack = $_.ScriptStackTrace
} finally {
    if ($null -ne $locked) { $locked.Dispose() }
    $result.passed = @($checks | Where-Object { $_.passed }).Count
    $result.total = 4
    [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($Output)))
    [IO.File]::WriteAllText([IO.Path]::GetFullPath($Output), ($result | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
    $result | ConvertTo-Json -Depth 8
}
if ($result.passed -ne $result.total) { exit 1 }
