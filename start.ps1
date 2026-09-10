$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$localPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$workspacePython = Join-Path $PSScriptRoot '..\..\work\.venv\Scripts\python.exe'
if (Test-Path $localPython) { & $localPython -m streamlit run app.py }
elseif (Test-Path $workspacePython) { & $workspacePython -m streamlit run app.py }
else { Write-Error '请先按照 README 安装 Python 依赖。' }
