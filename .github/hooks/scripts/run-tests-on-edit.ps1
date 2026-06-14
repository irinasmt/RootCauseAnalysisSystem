param()

# Read stdin (hook payload is JSON piped to stdin)
$rawInput = [Console]::In.ReadToEnd()

if (-not $rawInput.Trim()) {
    exit 0
}

try {
    $data = $rawInput | ConvertFrom-Json
} catch {
    exit 0
}

# Only fire on file-editing tools
$editTools = @('replace_string_in_file', 'create_file', 'multi_replace_string_in_file')
if ($data.toolName -notin $editTools) {
    exit 0
}

# Collect all file paths touched by this tool call
# toolArgs is a JSON string per the hooks payload spec
$filePaths = @()
try {
    $toolArgs = $data.toolArgs | ConvertFrom-Json
    if ($toolArgs.filePath) {
        $filePaths += $toolArgs.filePath
    }
    if ($toolArgs.replacements) {
        $filePaths += $toolArgs.replacements | ForEach-Object { $_.filePath }
    }
} catch {
    exit 0
}

# Skip if no Python file was edited
$hasPyFile = $filePaths | Where-Object { $_ -match '\.py$' }
if (-not $hasPyFile) {
    exit 0
}

# Resolve repo root from script location (scripts/ → hooks/ → .github/ → repo root)
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '../../..')

# Run the unit suite and capture output
$testOutput = & "$repoRoot\.venv\Scripts\pytest" "$repoRoot\tests\unit" -q 2>&1 | Out-String
$trimmed = $testOutput.Trim()

$response = [PSCustomObject]@{
    systemMessage = "Unit tests ran automatically after Python edit:`n$trimmed"
} | ConvertTo-Json -Compress

Write-Output $response
exit 0
