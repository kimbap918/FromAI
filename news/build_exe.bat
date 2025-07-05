@echo off
echo ========================================
echo Unified News Tool EXE Build Start
echo ========================================

REM 기존 빌드 폴더 정리
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "*.spec" del "*.spec"

echo.
echo 1. Building EXE file with PyInstaller...
pyinstaller --onefile ^
           --windowed ^
           --name "UnifiedNewsTool" ^
           --add-data "requirements.txt;." ^
           --hidden-import "PyQt5" ^
           --hidden-import "PyQt5.QtCore" ^
           --hidden-import "PyQt5.QtWidgets" ^
           --hidden-import "PyQt5.QtGui" ^
           --hidden-import "selenium" ^
           --hidden-import "selenium.webdriver" ^
           --hidden-import "selenium.webdriver.chrome" ^
           --hidden-import "selenium.webdriver.chrome.service" ^
           --hidden-import "selenium.webdriver.common.by" ^
           --hidden-import "selenium.webdriver.chrome.options" ^
           --hidden-import "selenium.webdriver.support.ui" ^
           --hidden-import "selenium.webdriver.support" ^
           --hidden-import "selenium.webdriver.support.expected_conditions" ^
           --hidden-import "webdriver_manager" ^
           --hidden-import "webdriver_manager.chrome" ^
           --hidden-import "PIL" ^
           --hidden-import "PIL.Image" ^
           --hidden-import "requests" ^
           --hidden-import "bs4" ^
           --hidden-import "bs4.BeautifulSoup" ^
           --hidden-import "newspaper" ^
           --hidden-import "newspaper.article" ^
           --hidden-import "pyperclip" ^
           --hidden-import "win32clipboard" ^
           --hidden-import "win32con" ^
           --hidden-import "urllib" ^
           --hidden-import "urllib.parse" ^
           --hidden-import "datetime" ^
           --hidden-import "time" ^
           --hidden-import "io" ^
           --hidden-import "re" ^
           --hidden-import "platform" ^
           --hidden-import "subprocess" ^
           --hidden-import "os" ^
           --hidden-import "sys" ^
           --hidden-import "webbrowser" ^
           --collect-all "newspaper" ^
           --collect-all "bs4" ^
           --collect-all "requests" ^
           --collect-all "PIL" ^
           --collect-all "selenium" ^
           --collect-all "webdriver_manager" ^
           unified_gui.py

echo.
echo 2. Build completed!
echo.
echo 3. Checking results:
if exist "dist\UnifiedNewsTool.exe" (
    echo ✅ EXE file created successfully: dist\UnifiedNewsTool.exe
    echo.
    echo 📁 File size:
    dir "dist\UnifiedNewsTool.exe" | findstr "UnifiedNewsTool.exe"
) else (
    echo ❌ EXE file creation failed
)

echo.
echo 4. Test execution:
echo - Double-click UnifiedNewsTool.exe in the dist folder to run
echo - Chrome browser must be installed
echo.
pause 