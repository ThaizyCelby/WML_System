# Strip UTF-8 BOMs from all Python and HTML files in the project
Get-ChildItem -Path .\apps,.\core,.\config,.\templates -Recurse -Include *.py,*.html -File -ErrorAction SilentlyContinue |
    ForEach-Object {
        $path = $_.FullName
        try {
            $bytes = [System.IO.File]::ReadAllBytes($path)
            if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
                $newBytes = $bytes[3..($bytes.Length - 1)]
                [System.IO.File]::WriteAllBytes($path, $newBytes)
                Write-Host "BOM removed: $path"
            }
        } catch {
            Write-Host "Skipped: $path ($_)"
        }
    }
Write-Host "Done."