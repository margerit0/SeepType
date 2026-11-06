[CmdletBinding(SupportsShouldProcess = $true)]
param([switch] $Apply, [switch] $AllowDevelopment)

. (Join-Path $PSScriptRoot 'scripts/Common.ps1')
$package = Get-StudyPackage $PSScriptRoot -ForUninstall
$receiptPath = Resolve-StudyChild $package.Root 'install-receipt.json'
$receiptPresent = Test-Path -LiteralPath $receiptPath
$plan = [ordered]@{
    action = 'uninstall'; apply_requested = [bool]$Apply; product = $package.Manifest.product.name;
    version = $package.Manifest.product.version; target = (Get-StudyTarget $package.Manifest.product.version);
    receipt_present = $receiptPresent; registry_class = 'HKLM\Software\Classes\CLSID\' + $script:StudyClassGuid;
    profile_guid = $package.Manifest.product.guids.language_profile;
    delete_policy = 'Only recorded, unmodified package files inside the validated installation root';
    preserve_user_data = $true; preserve_unlisted_or_modified_files = $true;
    terminate_other_applications = $false; default_input_method_changed = $false;
    apply_command = '.\Uninstall.ps1 -Apply -AllowDevelopment'
}
$plan | ConvertTo-Json -Depth 10
if (-not $Apply) { return }
Assert-StudyApplyRequirements $package -AllowDevelopment:$AllowDevelopment
$receipt = Get-StudyReceipt $package
if (-not $PSCmdlet.ShouldProcess($package.Root, 'Stop this user/session StudyIME service, unregister its profile and remove recorded files')) { return }

$critical = @('bin/StudyIME.Service.exe', 'bin/StudyIME.Registrar.exe', 'bin/StudyIME.TSF.x64.dll')
if (@('copying', 'copied', 'unregistered', 'cleanup-pending') -notcontains $receipt.status) {
    foreach ($name in $critical) {
        $entry = @($package.Manifest.files | Where-Object { $_.path -eq $name })[0]
        $path = Resolve-StudyChild $package.Root $name
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or
            (Get-StudyHash $path) -ne $entry.sha256) {
            throw "Restore the original verified native file before unregistering: $name"
        }
    }
    Invoke-StudyNative $package.Root 'StudyIME.Service.exe' '--stop'
    # Even an interrupted registration is checked against the exact DLL owner.
    Invoke-StudyNative $package.Root 'StudyIME.Registrar.exe' '--unregister --apply'
    $receipt.registered = $false
    $receipt.status = 'unregistered'
    Write-StudyReceipt $package.Root $receipt
}

$support = @('Install.ps1', 'Uninstall.ps1', 'scripts/Common.ps1', 'product.json')
$retained = New-Object 'System.Collections.Generic.List[string]'
foreach ($file in $package.Manifest.files) {
    $path = Resolve-StudyChild $package.Root $file.path
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { continue }
    if ((Get-StudyHash $path) -ne $file.sha256) {
        $retained.Add($file.path); continue
    }
    if ($support -contains $file.path) { continue }
    try { Remove-Item -LiteralPath $path -ErrorAction Stop }
    catch { $retained.Add($file.path) }
}
if ($retained.Count) {
    $receipt.status = 'cleanup-pending'
    Write-StudyReceipt $package.Root $receipt
    throw ('Unregistered. Files are modified or still in use; close applications and retry. Preserved: ' + ($retained -join ', '))
}
Remove-StudyAppListEntry $package.Root
foreach ($relative in ($support + @('package-manifest.json', 'install-receipt.json'))) {
    $path = Resolve-StudyChild $package.Root $relative
    if (Test-Path -LiteralPath $path -PathType Leaf) { Remove-Item -LiteralPath $path }
}
Remove-StudyEmptyDirectories $package.Root @($package.Manifest.files | ForEach-Object { $_.path })
Write-Output 'StudyIME unregistered and recorded program files removed. User settings/data and unlisted files were preserved.'
