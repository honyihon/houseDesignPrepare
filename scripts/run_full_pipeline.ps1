param(
    [ValidateSet("concept", "draft", "ifc")]
    [string]$Mode = "draft",
    [ValidateSet("a3", "a4")]
    [string]$Paper = "a3",
    [ValidateSet("auto", "baseline", "best")]
    [string]$Selection = "auto",
    [ValidateSet("presentation", "technical", "debug")]
    [string]$DrawingStyle = "presentation",
    [ValidateSet("inner", "outer", "none")]
    [string]$ValidationOwner = "inner",
    [string]$Output = "structured/candidates/print_bundle.pdf",
    [string]$PythonExe = "python"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot

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

function Invoke-Step {
    param(
        [string]$Name,
        [string[]]$Arguments
    )

    Write-Host ("`n==> {0}" -f $Name) -ForegroundColor Cyan
    & $PythonExe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw ("Step failed: {0} (exit code {1})" -f $Name, $LASTEXITCODE)
    }
}

Write-Host ("Running mode: {0} | selection: {1} | drawing style: {2} | validation owner: {3}" -f $Mode, $resolvedSelection, $DrawingStyle, $ValidationOwner) -ForegroundColor DarkCyan

Invoke-Step -Name "Step 1/7 extract_layout_data" -Arguments @("scripts/extract_layout_data.py")
Invoke-Step -Name "Step 2/7 build_room_program" -Arguments @("scripts/build_room_program.py")
Invoke-Step -Name "Step 3/7 evaluate_architect_metrics" -Arguments @("scripts/evaluate_architect_metrics.py")
Invoke-Step -Name "Step 4/7 generate_layout_candidates" -Arguments @("scripts/generate_layout_candidates.py")
Invoke-Step -Name "Step 5/7 render_candidate_viewer" -Arguments @("scripts/render_candidate_viewer.py")
Invoke-Step -Name "Step 6/7 export_top1_svgs" -Arguments @(
    "scripts/export_top1_svgs.py",
    "--selection",
    $resolvedSelection,
    "--style",
    $DrawingStyle
)

if ($Mode -ne "concept") {
    Invoke-Step -Name "Step 7/7 export_print_bundle_pdf" -Arguments @(
        "scripts/export_print_bundle_pdf.py",
        "--paper",
        $Paper,
        "--output",
        $Output
    )

    if (-not (Test-Path -LiteralPath $Output)) {
        throw ("PDF not found after pipeline run: {0}" -f $Output)
    }
}
else {
    Write-Host "`nMode concept: skip PDF export for faster iteration." -ForegroundColor Yellow
}

if ($Mode -eq "ifc" -and $ValidationOwner -eq "inner") {
    Invoke-Step -Name "Step IFC gate validate_layout_bundle" -Arguments @("scripts/validate_layout_bundle.py")
}
elseif ($Mode -eq "ifc" -and $ValidationOwner -eq "outer") {
    Write-Host "`nMode ifc: validation owned by outer workflow." -ForegroundColor Yellow
}
elseif ($Mode -eq "ifc" -and $ValidationOwner -eq "none") {
    Write-Host "`nMode ifc: validation skipped by explicit request." -ForegroundColor Yellow
}

if ($Mode -eq "concept") {
    $manifestPath = (Resolve-Path -LiteralPath "structured/candidates/svg/manifest.json").Path
    Write-Host ("`nPipeline completed (concept). Manifest: {0}" -f $manifestPath) -ForegroundColor Green
}
else {
    $pdfPath = (Resolve-Path -LiteralPath $Output).Path
    Write-Host ("`nPipeline completed ({0}). PDF: {1}" -f $Mode, $pdfPath) -ForegroundColor Green
}
