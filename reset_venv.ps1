<#
.SYNOPSIS
    Securely and completely resets the Python virtual environment.
.DESCRIPTION
    This script automates the process of deleting the old .venv folder,
    creating a new one, upgrading core packaging tools, and installing
    all dependencies from requirements.txt.

    It will automatically request Administrator privileges and will pause
    the new window for review before closing.
.EXAMPLE
    .\reset_venv.ps1
#>
$adminCheck = [Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $adminCheck.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Warning "It's recommended to run this script from an elevated PowerShell session."
}

# --- Self-Elevation Logic ---
# This block ensures the script runs with Administrator privileges.
if (-Not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]'Administrator')) {
    # Construct the command to re-launch this script in a new, elevated PowerShell window.
    $arguments = "-NoProfile -ExecutionPolicy Bypass -Command `"& '$($MyInvocation.MyCommand.Path)'`""
    Start-Process powershell.exe -Verb RunAs -ArgumentList $arguments
    # Exit the original, non-elevated script.
    exit
}

# --- Main Script Logic ---
# All commands are wrapped in a try/catch/finally block for robust execution.

try {
    # Set the working directory to the script's own location. This is crucial for making sure
    # relative paths like '.\.venv' and 'requirements.txt' are found correctly.
    Set-Location -Path $PSScriptRoot

    # Set the name of the virtual environment folder
    $venvPath = ".venv"

    # Use -ErrorAction Stop on native PowerShell cmdlets to make them halt on error.
    Write-Host "--- Step 1: Removing old virtual environment ---" -ForegroundColor Yellow
    Write-Host "(If this step fails with a 'permission denied' error, please close VS Code and any open terminals, then run the script again.)" -ForegroundColor Cyan
    if (Test-Path $venvPath) {
        Remove-Item -Path $venvPath -Recurse -Force -ErrorAction Stop
        Write-Host "Old .venv folder removed successfully." -ForegroundColor Green
    } else {
        Write-Host "No old .venv folder found. Skipping."
    }

    Write-Host "`n--- Step 2: Creating new virtual environment ---" -ForegroundColor Yellow
    # For external commands like python.exe, we can't use -ErrorAction.
    # We must check the exit code manually afterwards.
    python -m venv $venvPath
    if (-not $?) { throw "Failed to create virtual environment. Last exit code: $LASTEXITCODE" }
    Write-Host "New .venv created successfully." -ForegroundColor Green

    # Define the absolute path to the Python executable inside the new venv
    $pythonExecutable = Join-Path -Path $PSScriptRoot -ChildPath "$venvPath\Scripts\python.exe"

    Write-Host "`n--- Step 3: Upgrading core packaging tools ---" -ForegroundColor Yellow
    # Use the call operator '&' with the full path to the venv's python.exe
    & $pythonExecutable -m pip install --upgrade pip setuptools wheel
    if (-not $?) { throw "Failed to upgrade pip. Last exit code: $LASTEXITCODE" }
    Write-Host "Pip, setuptools, and wheel upgraded successfully." -ForegroundColor Green

    Write-Host "`n--- Step 4: Installing project dependencies ---" -ForegroundColor Yellow
    & $pythonExecutable -m pip install -r requirements.txt
    if (-not $?) { throw "Failed to install requirements. Last exit code: $LASTEXITCODE" }
    Write-Host "Dependencies from requirements.txt installed successfully." -ForegroundColor Green

    Write-Host "`n----------------------------------------"
    Write-Host "Virtual environment reset successfully!" -ForegroundColor Cyan

}
catch {
    # If any command with -ErrorAction Stop fails, or if we 'throw' an error, the script jumps here.
    Write-Host "`n----------------------------------------"
    Write-Host "AN ERROR OCCURRED:" -ForegroundColor Red
    # $_ is the error record. For thrown exceptions, $_.Exception.Message is null.
    # The default string representation of $_ is more reliable here.
    Write-Host $_ -ForegroundColor Red
    Write-Host "----------------------------------------"
}
finally {
    # This block always runs, whether the script succeeded or failed.
    # It prompts the user to press a key before the script ends and the window closes.
    Write-Host "Script finished. Press any key to exit..."
    $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown") | Out-Null
}
