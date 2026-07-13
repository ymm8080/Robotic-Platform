@echo off
echo Cleaning up temporary script files...
echo.

REM List of temporary script files to remove
set FILES_TO_REMOVE=^
_fix_ai_review.py ^
_fix_ai_review_simple.py ^
_apply_fixes.py ^
_apply_remaining.py ^
_fix_pr45.py ^
apply_all_fixes.py ^
apply_fixes.py ^
check_syntax.py ^
final_check.py ^
fix_bom.py

echo Removing temporary files:
for %%f in (%FILES_TO_REMOVE%) do (
    if exist "%%f" (
        echo   Deleting %%f
        del "%%f"
    ) else (
        echo   %%f not found
    )
)

echo.
echo Creating backup of current auto-fix script...
if exist "auto_fix_all.py" (
    copy "auto_fix_all.py" "auto_fix_all.py.backup"
    echo   Created backup: auto_fix_all.py.backup
)

echo.
echo Removing __pycache__ directories...
for /d /r . %%d in (__pycache__) do (
    if exist "%%d" (
        echo   Deleting %%d
        rmdir /s /q "%%d"
    )
)

echo.
echo Cleaning .pytest_cache...
if exist ".pytest_cache" (
    rmdir /s /q ".pytest_cache"
    echo   Deleted .pytest_cache
)

echo.
echo Checking for other temporary files...
REM Check for any other _*.py files
dir /b _*.py 2>nul
if not errorlevel 1 (
    echo.
    set /p deleteOther="Found other _*.py files. Delete them? (Y/N): "
    if /i "%deleteOther%"=="Y" (
        del _*.py
        echo   Deleted other _*.py files
    )
)

echo.
echo Cleanup complete!
echo.
echo Current directory listing:
dir /b *.py | findstr /v "monitor_catpaw auto_fix_all cleanup_temp_files setup_catpaw_monitor"

pause