# Shared implementation for the StudyIME script installer. Loading this file
# only defines functions. System writes occur exclusively inside -Apply paths.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script:StudyProductId = 'StudyIME.InputMethod'
$script:StudyProductGuid = '{D89859C5-5A51-53E6-8199-DF3407D2908B}'
$script:StudyClassGuid = '{FEB10355-3C08-5342-B75C-5873F1CA04DF}'
$script:StudyUninstallKey = 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\' + $script:StudyProductGuid

function Get-StudyHash([string] $Path) {
    # Managed SHA256 works in both Windows PowerShell 5.1 and PowerShell 7,
    # including hosts whose module paths do not expose Get-FileHash.
    $stream = [IO.File]::OpenRead($Path)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
    finally { $algorithm.Dispose(); $stream.Dispose() }
}

function Assert-StudyNoReparse([string] $Path) {
    $cursor = [IO.Path]::GetFullPath($Path)
    while ($cursor) {
        if (Test-Path -LiteralPath $cursor) {
            $item = Get-Item -LiteralPath $cursor -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Reparse points are not accepted in installer paths: $cursor"
            }
        }
        $parent = [IO.Path]::GetDirectoryName($cursor.TrimEnd('\'))
        if ($parent -eq $cursor) { break }
        $cursor = $parent
    }
}

function Resolve-StudyChild([string] $Root, [string] $Relative) {
    if ([string]::IsNullOrWhiteSpace($Relative) -or $Relative.Contains('\') -or $Relative.StartsWith('/')) {
        throw "Invalid manifest path: $Relative"
    }
    foreach ($part in $Relative.Split('/')) {
        if (-not $part -or $part -eq '.' -or $part -eq '..' -or $part -match '[<>:"|?*\x00-\x1f]' -or
            $part -match '[. ]$' -or $part -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)') {
            throw "Unsafe manifest path: $Relative"
        }
    }
    $absoluteRoot = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    $path = [IO.Path]::GetFullPath((Join-Path $absoluteRoot ($Relative.Replace('/', '\'))))
    if (-not $path.StartsWith($absoluteRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Manifest path escaped the package root: $Relative"
    }
    Assert-StudyNoReparse $path
    return $path
}

function Get-StudyTreeFiles([string] $Root) {
    # Enumerate a directory only after rejecting its reparse attribute.
    Assert-StudyNoReparse $Root
    $queue = New-Object 'System.Collections.Generic.Queue[string]'
    $queue.Enqueue([IO.Path]::GetFullPath($Root))
    while ($queue.Count) {
        $directory = $queue.Dequeue()
        foreach ($item in Get-ChildItem -LiteralPath $directory -Force) {
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Unexpected reparse point: $($item.FullName)"
            }
            if ($item.PSIsContainer) { $queue.Enqueue($item.FullName) }
            else { $item.FullName }
        }
    }
}

function Get-StudyPackage([string] $Root, [switch] $ForUninstall) {
    $absolute = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    Assert-StudyNoReparse $absolute
    $manifestPath = Resolve-StudyChild $absolute 'package-manifest.json'
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($manifest.schema_version -ne 1 -or $manifest.product.id -ne $script:StudyProductId -or
        $manifest.product.guids.product -ne $script:StudyProductGuid.Trim('{}') -or
        $manifest.product.guids.text_service -ne $script:StudyClassGuid.Trim('{}') -or
        $manifest.product.install_folder -ne 'StudyIME' -or $manifest.product.architecture -ne 'x64' -or
        $manifest.product.version -notmatch '^\d+\.\d+\.\d+(?:-[a-z]+\.\d+)?$' -or
        @($manifest.files).Count -eq 0) {
        throw 'Unrecognized StudyIME package identity or format.'
    }
    $names = @{}
    foreach ($file in $manifest.files) {
        $path = Resolve-StudyChild $absolute $file.path
        if ($names.ContainsKey($file.path) -or $file.path -eq 'package-manifest.json' -or
            $file.path -eq 'install-receipt.json' -or $file.sha256 -notmatch '^[0-9a-f]{64}$' -or $file.bytes -lt 0) {
            throw "Invalid or duplicate manifest entry: $($file.path)"
        }
        $names[$file.path] = $true
        if (-not $ForUninstall) {
            if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or
                (Get-Item -LiteralPath $path).Length -ne $file.bytes -or
                (Get-StudyHash $path) -ne $file.sha256) {
                throw "Package integrity failure: $($file.path)"
            }
        }
    }
    foreach ($required in @('product.json', 'Install.ps1', 'Uninstall.ps1', 'scripts/Common.ps1',
        'bin/StudyIME.TSF.x64.dll', 'bin/StudyIME.Service.exe', 'bin/StudyIME.Registrar.exe', 'bin/StudyIME.Settings.exe', 'bin/rime.dll')) {
        if (-not $names.ContainsKey($required)) { throw "Required package file is missing: $required" }
    }
    if (-not $ForUninstall) {
        foreach ($file in Get-StudyTreeFiles $absolute) {
            $relative = $file.Substring($absolute.Length + 1).Replace('\', '/')
            if ($relative -ne 'package-manifest.json' -and $relative -ne 'install-receipt.json' -and -not $names.ContainsKey($relative)) {
                throw "Unlisted package file: $relative"
            }
        }
    }
    return [PSCustomObject]@{ Root = $absolute; Manifest = $manifest; ManifestPath = $manifestPath;
        ManifestHash = (Get-StudyHash $manifestPath) }
}

function Get-StudyTarget([string] $Version) {
    if ($Version -notmatch '^\d+\.\d+\.\d+(?:-[a-z]+\.\d+)?$') { throw 'Invalid product version.' }
    $programFiles = [Environment]::GetFolderPath([Environment+SpecialFolder]::ProgramFiles)
    $base = [IO.Path]::GetFullPath((Join-Path $programFiles 'StudyIME'))
    $target = [IO.Path]::GetFullPath((Join-Path $base $Version))
    if (-not $target.StartsWith($base + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid install target.' }
    Assert-StudyNoReparse $target
    return $target
}

function Test-StudyAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Assert-StudyApplyRequirements($Package, [switch] $AllowDevelopment) {
    if (-not [Environment]::Is64BitProcess -or -not [Environment]::Is64BitOperatingSystem) {
        throw 'Use 64-bit PowerShell on Windows 11 x64.'
    }
    if (-not (Test-StudyAdministrator)) { throw 'Applying an installation or uninstallation requires an elevated PowerShell window.' }
    $build = [int]([Microsoft.Win32.Registry]::GetValue('HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion', 'CurrentBuildNumber', '0'))
    if ($build -lt $Package.Manifest.product.minimum_windows_build) { throw 'This package requires Windows 11.' }
    if (-not $Package.Manifest.release_ready -and -not $AllowDevelopment) {
        throw 'This is an unreviewed developer preview. Explicit -AllowDevelopment is required for a local development installation.'
    }
}

function Invoke-StudyNative([string] $Root, [string] $Name, [string] $Arguments) {
    $path = Resolve-StudyChild $Root ('bin/' + $Name)
    $start = New-Object Diagnostics.ProcessStartInfo
    $start.FileName = $path
    $start.Arguments = $Arguments  # Only fixed internal arguments, never file/user text.
    $start.WorkingDirectory = $Root
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    [void] $start.EnvironmentVariables.Remove('STUDYIME_DEV_SESSION')
    [void] $start.EnvironmentVariables.Remove('STUDYIME_DEV_DATA_ROOT')
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $start
    try {
        if (-not $process.Start()) { throw "Could not start $Name" }
        $output = $process.StandardOutput.ReadToEndAsync()
        $errorOutput = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(90000)) {
            $process.Kill()  # Only the child that this invocation just started.
            $process.WaitForExit()
            throw "$Name exceeded the installer operation timeout."
        }
        if ($process.ExitCode -ne 0) { throw "$Name failed ($($process.ExitCode)): $($errorOutput.Result)" }
    } finally { $process.Dispose() }
}

function Write-StudyReceipt([string] $Root, $Receipt) {
    $path = Resolve-StudyChild $Root 'install-receipt.json'
    $pending = Resolve-StudyChild $Root 'install-receipt.json.tmp'
    $utf8 = New-Object Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($pending, ($Receipt | ConvertTo-Json -Depth 10), $utf8)
    # Windows PowerShell 5.1 coerces $null to an empty System.String in this
    # overload. NullString preserves the null backup path required by File.Replace.
    if (Test-Path -LiteralPath $path) { [IO.File]::Replace($pending, $path, [NullString]::Value) }
    else { [IO.File]::Move($pending, $path) }
}

function Get-StudyReceipt($Package) {
    $path = Resolve-StudyChild $Package.Root 'install-receipt.json'
    $receipt = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
    $target = Get-StudyTarget $Package.Manifest.product.version
    if ($receipt.schema_version -ne 1 -or $receipt.product_id -ne $script:StudyProductId -or
        $receipt.manifest_sha256 -ne $Package.ManifestHash -or
        $receipt.install_root -ne $target -or $Package.Root -ne $target) {
        throw 'The installation receipt does not match this product, version, path, and manifest.'
    }
    return $receipt
}

function Remove-StudyEmptyTipBranch([Microsoft.Win32.RegistryKey] $Parent) {
    # TSF removes registrations but can leave these empty containers in both
    # registry views. Inspect the complete product branch before deleting any
    # key; a value or an unfamiliar child means that the branch is preserved.
    $allowed = @(
        '', 'Category', 'Category\Category', 'Category\Item',
        ('Category\Item\' + $script:StudyClassGuid),
        'Category\Category\{046B8C80-1647-40F7-9B21-B93B81AABC1B}',
        'Category\Category\{34745C63-B2F0-4784-8B67-5E12C8701A31}',
        'Category\Category\{49D2F9CF-1F5E-11D7-A6D3-00065B84435C}',
        'Category\Category\{CCF05DD7-4A87-11D7-A6E2-00065B84435C}',
        'LanguageProfile', 'LanguageProfile\0x00000804'
    )
    $paths = New-Object 'System.Collections.Generic.List[string]'
    $visit = {
        param([Microsoft.Win32.RegistryKey] $Key, [string] $Relative)
        if ($allowed -notcontains $Relative -or $Key.ValueCount -ne 0) {
            throw "Preserved nonempty or unfamiliar StudyIME TIP registry branch: $Relative"
        }
        foreach ($name in $Key.GetSubKeyNames()) {
            $child = $Key.OpenSubKey($name)
            if ($null -eq $child) { throw 'StudyIME TIP registry changed during inspection.' }
            try {
                $relativeChild = if ($Relative) { $Relative + '\' + $name } else { $name }
                & $visit $child $relativeChild
            } finally { $child.Dispose() }
        }
        $paths.Add($Relative)
    }
    $tip = $Parent.OpenSubKey($script:StudyClassGuid)
    if ($null -eq $tip) { return $false }
    try { & $visit $tip '' } finally { $tip.Dispose() }
    # Children precede parents. DeleteSubKey is deliberately nonrecursive and
    # every key is checked again immediately before removal.
    foreach ($relative in $paths) {
        $path = $script:StudyClassGuid
        if ($relative) { $path += '\' + $relative }
        $key = $Parent.OpenSubKey($path)
        if ($null -eq $key) { continue }
        try {
            if ($key.ValueCount -ne 0 -or $key.SubKeyCount -ne 0) {
                throw "StudyIME TIP registry changed during cleanup; preserved: $path"
            }
        } finally { $key.Dispose() }
        $Parent.DeleteSubKey($path, $false)
    }
    return $true
}

function Remove-StudyEmptyTipKeys($Package) {
    $receipt = Get-StudyReceipt $Package
    if ($receipt.registered -or @('unregistered', 'cleanup-pending') -notcontains $receipt.status) {
        throw 'Empty TIP cleanup requires a verified, unregistered installation receipt.'
    }
    foreach ($view in @([Microsoft.Win32.RegistryView]::Registry64, [Microsoft.Win32.RegistryView]::Registry32)) {
        $machine = [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::LocalMachine, $view)
        try {
            $class = $machine.OpenSubKey('Software\Classes\CLSID\' + $script:StudyClassGuid)
            if ($null -ne $class) {
                $class.Dispose()
                throw 'StudyIME COM class still exists; complete native unregistration first.'
            }
            $parent = $machine.OpenSubKey('Software\Microsoft\CTF\TIP', $true)
            if ($null -eq $parent) { continue }
            try { [void](Remove-StudyEmptyTipBranch $parent) }
            finally { $parent.Dispose() }
        } finally { $machine.Dispose() }
    }
}

function Get-StudyAppListEntry {
    $machine = [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::LocalMachine, [Microsoft.Win32.RegistryView]::Registry64)
    try {
        $key = $machine.OpenSubKey($script:StudyUninstallKey)
        if ($null -eq $key) { return $null }
        try { return [string]$key.GetValue('InstallLocation', '') }
        finally { $key.Dispose() }
    } finally { $machine.Dispose() }
}

function Set-StudyAppListEntry($Package) {
    $machine = [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::LocalMachine, [Microsoft.Win32.RegistryView]::Registry64)
    try {
        $key = $machine.CreateSubKey($script:StudyUninstallKey)
        try {
            $key.SetValue('DisplayName', $Package.Manifest.product.name + ' (StudyIME developer preview)')
            $key.SetValue('DisplayVersion', $Package.Manifest.product.version)
            $key.SetValue('Publisher', 'StudyIME contributors')
            $key.SetValue('InstallLocation', $Package.Root)
            $key.SetValue('DisplayIcon', '"' + (Resolve-StudyChild $Package.Root 'bin/StudyIME.Settings.exe') + '",0')
            $hostPath = Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::System)) 'WindowsPowerShell\v1.0\powershell.exe'
            $command = '"' + $hostPath + '" -NoProfile -File "' + (Resolve-StudyChild $Package.Root 'Uninstall.ps1') + '" -Apply -AllowDevelopment'
            $key.SetValue('UninstallString', $command)
            $key.SetValue('NoModify', 1, [Microsoft.Win32.RegistryValueKind]::DWord)
            $key.SetValue('NoRepair', 1, [Microsoft.Win32.RegistryValueKind]::DWord)
        } finally { $key.Dispose() }
    } finally { $machine.Dispose() }
}

function Remove-StudyAppListEntry([string] $Root) {
    $location = Get-StudyAppListEntry
    if ($null -eq $location) { return }
    if ($location -ne $Root) { throw 'The app-list entry belongs to another installation.' }
    $machine = [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::LocalMachine, [Microsoft.Win32.RegistryView]::Registry64)
    try { $machine.DeleteSubKeyTree($script:StudyUninstallKey, $false) }
    finally { $machine.Dispose() }
}

function Remove-StudyEmptyDirectories([string] $Root, $RelativeFiles) {
    # No recursive deletion: only derived, verified directories that are empty.
    $directories = @{}
    foreach ($relative in $RelativeFiles) {
        $path = [IO.Path]::GetDirectoryName((Resolve-StudyChild $Root $relative))
        while ($path -and $path.StartsWith($Root + '\', [StringComparison]::OrdinalIgnoreCase)) {
            $directories[$path] = $true
            $path = [IO.Path]::GetDirectoryName($path)
        }
    }
    foreach ($directory in ($directories.Keys | Sort-Object Length -Descending)) {
        Assert-StudyNoReparse $directory
        if ((Test-Path -LiteralPath $directory) -and @(Get-ChildItem -LiteralPath $directory -Force).Count -eq 0) {
            Remove-Item -LiteralPath $directory
        }
    }
    Assert-StudyNoReparse $Root
    if ((Test-Path -LiteralPath $Root) -and @(Get-ChildItem -LiteralPath $Root -Force).Count -eq 0) {
        Remove-Item -LiteralPath $Root
    }
}
