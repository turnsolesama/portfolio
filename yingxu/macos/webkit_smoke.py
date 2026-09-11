from pathlib import Path
import subprocess
import sys

root=Path(__file__).resolve().parents[1]
executable=root/'.release-work/macos/dist/YingXu.app/Contents/MacOS/YingXu'
result=subprocess.run([str(executable),'--ui-smoke-test'],capture_output=True,timeout=100)
report=root/'releases/macos-preview/webkit-verification.txt'
report.write_bytes(result.stdout+b'\n'+result.stderr)
print(result.stdout.decode('utf-8',errors='replace'))
print(result.stderr.decode('utf-8',errors='replace'))
sys.exit(result.returncode)
