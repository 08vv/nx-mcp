import sys
sys.path.insert(0, r"c:\Users\HP\nx-mcp\src")
from nx_mcp import nx_bridge

def run():
    journal_path = r"c:\Users\HP\nx-mcp\scratch\inspect_sketch.py"
    output_prt = r"c:\Users\HP\nx-mcp\scratch\inspect_sketch.prt"
    result = nx_bridge.run_journal(journal_path, output_prt)
    print(f"STDOUT:\n{result.stdout}")

if __name__ == "__main__":
    run()
