<#
.SYNOPSIS
    Recursively finds and renames Python test files to the standard unittest format.

.DESCRIPTION
    This script searches the 'test' directory and its subdirectories for any
    files ending in '.test.py' and renames them to the 'test_*.py' convention.
    For example, 'admin_ui.test.py' becomes 'test_admin_ui.py'.

    This is necessary for Python's built-in unittest discovery to find and run the tests.

.EXAMPLE
    .\rename_tests.ps1
#>
$adminCheck = [Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $adminCheck.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Warning "It's recommended to run this script from an elevated PowerShell session."
}

# Get the path to the 'test' directory relative to the repository root
$RootDir = Split-Path -Parent $PSScriptRoot
$testDirectory = Join-Path -Path $RootDir -ChildPath "test"

Write-Host "Searching for test files to rename in: $testDirectory" -ForegroundColor Yellow

# Find all files recursively in the 'test' directory that match the old naming pattern
Get-ChildItem -Path $testDirectory -Recurse -Filter "*.test.py" | ForEach-Object {
    # For each file found...
    $oldFile = $_
    $directory = $oldFile.DirectoryName

    # Get the base name (filename without the final .py extension)
    # e.g., "admin_ui.test"
    $baseName = $oldFile.BaseName

    # Remove the '.test' suffix to get the core module name
    # e.g., "admin_ui"
    $moduleName = $baseName.Replace(".test", "")

    # Construct the new, correct filename
    # e.g., "test_admin_ui.py"
    $newFileName = "test_$($moduleName).py"

    try {
        # Rename the file using its full path and the new file name
        Rename-Item -Path $oldFile.FullName -NewName $newFileName -ErrorAction Stop

        # Print a success message
        Write-Host "Renamed: $($oldFile.Name) -> $($newFileName)" -ForegroundColor Green
    }
    catch {
        Write-Host "Error renaming $($oldFile.FullName): $_" -ForegroundColor Red
    }
}

Write-Host "`nFile renaming process complete." -ForegroundColor Cyan
