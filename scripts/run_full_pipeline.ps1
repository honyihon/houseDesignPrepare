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
    $resolvedSelection = "baseline"
}
else {
    $resolvedSelection = $Selection
}

# Ten steps always run; the PDF export and the IFC gate are conditional, so the
# total is computed rather than hardcoded or the "Step n/N" counter overshoots.
$totalSteps = 10
if ($Mode -ne "concept") { $totalSteps++ }
if ($Mode -eq "ifc" -and $ValidationOwner -eq "inner") { $totalSteps++ }
$script:stepIndex = 0

function Invoke-Step {
    param(
        [string]$Name,
        [string[]]$Arguments,
        # Steps that report problems rather than produce artifacts: a non-zero
        # exit is a finding to surface, not a reason to abandon the run.
        [switch]$WarnOnFailure
    )

    $script:stepIndex++
    Write-Host ("`n==> Step {0}/{1} {2}" -f $script:stepIndex, $totalSteps, $Name) -ForegroundColor Cyan
    & $PythonExe @Arguments
    if ($LASTEXITCODE -ne 0) {
        if ($WarnOnFailure) {
            Write-Host ("    {0} reported problems (exit code {1}); continuing." -f $Name, $LASTEXITCODE) -ForegroundColor Yellow
            return
        }
        throw ("Step failed: {0} (exit code {1})" -f $Name, $LASTEXITCODE)
    }
}

Write-Host ("Running mode: {0} | selection: {1} | drawing style: {2} | validation owner: {3}" -f $Mode, $resolvedSelection, $DrawingStyle, $ValidationOwner) -ForegroundColor DarkCyan

# HTML consistency runs first, against the source the whole pipeline reads.
# In ifc a critical finding stops the release; in concept/draft it is reported
# and the run continues so iteration is not blocked.
$consistencyArgs = @("scripts/check_html_consistency.py", "--mode", $Mode)
if ($Mode -eq "ifc") {
    Invoke-Step -Name "check_html_consistency" -Arguments $consistencyArgs
}
else {
    Invoke-Step -Name "check_html_consistency" -Arguments $consistencyArgs -WarnOnFailure
}

Invoke-Step -Name "extract_layout_data" -Arguments @("scripts/extract_layout_data.py")
Invoke-Step -Name "build_room_program" -Arguments @("scripts/build_room_program.py")
Invoke-Step -Name "evaluate_architect_metrics" -Arguments @("scripts/evaluate_architect_metrics.py")
Invoke-Step -Name "generate_layout_candidates" -Arguments @("scripts/generate_layout_candidates.py")
Invoke-Step -Name "render_candidate_viewer" -Arguments @("scripts/render_candidate_viewer.py")
# Runs in every mode, concept included: the 3D massing viewer is the fastest way
# to get a spatial read on a change, which is exactly what concept mode is for.
Invoke-Step -Name "export_model_3d" -Arguments @("scripts/export_model_3d.py")
# The parametric branch answers a different question from everything else here:
# not "what does the drawn plan measure" but "what fits in 32 ping at all". It
# reads inputs/brief instead of the HTML, so it runs in every mode.
Invoke-Step -Name "generate_parametric_plan" -Arguments @("scripts/generate_parametric_plan.py")
Invoke-Step -Name "export_walkthrough_3d" -Arguments @("scripts/export_walkthrough_3d.py")
Invoke-Step -Name "export_top1_svgs" -Arguments @(
    "scripts/export_top1_svgs.py",
    "--selection",
    $resolvedSelection,
    "--style",
    $DrawingStyle
)

if ($Mode -ne "concept") {
    Invoke-Step -Name "export_print_bundle_pdf" -Arguments @(
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
    Invoke-Step -Name "IFC gate validate_layout_bundle" -Arguments @("scripts/validate_layout_bundle.py", "--strict")
}
elseif ($Mode -eq "ifc" -and $ValidationOwner -eq "outer") {
    Write-Host "`nMode ifc: validation owned by outer workflow." -ForegroundColor Yellow
}
elseif ($Mode -eq "ifc" -and $ValidationOwner -eq "none") {
    Write-Host "`nMode ifc: validation skipped by explicit request." -ForegroundColor Yellow
}

$model3dPath = (Resolve-Path -LiteralPath "structured/candidates/model3d.html").Path
if ($Mode -eq "concept") {
    $manifestPath = (Resolve-Path -LiteralPath "structured/candidates/svg/manifest.json").Path
    Write-Host ("`nPipeline completed (concept). Manifest: {0}" -f $manifestPath) -ForegroundColor Green
}
else {
    $pdfPath = (Resolve-Path -LiteralPath $Output).Path
    Write-Host ("`nPipeline completed ({0}). PDF: {1}" -f $Mode, $pdfPath) -ForegroundColor Green
}
Write-Host ("3D massing viewer: {0}" -f $model3dPath) -ForegroundColor Green
$walkPath = (Resolve-Path -LiteralPath "structured/parametric/walkthrough.html").Path
Write-Host ("Walk-in 3D (parametric): {0}" -f $walkPath) -ForegroundColor Green
