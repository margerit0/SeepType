[CmdletBinding(SupportsShouldProcess = $true)]
param([switch] $Apply, [switch] $AllowDevelopment)

. (Join-Path $PSScriptRoot 'scripts/Common.ps1')
$package = Get-StudyPackage $PSScriptRoot
$target = Get-StudyTarget $package.Manifest.product.version
$plan = [ordered]@{
    action = 'install'; apply_requested = [bool]$Apply; product = $package.Manifest.product.name;
    version = $package.Manifest.product.version; source = $package.Root; target = $target;
    package_sha256 = $package.ManifestHash; files = @($package.Manifest.files).Count;
    architecture = 'x64'; registry_class = 'HKLM\Software\Classes\CLSID\' + $script:StudyClassGuid;
    language_profile = $package.Manifest.product.guids.language_profile; language_id = '0x0804';
    app_list_key = 'HKLM\' + $script:StudyUninstallKey;
    data_directory = (Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)) 'StudyIME');
    default_input_method_changed = $false; current_profile_activated = $false;
    automatic_start = 'On TSF activation, for this user and logon session';
    release_ready = $package.Manifest.release_ready; release_blockers = $package.Manifest.release_blockers;
    apply_command = '.\Install.ps1 -Apply -AllowDevelopment'
}
$plan | ConvertTo-Json -Depth 12
if (-not $Apply) { return }
Assert-StudyApplyRequirements $package -AllowDevelopment:$AllowDevelopment
if (Test-Path -LiteralPath $target) { throw 'Target already exists. Review/uninstall that version before an initial installation; in-place upgrades are not implemented.' }
if ($null -ne (Get-StudyAppListEntry)) { throw 'A StudyIME installation is already recorded. Uninstall it before installing this preview.' }
if (-not $PSCmdlet.ShouldProcess($target, 'Copy StudyIME, prepare user data, register its zh-CN TSF profile and app-list entry')) { return }

[void][IO.Directory]::CreateDirectory($target)
$receipt = [PSCustomObject]@{ schema_version = 1; product_id = $script:StudyProductId;
    install_root = $target; manifest_sha256 = $package.ManifestHash; status = 'copying'; registered = $false; failed = $false }
try {
    $recovery = @('package-manifest.json', 'scripts/Common.ps1', 'Uninstall.ps1', 'product.json')
    $copyOrder = $recovery + @($package.Manifest.files | Where-Object { $recovery -notcontains $_.path } | ForEach-Object { $_.path })
    foreach ($relative in $copyOrder) {
        $source = Resolve-StudyChild $package.Root $relative
        $destination = Resolve-StudyChild $target $relative
        [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination))
        Assert-StudyNoReparse $destination
        Copy-Item -LiteralPath $source -Destination $destination
        if ($relative -eq 'product.json') { Write-StudyReceipt $target $receipt }
    }
    $installed = Get-StudyPackage $target
    $receipt.status = 'copied'
    Write-StudyReceipt $target $receipt
    Invoke-StudyNative $target 'StudyIME.Service.exe' '--prepare-data'
    $receipt.status = 'registration-pending'
    Write-StudyReceipt $target $receipt
    Invoke-StudyNative $target 'StudyIME.Registrar.exe' '--register --apply'
    $receipt.registered = $true
    $receipt.status = 'registered'
    Write-StudyReceipt $target $receipt
    Set-StudyAppListEntry $installed
    $receipt.status = 'installed'
    Write-StudyReceipt $target $receipt
    Write-Output 'StudyIME installed. Select it explicitly in Windows when ready; the default input method was not changed.'
} catch {
    # Keep the verified payload and recovery receipt if any step fails. Never
    # erase a DLL that could still have a registration, and never remove data.
    $receipt.failed = $true  # Preserve the last durable stage for safe recovery.
    try { Write-StudyReceipt $target $receipt } catch { Write-Warning 'Could not update the recovery receipt.' }
    throw
}
