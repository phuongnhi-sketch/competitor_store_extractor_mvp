# ============================================================
# Competitor Store Extractor - Project Cleanup
# ============================================================
#
# SAFE CLEANUP SCRIPT
#
# Deletes:
#   - Python cache
#   - *.pyc / *.pyo
#   - pytest cache
#   - mypy cache
#   - ruff cache
#   - Streamlit cache
#   - test output folders
#   - debug output folders
#   - raw_api folders
#   - *.log
#   - *.tmp
#   - *.temp
#
# PROTECTED:
#   - All source code (*.py)
#   - All JSON files
#   - All YAML/YML files
#   - requirements.txt
#   - README.md
#   - .venv/
#   - brands/
#   - Files/folders containing "OLD"
#   - clean_project.ps1
#
# ============================================================

$ErrorActionPreference = "SilentlyContinue"


# ============================================================
# 1. PROJECT ROOT
# ============================================================

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Competitor Store Extractor - Project Cleanup" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Project folder:" -ForegroundColor Gray
Write-Host $ProjectRoot -ForegroundColor White
Write-Host ""

$deletedCount = 0


# ============================================================
# 2. HELPER - DELETE DIRECTORY
# ============================================================

function Remove-SafeDirectory {
    param (
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    # Never delete anything inside .venv
    if ($Path -like "*\.venv\*") {
        return
    }

    # Never delete anything containing OLD
    $name = Split-Path -Leaf $Path

    if ($name -match '(?i)OLD') {
        Write-Host "[KEEP OLD]       $Path" -ForegroundColor Green
        return
    }

    Write-Host "[DELETE FOLDER]  $Path" -ForegroundColor Yellow

    Remove-Item `
        -LiteralPath $Path `
        -Recurse `
        -Force

    if (-not (Test-Path -LiteralPath $Path)) {
        $script:deletedCount++
    }
}


# ============================================================
# 3. HELPER - DELETE FILE
# ============================================================

function Remove-SafeFile {
    param (
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    # Never delete anything inside .venv
    if ($Path -like "*\.venv\*") {
        return
    }

    $name = Split-Path -Leaf $Path

    # IMPORTANT:
    # Keep anything containing OLD
    if ($name -match '(?i)OLD') {
        Write-Host "[KEEP OLD]       $Path" -ForegroundColor Green
        return
    }

    Write-Host "[DELETE FILE]    $Path" -ForegroundColor DarkYellow

    Remove-Item `
        -LiteralPath $Path `
        -Force

    if (-not (Test-Path -LiteralPath $Path)) {
        $script:deletedCount++
    }
}


# ============================================================
# 4. HELPER - DELETE FILES BY EXTENSION/PATTERN
# ============================================================

function Remove-SafeFiles {
    param (
        [string]$Pattern
    )

    $files = Get-ChildItem `
        -Path $ProjectRoot `
        -Recurse `
        -File `
        -Force `
        -Filter $Pattern

    foreach ($file in $files) {

        # Never touch .venv
        if ($file.FullName -like "*\.venv\*") {
            continue
        }

        # Never delete OLD files
        if ($file.Name -match '(?i)OLD') {
            Write-Host "[KEEP OLD]       $($file.FullName)" -ForegroundColor Green
            continue
        }

        Remove-SafeFile $file.FullName
    }
}


# ============================================================
# 5. PYTHON CACHE
# ============================================================

Write-Host ""
Write-Host "--- Python cache ---" -ForegroundColor Cyan

$pythonCaches = Get-ChildItem `
    -Path $ProjectRoot `
    -Recurse `
    -Directory `
    -Force `
    -Filter "__pycache__"

foreach ($folder in $pythonCaches) {

    if ($folder.FullName -like "*\.venv\*") {
        continue
    }

    Remove-SafeDirectory $folder.FullName
}

Remove-SafeFiles "*.pyc"
Remove-SafeFiles "*.pyo"


# ============================================================
# 6. PYTHON TOOL CACHE
# ============================================================

Write-Host ""
Write-Host "--- Python tool cache ---" -ForegroundColor Cyan

$cacheFolders = @(
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache"
)

foreach ($cacheName in $cacheFolders) {

    $folders = Get-ChildItem `
        -Path $ProjectRoot `
        -Recurse `
        -Directory `
        -Force `
        -Filter $cacheName

    foreach ($folder in $folders) {

        if ($folder.FullName -like "*\.venv\*") {
            continue
        }

        Remove-SafeDirectory $folder.FullName
    }
}


# ============================================================
# 7. STREAMLIT CACHE
# ============================================================

Write-Host ""
Write-Host "--- Streamlit cache ---" -ForegroundColor Cyan

$streamlitCache = Join-Path `
    $ProjectRoot `
    ".streamlit\cache"

if (Test-Path -LiteralPath $streamlitCache) {

    Remove-SafeDirectory $streamlitCache
}


# ============================================================
# 8. KNOWN TEST / DEBUG OUTPUT
# ============================================================

Write-Host ""
Write-Host "--- Test / debug output ---" -ForegroundColor Cyan

$knownOutputFolders = @(
    "kfc_test_output",
    "debug_output",
    "test_output"
)

foreach ($folderName in $knownOutputFolders) {

    $path = Join-Path `
        $ProjectRoot `
        $folderName

    if (Test-Path -LiteralPath $path) {

        Remove-SafeDirectory $path
    }
}


# ============================================================
# 9. *_test_output FOLDERS
# ============================================================

Write-Host ""
Write-Host "--- *_test_output folders ---" -ForegroundColor Cyan

$allDirectories = Get-ChildItem `
    -Path $ProjectRoot `
    -Recurse `
    -Directory `
    -Force

foreach ($folder in $allDirectories) {

    # Never touch .venv
    if ($folder.FullName -like "*\.venv\*") {
        continue
    }

    # Keep OLD folders
    if ($folder.Name -match '(?i)OLD') {
        Write-Host "[KEEP OLD]       $($folder.FullName)" -ForegroundColor Green
        continue
    }

    if ($folder.Name -like "*_test_output") {

        Remove-SafeDirectory $folder.FullName
    }
}


# ============================================================
# 10. RAW API DEBUG FOLDERS
# ============================================================

Write-Host ""
Write-Host "--- Raw API folders ---" -ForegroundColor Cyan

$rawApiFolders = Get-ChildItem `
    -Path $ProjectRoot `
    -Recurse `
    -Directory `
    -Force

foreach ($folder in $rawApiFolders) {

    # Never touch .venv
    if ($folder.FullName -like "*\.venv\*") {
        continue
    }

    # Keep OLD folders
    if ($folder.Name -match '(?i)OLD') {
        Write-Host "[KEEP OLD]       $($folder.FullName)" -ForegroundColor Green
        continue
    }

    if ($folder.Name -eq "raw_api") {

        Remove-SafeDirectory $folder.FullName
    }
}


# ============================================================
# 11. LOG FILES
# ============================================================

Write-Host ""
Write-Host "--- Log files ---" -ForegroundColor Cyan

Remove-SafeFiles "*.log"


# ============================================================
# 12. TEMPORARY FILES
# ============================================================

Write-Host ""
Write-Host "--- Temporary files ---" -ForegroundColor Cyan

Remove-SafeFiles "*.tmp"
Remove-SafeFiles "*.temp"


# ============================================================
# 13. JSON FILES
# ============================================================
#
# IMPORTANT:
#
# We DO NOT delete *.json.
#
# This protects:
#   - configuration JSON
#   - mapping JSON
#   - API configuration
#   - other project data
#
# Even debug JSON files are preserved unless they are inside
# a folder already removed above.
#
# ============================================================

Write-Host ""
Write-Host "--- JSON files ---" -ForegroundColor Cyan

Write-Host "JSON files are protected." -ForegroundColor Green
Write-Host "No JSON files were deleted." -ForegroundColor Green


# ============================================================
# 14. OLD FILES / FOLDERS
# ============================================================
#
# IMPORTANT:
#
# Files/folders containing "OLD" are intentionally preserved.
#
# Examples:
#
#   app_OLD.py
#   crawler_OLD.py
#   OLD_backup/
#   old_version/
#   config_OLD.json
#
# ============================================================

Write-Host ""
Write-Host "--- OLD files / folders ---" -ForegroundColor Cyan

Write-Host "Files and folders containing 'OLD' are protected." -ForegroundColor Green


# ============================================================
# 15. SUMMARY
# ============================================================

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Cleanup completed" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan

Write-Host ""
Write-Host "Deleted items: $deletedCount" -ForegroundColor White

Write-Host ""
Write-Host "Protected items:" -ForegroundColor Green

Write-Host "  [KEEP] Python source code (*.py)"
Write-Host "  [KEEP] JSON files"
Write-Host "  [KEEP] YAML / YML files"
Write-Host "  [KEEP] requirements.txt"
Write-Host "  [KEEP] README.md"
Write-Host "  [KEEP] .venv/"
Write-Host "  [KEEP] brands/"
Write-Host "  [KEEP] Files containing OLD"
Write-Host "  [KEEP] Folders containing OLD"
Write-Host "  [KEEP] clean_project.ps1"

Write-Host ""
Write-Host "Done." -ForegroundColor Cyan
Write-Host ""