param(
    [Parameter(Mandatory = $true)]
    [string]$Request,
    [ValidateSet("concept", "draft", "ifc")]
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

$resolvedRequest = Resolve-Path -LiteralPath $Request -ErrorAction Stop
$resolvedRequestPath = $resolvedRequest.Path
$normalizedBuildings = ($Buildings -split ",") | ForEach-Object { $_.Trim().ToUpper() } | Where-Object { $_ -ne "" }
$buildingsArg = ($normalizedBuildings -join ",")
if (-not $buildingsArg) {
    throw "Invalid -Buildings value. Use comma separated A,B,C."
}

if ($Selection -eq "auto") {
    if ($Mode -eq "concept") {
        $resolvedSelection = "best"
    }
    else {
        $resolvedSelection = "baseline"
    }
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

function Assert-IfCSignoff {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "IFC mode requires signoff file: $Path"
    }
    $content = Get-Content -Raw -LiteralPath $Path
    if ($content -notmatch "(?im)^\s*decision\s*:\s*(approved|pass|approved_with_conditions)\s*$") {
        throw "IFC signoff missing valid decision (approved/pass/approved_with_conditions): $Path"
    }
}

Write-Host ("Running expert workflow | mode={0} | selection={1} | buildings={2} | drawing style={3}" -f $Mode, $resolvedSelection, $buildingsArg, $DrawingStyle) -ForegroundColor DarkCyan
Write-Host ("Request file: {0}" -f $resolvedRequestPath) -ForegroundColor DarkCyan

Invoke-PythonStep -Name "Step 1/7 normalize requirement" -Arguments @(
    "scripts/evaluate_expert_gates.py",
    "--stage", "normalize",
    "--request", $resolvedRequestPath,
    "--buildings", $buildingsArg,
    "--mode", $Mode,
    "--selection", $resolvedSelection
)

$gateExit = Invoke-PythonStep -Name "Step 2/7 expert rules preflight gate" -Arguments @(
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

Invoke-PythonStep -Name "Step 3/7 HTML consistency check" -Arguments @(
    "scripts/check_html_consistency.py",
    "--buildings", $buildingsArg
)

if ($Mode -eq "ifc") {
    Assert-IfCSignoff -Path $Signoff
}

Write-Host ("`n==> Step 4/7 run_full_pipeline ({0})" -f $Mode) -ForegroundColor Cyan
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

Invoke-PythonStep -Name "Step 5/7 validate layout bundle" -Arguments @(
    "scripts/validate_layout_bundle.py"
)

$reportExit = Invoke-PythonStep -Name "Step 6/7 summarize expert report" -Arguments @(
    "scripts/evaluate_expert_gates.py",
    "--stage", "report",
    "--request", $resolvedRequestPath,
    "--buildings", $buildingsArg,
    "--mode", $Mode,
    "--selection", $resolvedSelection,
    "--signoff", $Signoff
) -AllowedExitCodes @(0, 10)

if ($reportExit -eq 10) {
    Write-Host "`nHard gate failed in final report. Check structured/expert_review/report.md." -ForegroundColor Red
    exit 10
}

Invoke-PythonStep -Name "Step 7/7 export final design HTML" -Arguments @(
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
