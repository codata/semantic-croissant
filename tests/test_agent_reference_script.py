import subprocess
import sys
import os

def main():
    # Construct the path to the agent script
    agent_script = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "agents", "agent_reference_script.py"))
    
    # The queries we want to test
    queries = [
        "Ask Dataverse expert about UK climate datasets",
        "Collect variables from 2 Malawi datasets?",
        "Ask Dataverse expert about Honduras climate datasets",
        "Describe https://lnkd.in/p/eMN5nX5C"
    ]
    
    overall_success = True
    
    for i, query in enumerate(queries, 1):
        print(f"\n[{i}/{len(queries)}] Running test for agent script with query:\n'{query}'\n")
        
        # Run the agent script using subprocess
        result = subprocess.run(
            [sys.executable, agent_script, "-q", query, "--save-vault"],
            capture_output=True,
            text=True
        )
        
        # Print the outputs for logging
        if result.stdout:
            print("=== STDOUT ===")
            print(result.stdout)
            
        if result.stderr:
            print("=== STDERR ===")
            print(result.stderr)
            
        # Verify the execution was successful
        if result.returncode == 0:
            print(f"\n✅ Query passed successfully.")
        else:
            print(f"\n❌ Query failed with return code {result.returncode}.")
            overall_success = False

    if overall_success:
        print("\n✅ All agent script tests passed successfully.")
    else:
        print("\n❌ One or more agent script tests failed.")
        sys.exit(1)

if __name__ == "__main__":
    main()
