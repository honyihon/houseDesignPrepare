param(
    [Parameter(Mandatory = $true)]
    [string]$Request,
    [ValidateSet("concept", "draft", "release", "ifc")]
    [string]$Mode = "draft",
    [ValidateSet("auto", "baseline", "best")]
    [string]$Selection = "auto",
    [ValidateSet("presentation", "technical", "debug")]
    [string]$DrawingStyle = "presentation",
    [ValidateSet("a3", "a4")]
    [string]$Paper = "a3",
    [string]$Buildings = "A,B,C",
    [string]$Output = "structured/candidates/print_bundle.pdf",
    [string]$Signoff = "structured/expert_review/signoff.yaml",
    [string]$PythonExe = "python"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot

if ($Mode -eq "release") {
    $Mode = "ifc"
}
elseif ($Mode -eq "ifc") {
    Write-Host "Mode 'ifc' is deprecated; use 'release'. IFC now names imported drawing files." -ForegroundColor Yellow
}

$resolvedRequest = Resolve-Path -LiteralPath $Request -ErrorAction Stop
$resolvedRequestPath = $resolvedRequest.Path
$normalizedBuildings = ($Buildings -split ",") | ForEach-Object { $_.Trim().ToUpper() } | Where-Object { $_ -ne "" }
$buildingsArg = ($normalizedBuildings -join ",")
if (-not $buildingsArg) {
    throw "Invalid -Buildings value. Use comma separated A,B,C."
}

if ($Selection -eq "auto") {
    $resolvedSelection = "baseline"
}
else {
    $resolvedSelection = $Selection
}

function Invoke-PythonStep {
    param(
        [string]$Name,
        [string[]]$Arguments,
        [int[]]$AllowedExitCodes = @(0)
    )

    Write-Host ("`n==> {0}" -f $Name) -ForegroundColor Cyan
    & $PythonExe @Arguments
    $code = $LASTEXITCODE
    if ($AllowedExitCodes -notcontains $code) {
        throw ("Step failed: {0} (exit code {1})" -f $Name, $code)
    }
    return $code
}

Write-Host ("Running expert workflow | mode={0} | selection={1} | buildings={2} | drawing style={3}" -f $Mode, $resolvedSelection, $buildingsArg, $DrawingStyle) -ForegroundColor DarkCyan
Write-Host ("Request file: {0}" -f $resolvedRequestPath) -ForegroundColor DarkCyan

Invoke-PythonStep -Name "Step 1/8 normalize requirement" -Arguments @(
    "scripts/evaluate_expert_gates.py",
    "--stage", "normalize",
    "--request", $resolvedRequestPath,
    "--buildings", $buildingsArg,
    "--mode", $Mode,
    "--selection", $resolvedSelection
)

$gateExit = Invoke-PythonStep -Name "Step 2/8 expert rules preflight gate" -Arguments @(
    "scripts/evaluate_expert_gates.py",
    "--stage", "gate",
    "--request", $resolvedRequestPath,
    "--buildings", $buildingsArg,
    "--mode", $Mode,
    "--selection", $resolvedSelection
) -AllowedExitCodes @(0, 10)

if ($gateExit -eq 10) {
    Write-Host "`nHard gate failed. Please resolve critical issues and rerun." -ForegroundColor Red
    exit 10
}

Invoke-PythonStep -Name "Step 3/8 HTML consistency check" -Arguments @(
    "scripts/check_html_consistency.py",
    "--buildings", $buildingsArg,
    "--mode", $Mode
)

Write-Host ("`n==> Step 4/8 run_full_pipeline ({0})" -f $Mode) -ForegroundColor Cyan
powershell -ExecutionPolicy Bypass -File "scripts/run_full_pipeline.ps1" `
    -Mode $Mode `
    -Paper $Paper `
    -Selection $resolvedSelection `
    -DrawingStyle $DrawingStyle `
    -ValidationOwner outer `
    -Output $Output `
    -PythonExe $PythonExe
if ($LASTEXITCODE -ne 0) {
    throw ("Step failed: run_full_pipeline (exit code {0})" -f $LASTEXITCODE)
}

$validationArgs = @("scripts/validate_layout_bundle.py")
if ($Mode -eq "ifc") {
    $validationArgs += "--strict"
}
Invoke-PythonStep -Name "Step 5/8 validate layout bundle" -Arguments $validationArgs

$reportArgs = @(
    "scripts/evaluate_expert_gates.py",
    "--stage", "report",
    "--request", $resolvedRequestPath,
    "--buildings", $buildingsArg,
    "--mode", $Mode,
    "--selection", $resolvedSelection,
    "--signoff", $Signoff
)
if ($Mode -eq "ifc") {
    $reportArgs += "--enforce-signoff-hash"
}

$reportExit = Invoke-PythonStep -Name "Step 6/8 summarize expert report" -Arguments $reportArgs -AllowedExitCodes @(0, 2, 10)

if ($reportExit -eq 10) {
    Write-Host "`nHard gate failed in final report. Check structured/expert_review/report.md." -ForegroundColor Red
    exit 10
}
if ($reportExit -eq 2) {
    Write-Host "`nIFC signoff is missing or stale. Check structured/expert_review/report.json and update related_report_hash in signoff.yaml." -ForegroundColor Red
    exit 2
}

Invoke-PythonStep -Name "Step 7/8 generate domain checklist" -Arguments @(
    "scripts/generate_domain_checklist.py"
)

Invoke-PythonStep -Name "Step 8/8 export final design HTML" -Arguments @(
    "scripts/export_final_design_html.py",
    "--mode", $Mode,
    "--selection", $resolvedSelection,
    "--buildings", $buildingsArg
)

Write-Host "`nExpert workflow completed successfully." -ForegroundColor Green
Write-Host ("Report: {0}" -f (Resolve-Path -LiteralPath "structured/expert_review/report.md").Path) -ForegroundColor Green
Write-Host ("Final HTML: {0}" -f (Resolve-Path -LiteralPath "structured/final_design_html/index.html").Path) -ForegroundColor Green
if ($Mode -ne "concept" -and (Test-Path -LiteralPath $Output)) {
    Write-Host ("Output: {0}" -f (Resolve-Path -LiteralPath $Output).Path) -ForegroundColor Green
}
