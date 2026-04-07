param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$ErrorActionPreference = 'Stop'
$projectRoot = 'C:\Users\ace09\Projects\assistant-runtime'

Set-Location $projectRoot
python .\app\assistant_cli.py @Args
