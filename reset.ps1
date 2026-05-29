# reset_simple.ps1
Write-Host "Cleaning migrations..." -ForegroundColor Yellow

# Clean all custom app migrations
$apps = @("chatApp", "departmentApp", "mentoshipApp", "notificationApp", "onboarding", "userApp")
foreach ($app in $apps) {
    $migrationsPath = "D:\DJANGO\FINAL YEAR PROJECTS\Teta\backend\$app\migrations"
    if (Test-Path $migrationsPath) {
        Get-ChildItem -Path $migrationsPath -Filter "*.py" | Where-Object {$_.Name -ne "__init__.py"} | Remove-Item -Force
        Remove-Item -Path "$migrationsPath\__pycache__" -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "Cleaned migrations for $app"
    }
}

# Clean project pycache
Write-Host "Cleaning project cache..."
Remove-Item -Path "D:\DJANGO\FINAL YEAR PROJECTS\Teta\backend\__pycache__" -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "Done!"