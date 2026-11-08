param([string] $Common, [string] $Output)
$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
if (-not $Common) { $Common = Join-Path $repoRoot 'packaging/windows/Common.ps1' }
if (-not $Output) { $Output = Join-Path $repoRoot 'experiments/phase6/results/uninstall-registry-checks.json' }
. $Common
$fixtureId = [guid]::NewGuid().ToString('N')
$fixtureBase = 'Software\StudyIME.UninstallTests'
$user = [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::CurrentUser, [Microsoft.Win32.RegistryView]::Registry64)
$parent = $user.CreateSubKey($fixtureBase + '\' + $fixtureId)
$checks = New-Object 'System.Collections.Generic.List[object]'
$result = [ordered]@{
    recorded_at = [DateTime]::UtcNow.ToString('o'); powershell = $PSVersionTable.PSVersion.ToString();
    common_sha256 = Get-StudyHash $Common; registry_fixture = 'HKCU\' + $fixtureBase + '\' + $fixtureId;
    system_install_executed = $false; tsf_registration_executed = $false; checks = $checks
}
function Assert-Check([string] $Name, [bool] $Pass) {
    $checks.Add([ordered]@{ name = $Name; passed = $Pass })
    if (-not $Pass) { throw $Name }
}
function Create-FixtureKey([string] $Relative, [string] $ValueName = '', [string] $Value = '') {
    $key = $parent.CreateSubKey($script:StudyClassGuid + $Relative)
    try { if ($ValueName) { $key.SetValue($ValueName, $Value) } }
    finally { $key.Dispose() }
}
function Test-FixtureKey([string] $Relative) {
    $key = $parent.OpenSubKey($script:StudyClassGuid + $Relative)
    if ($null -eq $key) { return $false }
    $key.Dispose()
    return $true
}
function Clear-ProductFixture {
    # This fixed GUID is only below the fresh HKCU fixture, never the TSF tree.
    $parent.DeleteSubKeyTree($script:StudyClassGuid, $false)
}
try {
    $neighbor = $parent.CreateSubKey('unrelated-product')
    try { $neighbor.SetValue('keep', 'unchanged') } finally { $neighbor.Dispose() }
    foreach ($relative in @(
        '\Category\Category\{046B8C80-1647-40F7-9B21-B93B81AABC1B}',
        '\Category\Category\{34745C63-B2F0-4784-8B67-5E12C8701A31}',
        '\Category\Category\{49D2F9CF-1F5E-11D7-A6D3-00065B84435C}',
        '\Category\Category\{CCF05DD7-4A87-11D7-A6E2-00065B84435C}',
        ('\Category\Item\' + $script:StudyClassGuid), '\LanguageProfile\0x00000804')) {
        Create-FixtureKey $relative
    }
    $removed = Remove-StudyEmptyTipBranch $parent
    Assert-Check 'remove the observed empty TSF containers' ($removed -and -not (Test-FixtureKey ''))
    $neighbor = $parent.OpenSubKey('unrelated-product')
    try { Assert-Check 'preserve a neighboring product branch' ($neighbor.GetValue('keep') -eq 'unchanged') }
    finally { $neighbor.Dispose() }
    Assert-Check 'repeating cleanup is harmless' (-not (Remove-StudyEmptyTipBranch $parent))

    Create-FixtureKey '' 'owner' 'preserve'
    $blocked = $false
    try { [void](Remove-StudyEmptyTipBranch $parent) } catch { $blocked = $true }
    $key = $parent.OpenSubKey($script:StudyClassGuid)
    try { Assert-Check 'preserve registry values' ($blocked -and $key.GetValue('owner') -eq 'preserve') }
    finally { $key.Dispose() }
    Clear-ProductFixture

    Create-FixtureKey '\Category\Item'
    Create-FixtureKey '\LanguageProfile\0x00000804\{C126F14A-E78D-57FF-910F-205A393AE9D9}' 'Enable' '1'
    $blocked = $false
    try { [void](Remove-StudyEmptyTipBranch $parent) } catch { $blocked = $true }
    Assert-Check 'active profile prevents all cleanup, including earlier empty siblings' ($blocked -and (Test-FixtureKey '\Category\Item') -and (Test-FixtureKey '\LanguageProfile\0x00000804\{C126F14A-E78D-57FF-910F-205A393AE9D9}'))
    Clear-ProductFixture

    Create-FixtureKey '\UnfamiliarEmptyBranch'
    $blocked = $false
    try { [void](Remove-StudyEmptyTipBranch $parent) } catch { $blocked = $true }
    Assert-Check 'preserve unfamiliar empty branches' ($blocked -and (Test-FixtureKey '\UnfamiliarEmptyBranch'))
    Clear-ProductFixture

    Create-FixtureKey ''
    $readOnly = $user.OpenSubKey($fixtureBase + '\' + $fixtureId)
    $blocked = $false
    try { [void](Remove-StudyEmptyTipBranch $readOnly) } catch { $blocked = $true }
    finally { $readOnly.Dispose() }
    Assert-Check 'a write failure preserves the branch for retry' ($blocked -and (Test-FixtureKey ''))
    Assert-Check 'retry after a write failure completes cleanup' ((Remove-StudyEmptyTipBranch $parent) -and -not (Test-FixtureKey ''))
} catch {
    $result.error = $_.ToString()
    $result.script_stack = $_.ScriptStackTrace
} finally {
    $parent.Dispose()
    $testBase = $user.OpenSubKey($fixtureBase, $true)
    try { $testBase.DeleteSubKeyTree($fixtureId, $false) } finally { $testBase.Dispose() }
    $testBase = $user.OpenSubKey($fixtureBase)
    $emptyBase = $false
    try { $emptyBase = $testBase.ValueCount -eq 0 -and $testBase.SubKeyCount -eq 0 } finally { $testBase.Dispose() }
    if ($emptyBase) { $user.DeleteSubKey($fixtureBase, $false) }
    $user.Dispose()
    $result.passed = @($checks | Where-Object { $_.passed }).Count
    $result.total = 8
    [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($Output)))
    [IO.File]::WriteAllText([IO.Path]::GetFullPath($Output), ($result | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
    $result | ConvertTo-Json -Depth 8
}
if ($result.passed -ne $result.total) { exit 1 }
