param(
    [string]$AllowPort = "18080",
    [string]$BlockPort = "18114",
    [string]$AllowRemote = "LocalSubnet",
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Administrator 권한으로 실행해야 합니다. PowerShell을 '관리자 권한으로 실행' 후 다시 실행하세요."
    }
}

function Upsert-Rule {
    param(
        [Parameter(Mandatory = $true)][string]$DisplayName,
        [Parameter(Mandatory = $true)][ValidateSet("Allow", "Block")][string]$Action,
        [Parameter(Mandatory = $true)][string]$LocalPort,
        [Parameter(Mandatory = $true)][string]$RemoteAddress,
        [Parameter(Mandatory = $true)][string]$Description
    )

    Get-NetFirewallRule -DisplayName $DisplayName -ErrorAction SilentlyContinue | Remove-NetFirewallRule | Out-Null

    if ($DryRun) {
        Write-Host "[DRYRUN] $DisplayName ($Action TCP/$LocalPort Remote=$RemoteAddress)"
        return
    }

    New-NetFirewallRule `
        -DisplayName $DisplayName `
        -Direction Inbound `
        -Action $Action `
        -Enabled True `
        -Profile Any `
        -Protocol TCP `
        -LocalPort $LocalPort `
        -LocalAddress Any `
        -RemoteAddress $RemoteAddress `
        -EdgeTraversalPolicy Block `
        -Description $Description | Out-Null
}

Assert-Admin

$allowRule = "AIOps-Allow-$AllowPort-Trusted"
$blockRule = "AIOps-Block-$BlockPort-All"

Upsert-Rule `
    -DisplayName $allowRule `
    -Action Allow `
    -LocalPort $AllowPort `
    -RemoteAddress $AllowRemote `
    -Description "Allow AIOps API only from trusted remote addresses"

Upsert-Rule `
    -DisplayName $blockRule `
    -Action Block `
    -LocalPort $BlockPort `
    -RemoteAddress "Any" `
    -Description "Block direct inbound access to llama.cpp port"

Write-Host "Applied:"
Get-NetFirewallRule -DisplayName $allowRule, $blockRule |
    Format-Table DisplayName, Enabled, Direction, Action, Profile -AutoSize

Write-Host ""
Write-Host "Address filters:"
Get-NetFirewallRule -DisplayName $allowRule, $blockRule |
    Get-NetFirewallAddressFilter |
    Format-Table LocalAddress, RemoteAddress -AutoSize

