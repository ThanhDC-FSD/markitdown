param()

Write-Host "`n=========================================="  -ForegroundColor Green
Write-Host "API Endpoint Tests" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green

Write-Host "`nTest 1: GET / - Root endpoint" -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "http://localhost:8001/" -Method Get
    Write-Host "PASS - API is responding" -ForegroundColor Green
    Write-Host "Version: $($response.version), Status: $($response.status)" -ForegroundColor Gray
} catch {
    Write-Host "FAIL - $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`nTest 2: GET /api/status - Check KB" -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "http://localhost:8001/api/status" -Method Get
    Write-Host "PASS - KB status retrieved" -ForegroundColor Green
    Write-Host "Documents: $($response.documents_in_kb), Chunks: $($response.total_chunks)" -ForegroundColor Gray
} catch {
    Write-Host "FAIL - $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`nTest 3: POST /api/ingest - Add document" -ForegroundColor Yellow
try {
    $headers = @{"Content-Type" = "application/json"}
    $body = @{
        "source_type" = "file"
        "source" = "./sample_docs/machine_learning_basics.md"
        "metadata" = @{"topic" = "ML"}
    } | ConvertTo-Json
    
    $response = Invoke-RestMethod -Uri "http://localhost:8001/api/ingest" -Method Post -Headers $headers -Body $body
    Write-Host "PASS - Document ingested" -ForegroundColor Green
    Write-Host "Processed: $($response.documents_processed), Success: $($response.success)" -ForegroundColor Gray
} catch {
    Write-Host "FAIL - $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`nTest 4: GET /api/status - After ingestion" -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "http://localhost:8001/api/status" -Method Get
    Write-Host "PASS - KB status after ingestion" -ForegroundColor Green
    Write-Host "Documents: $($response.documents_in_kb), Chunks: $($response.total_chunks)" -ForegroundColor Gray
} catch {
    Write-Host "FAIL - $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`nTest 5: POST /api/query - Query KB" -ForegroundColor Yellow
try {
    $headers = @{"Content-Type" = "application/json"}
    $body = @{
        "query" = "What is machine learning?"
        "top_k" = 5
        "rerank_top_k" = 3
    } | ConvertTo-Json
    
    $response = Invoke-RestMethod -Uri "http://localhost:8001/api/query" -Method Post -Headers $headers -Body $body
    Write-Host "PASS - Query executed" -ForegroundColor Green
    Write-Host "Answer length: $($response.answer.Length) chars, Success: $($response.success)" -ForegroundColor Gray
    if ($response.context_chunks -and $response.context_chunks.Count -gt 0) {
        Write-Host "Retrieved $($response.context_chunks.Count) context chunks" -ForegroundColor Gray
    }
} catch {
    Write-Host "FAIL - $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`n=========================================="  -ForegroundColor Green
Write-Host "All tests completed" -ForegroundColor Green
