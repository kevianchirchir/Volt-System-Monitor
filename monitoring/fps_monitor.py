import subprocess
import os

PRESENTMON_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "tools",
    "PresentMon-2.6.0-x64.exe"
)

def start_presentmon():
    process = subprocess.Popen(
        [PRESENTMON_PATH, "--help"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    output, error = process.communicate()

    print(output)
    print(error)

start_presentmon()