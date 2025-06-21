<#
.SYNOPSIS
    Recursively creates an empty __init__.py file in directories that contain Python scripts.

.DESCRIPTION
    This script ensures Python's test discovery and module importing work reliably
    by turning directories with Python code into packages. It will only add an
    __init__.py file to a directory if it finds at least one '.py' file within
    that directory or any of its subdirectories.

    It intelligently ignores common directories like .venv, .git, and __pycache__.

.EXAMPLE
    .\create_inits.ps1
#>

# Get the current location (your project's root directory)
$rootPath = (Get-Location).Path

# Define directories to exclude from the search
$excludedDirs = @(".venv", ".git", "__pycache__", ".vscode", "node_modules")

# Create a hashtable to store unique directories that need an __init__.py
$dirsToInit = @{}

# Find all directories that are NOT in the exclusion list
Get-ChildItem -Path $rootPath -Recurse -Directory | ForEach-Object {
    $isExcluded = $false
    foreach ($exclude in $excludedDirs) {
        if ($_.FullName.StartsWith( (Join-Path -Path $rootPath -ChildPath $exclude)) ) {
            $isExcluded = $true
            break
        }
    }

    if (-not $isExcluded) {
        # Check if this specific directory contains any .py files (not recursive)
        if (Get-ChildItem -Path $_.FullName -Filter *.py -File | Select-Object -First 1) {
            # If it has python files, walk up the parent directories and add them to our list
            $currentDir = $_
            while ($currentDir -and $currentDir.FullName.StartsWith($rootPath)) {
                if (-not $dirsToInit.ContainsKey($currentDir.FullName)) {
                    $dirsToInit[$currentDir.FullName] = $true
                }
                $currentDir = $currentDir.Parent
            }
        }
    }
}

# Now, iterate through the unique directories and add __init__.py if needed
foreach ($dirPath in $dirsToInit.Keys) {
    $initPath = Join-Path -Path $dirPath -ChildPath "__init__.py"
    if (-not (Test-Path $initPath)) {
        New-Item -Path $initPath -ItemType File | Out-Null
        Write-Host "Created: $initPath"
    }
}

Write-Host "Python __init__.py check complete."
