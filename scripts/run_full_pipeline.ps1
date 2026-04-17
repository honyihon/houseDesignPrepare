param(
    [ValidateSet("concept", "draft", "ifc")]
    [string]$Mode = "draft",
    [ValidateSet("a3", "a4")]
    [string]$Paper = "a3",
    [ValidateSet("auto", "baseline", "best")]
    [string]$Selection = "auto",
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

Write-Host ("Running mode: {0} | selection: {1}" -f $Mode, $resolvedSelection) -ForegroundColor DarkCyan

Invoke-Step -Name "Step 1/6 extract_layout_data" -Arguments @("scripts/extract_layout_data.py")
Invoke-Step -Name "Step 2/6 build_room_program" -Arguments @("scripts/build_room_program.py")
Invoke-Step -Name "Step 3/6 generate_layout_candidates" -Arguments @("scripts/generate_layout_candidates.py")
Invoke-Step -Name "Step 4/6 render_candidate_viewer" -Arguments @("scripts/render_candidate_viewer.py")
Invoke-Step -Name "Step 5/6 export_top1_svgs" -Arguments @("scripts/export_top1_svgs.py", "--selection", $resolvedSelection)

if ($Mode -ne "concept") {
    Invoke-Step -Name "Step 6/6 export_print_bundle_pdf" -Arguments @(
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

if ($Mode -eq "ifc") {
    Invoke-Step -Name "Step IFC gate validate_layout_bundle" -Arguments @("scripts/validate_layout_bundle.py")
}

if ($Mode -eq "concept") {
    $manifestPath = (Resolve-Path -LiteralPath "structured/candidates/svg/manifest.json").Path
    Write-Host ("`nPipeline completed (concept). Manifest: {0}" -f $manifestPath) -ForegroundColor Green
}
else {
    $pdfPath = (Resolve-Path -LiteralPath $Output).Path
    Write-Host ("`nPipeline completed ({0}). PDF: {1}" -f $Mode, $pdfPath) -ForegroundColor Green
}
