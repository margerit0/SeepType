# Move only this task's caches after an explicit storage-location choice.
param([Parameter(Mandatory=$true)][string]$Destination)
$ErrorActionPreference = 'Stop'
$workspaceRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$cacheDestination = [System.IO.Path]::GetFullPath($Destination)
$workspacePrefix = $workspaceRoot.TrimEnd('\','/') + [System.IO.Path]::DirectorySeparatorChar
$destinationPrefix = $cacheDestination.TrimEnd('\','/') + [System.IO.Path]::DirectorySeparatorChar
if ($cacheDestination -eq [System.IO.Path]::GetPathRoot($cacheDestination)) { throw 'A volume root is not a cache directory' }
if (Test-Path -LiteralPath $cacheDestination) { throw 'Destination already exists; inspect it before any migration' }
$sourceRoot = [System.IO.Path]::GetFullPath((Join-Path $workspaceRoot '.cache/android'))
if (-not $sourceRoot.StartsWith($workspacePrefix, [System.StringComparison]::OrdinalIgnoreCase)) { throw 'Source escaped workspace' }
New-Item -ItemType Directory -Path $cacheDestination | Out-Null

function Move-VerifiedCache([string]$Source, [string]$Target) {
    $resolvedSource = [System.IO.Path]::GetFullPath($Source)
    $resolvedTarget = [System.IO.Path]::GetFullPath($Target)
    if (-not $resolvedSource.StartsWith($workspacePrefix, [System.StringComparison]::OrdinalIgnoreCase)) { throw 'Unapproved source' }
    if ($resolvedTarget -ne $cacheDestination -and -not $resolvedTarget.StartsWith($destinationPrefix, [System.StringComparison]::OrdinalIgnoreCase)) { throw 'Unapproved destination' }
    if (Test-Path -LiteralPath $resolvedSource) {
        if ((Get-Item -LiteralPath $resolvedSource).Attributes -band [System.IO.FileAttributes]::ReparsePoint) { throw 'Source is already a reparse point' }
        $migrationLog = Join-Path $cacheDestination 'migration-copy.log'
        & robocopy.exe $resolvedSource $resolvedTarget /E /COPY:DAT /DCOPY:DAT /R:1 /W:1 /XJ /NFL /NDL /NP /NJH /NJS "/LOG+:$migrationLog" | Out-Null
        if ($LASTEXITCODE -ge 8) { throw "Cache copy failed: $resolvedSource" }
        # Verify all original bytes before removing the original tree. No
        # directory enumeration is passed to another shell for deletion.
        $originalFiles = @(Get-ChildItem -LiteralPath $resolvedSource -File -Recurse -Force)
        foreach ($sourceFile in $originalFiles) {
            $relative = $sourceFile.FullName.Substring($resolvedSource.Length).TrimStart('\','/')
            $targetFile = Join-Path $resolvedTarget $relative
            if ((Get-Item -LiteralPath $targetFile).Length -ne $sourceFile.Length -or
                (Get-FileHash -LiteralPath $sourceFile.FullName -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $targetFile -Algorithm SHA256).Hash) {
                throw "Cache verification failed: $relative"
            }
        }
        # Both absolute endpoints were checked above; the source was not a link.
        Remove-Item -LiteralPath $resolvedSource -Recurse -Force
        Write-Output "Verified and moved $($originalFiles.Count) files: $resolvedSource"
    } else {
        New-Item -ItemType Directory -Path $resolvedTarget -Force | Out-Null
        New-Item -ItemType Directory -Path ([System.IO.Path]::GetDirectoryName($resolvedSource)) -Force | Out-Null
    }
    New-Item -ItemType Junction -Path $resolvedSource -Target $resolvedTarget | Out-Null
}

Move-VerifiedCache $sourceRoot $cacheDestination
$otherCaches = @{
    '.cache/dictionaries'='dictionaries'
    'android/.gradle'='project-gradle'
    'android/.kotlin'='project-kotlin'
    'android/build'='gradle-build/root'
    'android/app/build'='gradle-build/app'
    'android/app/src/main/jniLibs'='packaging/jniLibs'
    'android/app/src/main/assets/generated'='packaging/assets'
    'android/app/src/androidTest/assets/generated'='packaging/test-assets'
}
foreach ($entry in $otherCaches.GetEnumerator()) {
    Move-VerifiedCache (Join-Path $workspaceRoot $entry.Key) (Join-Path $cacheDestination $entry.Value)
}
$record = @{ workspace=$workspaceRoot; path=$cacheDestination; reason='User-authorized Android cache migration; source code remains in Android worktree' } | ConvertTo-Json
Set-Content -LiteralPath (Join-Path $workspaceRoot '.cache/android-cache-location.json') -Value $record -Encoding utf8
Write-Output "Android caches now reside in $cacheDestination"
