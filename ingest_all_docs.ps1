$docs = @(
    @{
        doc_id = "Project_Aurora-v6-20260528_082613"
        source = "C:\Users\DIH8HC\Downloads\Project_Aurora-v6-20260528_082613.pdf"
    },
    @{
        doc_id = "PMT_Architecture-v4-20260527_103159"
        source = "C:\Users\DIH8HC\Downloads\PMT_Architecture-v4-20260527_103159.pdf"
    },
    @{
        doc_id = "Cloudspace-v1-20260527_101338"
        source = "C:\Users\DIH8HC\Downloads\Cloudspace-v1-20260527_101338.pdf"
    }
)

$baseUrl = "http://localhost:8001"

foreach ($doc in $docs) {
    $payload = @{
        doc_id = $doc.doc_id
        source = $doc.source
        source_type = "pdf"
    } | ConvertTo-Json

    Write-Host "Ingesting: $($doc.doc_id)" -ForegroundColor Cyan
    try {
        $response = Invoke-WebRequest -Uri "$baseUrl/api/ingest" -Method POST -Body $payload -ContentType "application/json" -UseBasicParsing -TimeoutSec 60
        Write-Host "Status: $($response.StatusCode)" -ForegroundColor Green
    } catch {
        Write-Host "Error: $_" -ForegroundColor Red
    }
    Start-Sleep -Seconds 2
}

Write-Host "`nAll documents ingested!" -ForegroundColor Green
