# Layer 5 (OS/deployment) firewall provisioning — Windows.
# tasks/18-security-zero-egress.md §7 Requirement 5.
#
# Mechanism: Windows Defender Firewall with Advanced Security, scripted via
# New-NetFirewallRule — an outbound Block rule scoped to the backend's
# Python/executable path. Windows Firewall does not filter loopback traffic
# by default, so the backend's calls to Ollama on 127.0.0.1 continue to work
# without a separate explicit allow rule (docs/security.md layer 5).
#
# THIS IS A ONE-TIME PROVISIONING STEP. Run the configure mode (no flags)
# once, well before demo day, on the actual reference Windows machine in an
# elevated (Administrator) PowerShell session, then leave it alone. NEVER
# run configure mode live during a demo. -Verify is read-only and safe to
# re-run anytime, including on demo day.
#
# The exact New-NetFirewallRule parameters below are authored per Task 18's
# documented intent but, per the task file's own "Known Risks", are NOT
# guaranteed correct by this documentation set — hand-verify on the actual
# Windows reference machine before relying on it.
#
# Usage:
#   .\scripts\configure_firewall_windows.ps1              # one-time provisioning (Administrator PowerShell)
#   .\scripts\configure_firewall_windows.ps1 -Verify       # read-only check, safe anytime

param(
    [switch]$Verify
)

$ErrorActionPreference = "Stop"

$RuleName = "Bulwark-Backend-Outbound-Block"
$BackendProgram = Join-Path $PSScriptRoot "..\backend\.venv\Scripts\python.exe" | Resolve-Path -ErrorAction SilentlyContinue

if (-not $IsWindows -and $PSVersionTable.PSVersion.Major -ge 6) {
    Write-Error "error: this script is Windows-only. Use configure_firewall_macos.sh on macOS."
    exit 1
}

function Test-Verify {
    Write-Host "Verifying outbound-block-except-loopback..."

    # 1. Loopback must still work (Ollama on 11434) — Windows Firewall never
    #    filters loopback, so this should always succeed regardless of the rule.
    try {
        $null = Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 3 -UseBasicParsing
        Write-Host "  [ok] loopback (Ollama :11434) reachable"
    } catch {
        Write-Host "  [warn] loopback (Ollama :11434) not reachable — Ollama may not be running; this is not a firewall failure"
    }

    # 2. A real outbound attempt must fail once the rule is active.
    $blocked = $false
    try {
        $null = Invoke-WebRequest -Uri "https://1.1.1.1" -TimeoutSec 3 -UseBasicParsing
    } catch {
        $blocked = $true
    }

    if ($blocked) {
        Write-Host "  [ok] outbound to a public host failed as expected"
        Write-Host "verify: PASS"
    } else {
        Write-Host "  [FAIL] outbound to a public host succeeded — the firewall rule is not active or not effective"
        exit 1
    }
}

function Set-Configure {
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Error "error: configure mode requires an elevated (Administrator) PowerShell session."
        exit 1
    }

    if (-not $BackendProgram) {
        Write-Error "error: could not resolve backend/.venv/Scripts/python.exe — activate/create the venv first, or set the -Program path manually in this script."
        exit 1
    }

    # Idempotent: remove any existing rule of this name before recreating.
    Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue

    New-NetFirewallRule `
        -DisplayName $RuleName `
        -Direction Outbound `
        -Action Block `
        -Program $BackendProgram `
        -Profile Any `
        -Enabled True | Out-Null

    Write-Host "configured: outbound Block rule '$RuleName' created for $BackendProgram"
    Write-Host "Run '.\scripts\configure_firewall_windows.ps1 -Verify' to confirm the rule is effective."
}

if ($Verify) {
    Test-Verify
} else {
    Set-Configure
}
