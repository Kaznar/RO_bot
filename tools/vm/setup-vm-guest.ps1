<#
Bootstrap script for the bot inside a Windows 11 VM.

Run from an ELEVATED PowerShell prompt INSIDE the VM:

    irm http://10.0.2.2:8080/tools/vm/setup-vm-guest.ps1 | iex

Prerequisite on the HOST machine (one-time, before running this):

    # In the project root:
    Compress-Archive `
        -Path src,tools,docs,pyproject.toml,uv.lock,config.json,README.md `
        -DestinationPath RO_bot.zip -Force
    python -m http.server 8080

Inside the VM, 10.0.2.2 is the host loopback (default VirtualBox NAT
gateway), so the VM can reach the HTTP server without any extra
networking config.

What this script does:
  1. Verify it is running as Administrator.
  2. Install Git and uv via winget (Win 11 has winget out of the box).
  3. Download RO_bot.zip from the host HTTP server.
  4. Extract it to C:\RO_bot.
  5. Run `uv sync` to install Python + bot dependencies.
  6. Print follow-up TODOs (USB filter, game client install).

We deliberately do NOT install VirtualBox Guest Additions: those drop
obvious fingerprints (drivers, services) that any modern anti-cheat
flags as "running in a VM".
#>

#requires -Version 5.1

$ErrorActionPreference = "Stop"
$ProgressPreference   = "SilentlyContinue"

$HostUrl    = "http://10.0.2.2:8080"
$ProjectDir = "C:\RO_bot"
$ZipPath    = "$env:TEMP\RO_bot.zip"

function Log-Step { param($Msg) Write-Host "==> $Msg" -ForegroundColor Cyan }
function Log-Ok   { param($Msg) Write-Host "    OK: $Msg"  -ForegroundColor Green }
function Log-Warn { param($Msg) Write-Host "    !!  $Msg"  -ForegroundColor Yellow }


function Assert-Admin {
    $isAdmin = ([Security.Principal.WindowsPrincipal] `
        [Security.Principal.WindowsIdentity]::GetCurrent() `
        ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) {
        throw "This script must be run from an elevated PowerShell."
    }
    Log-Ok "Running elevated."
}


function Test-WingetAvailable {
    return $null -ne (Get-Command winget -ErrorAction SilentlyContinue)
}


function Install-Tool {
    param([string]$WingetId, [string]$DisplayName, [string]$ExeName)
    if (Get-Command $ExeName -ErrorAction SilentlyContinue) {
        Log-Ok "$DisplayName already present."
        return
    }
    Log-Step "Installing $DisplayName via winget ($WingetId)..."
    winget install -e --id $WingetId `
        --accept-source-agreements --accept-package-agreements `
        --silent --disable-interactivity | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "winget install $WingetId failed (exit $LASTEXITCODE)."
    }
    # Refresh PATH so the just-installed exe is callable in this session.
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + `
                ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    Log-Ok "$DisplayName installed."
}


function Install-Uv {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        Log-Ok "uv already present ($(uv --version))."
        return
    }
    Log-Step "Installing uv (Astral Python toolchain)..."
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    $uvDir = "$env:USERPROFILE\.local\bin"
    if (Test-Path $uvDir) {
        $env:Path = "$uvDir;$env:Path"
    }
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw "uv install completed but `uv` is not on PATH."
    }
    Log-Ok "uv installed: $(uv --version)"
}


function Download-Project {
    Log-Step "Downloading RO_bot.zip from $HostUrl..."
    if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
    try {
        Invoke-WebRequest -Uri "$HostUrl/RO_bot.zip" -OutFile $ZipPath -UseBasicParsing
    } catch {
        throw "Could not download RO_bot.zip from $HostUrl. " +
              "Make sure `python -m http.server 8080` is running on the HOST " +
              "and RO_bot.zip exists in the project root. ($($_.Exception.Message))"
    }
    $size = (Get-Item $ZipPath).Length
    if ($size -lt 1000) {
        throw "Downloaded RO_bot.zip is only $size bytes - host is probably " +
              "serving a 404 page. Re-create the zip and retry."
    }
    Log-Ok "Downloaded $size bytes."
}


function Extract-Project {
    Log-Step "Extracting to $ProjectDir..."
    if (Test-Path $ProjectDir) {
        Log-Warn "$ProjectDir already exists - it will be overwritten."
        Remove-Item $ProjectDir -Recurse -Force
    }
    Expand-Archive -Path $ZipPath -DestinationPath $ProjectDir -Force
    Log-Ok "Extracted."
}


function Install-Deps {
    Log-Step "Running uv sync (installs Python + bot dependencies)..."
    Push-Location $ProjectDir
    try {
        uv sync
        if ($LASTEXITCODE -ne 0) {
            throw "uv sync failed (exit $LASTEXITCODE)."
        }
    } finally {
        Pop-Location
    }
    Log-Ok "Dependencies installed."
}


function Print-Followups {
    Write-Host ""
    Write-Host "================ NEXT STEPS (manual) ================" -ForegroundColor Magenta
    Write-Host @"
1. Plug Arduino into the HOST. In VirtualBox Manager (HOST), add a USB
   filter for the device:
     Settings -> USB -> Add filter from device list -> pick Arduino.
   Then unplug and re-plug it; VM should grab it. Verify in Device
   Manager (this VM) -> Ports (COM & LPT).

2. Install the NexusRO client inside this VM (run patcher, log in once
   with the throwaway character).

3. Edit $ProjectDir\config.json:
     - char_name -> your throwaway character
     - server.process_name / window_title -> match this client
     - allowed_maps / mobs -> as needed.

4. Start the bot from an ELEVATED PowerShell:
     cd $ProjectDir
     uv run ro-bot hunt
   First run will fire UAC (memory reads need admin).

5. Watch the first 30 minutes for any Gepard kicks / "abnormal client"
   popups. If Gepard kills the session, VirtualBox is being detected
   and you should fall back to Plan B (cooperative-cursor mode on the
   HOST instead of full VM).
"@ -ForegroundColor White
    Write-Host "=====================================================" -ForegroundColor Magenta
}


# ── Main ─────────────────────────────────────────────────────────────
try {
    Assert-Admin
    if (-not (Test-WingetAvailable)) {
        throw "winget not available. Install 'App Installer' from " +
              "Microsoft Store first."
    }
    Install-Tool -WingetId "Git.Git"     -DisplayName "Git"            -ExeName "git"
    Install-Uv
    Download-Project
    Extract-Project
    Install-Deps
    Print-Followups
    Write-Host ""
    Write-Host "Setup OK." -ForegroundColor Green
    exit 0
} catch {
    Write-Host ""
    Write-Host "SETUP FAILED: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
