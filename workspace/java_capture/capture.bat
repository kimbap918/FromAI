@echo off
rem === Java Capture 실행 ===
mvn -q exec:java -Dexec.mainClass=Capture -Dexec.args="%*"
