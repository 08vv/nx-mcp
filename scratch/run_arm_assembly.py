import sys
sys.path.insert(0, r"c:\Users\HP\nx-mcp\src")
from nx_mcp import nx_bridge
from pathlib import Path

def run():
    journal_path = r"c:\Users\HP\nx-mcp\src\nx_mcp\journals\create_arm_assembly.py"
    output_prt   = r"c:\Users\HP\nx-mcp\arm.prt"
    output_step  = r"c:\Users\HP\nx-mcp\arm.step"
    print(f"Running journal: {journal_path}")
    result = nx_bridge.run_journal(journal_path, output_prt, output_step)
    print(f"Return code: {result.returncode}")
    print(f"STDOUT:\n{result.stdout}")
    if result.stderr:
        print(f"STDERR:\n{result.stderr}")

if __name__ == "__main__":
    run()
