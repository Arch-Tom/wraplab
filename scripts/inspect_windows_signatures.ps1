# External read-only build evidence; never launched by WrapLab.
param([Parameter(Mandatory=$true)][string]$Bundle, [Parameter(Mandatory=$true)][string]$Output)
$ErrorActionPreference = 'Stop'
$rows = @(Get-ChildItem -LiteralPath $Bundle -Recurse -File | Where-Object { $_.Extension -in '.exe', '.dll', '.pyd' } | ForEach-Object {
    $signature = Get-AuthenticodeSignature -LiteralPath $_.FullName
    [PSCustomObject]@{
        Path = [IO.Path]::GetRelativePath((Resolve-Path -LiteralPath $Bundle).Path, $_.FullName)
        SHA256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        Status = [string]$signature.Status
        StatusMessage = $signature.StatusMessage
        SignerSubject = if ($signature.SignerCertificate) { $signature.SignerCertificate.Subject } else { $null }
        FileVersion = $_.VersionInfo.FileVersion
        ProductName = $_.VersionInfo.ProductName
        CompanyName = $_.VersionInfo.CompanyName
    }
})
$rows | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $Output -Encoding utf8
