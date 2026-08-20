import unittest
import sys
import os
import subprocess
import glob

class DynamicTests(unittest.TestCase):
    pass

def make_test_function(test_script):
    def test(self):
        # Run the script in a subprocess
        result = subprocess.run(
            [sys.executable, test_script],
            capture_output=True,
            text=True
        )
        
        # If it failed, fail the unit test and output stderr
        if result.returncode != 0:
            self.fail(f"Script {test_script} failed with exit code {result.returncode}.\n\nSTDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}")
            
    return test

if __name__ == '__main__':
    # Find all test_*.py files in the tests directory
    tests_dir = os.path.dirname(os.path.abspath(__file__))
    test_files = glob.glob(os.path.join(tests_dir, 'test_*.py'))
    
    # We want to skip this runner script itself if it matched
    test_files = [f for f in test_files if not f.endswith('run_all_tests.py')]
    
    # Dynamically add a test method for each script
    for test_file in test_files:
        test_name = 'test_' + os.path.basename(test_file).replace('.py', '')
        test_func = make_test_function(test_file)
        
        # Attach the function to our TestCase class
        setattr(DynamicTests, test_name, test_func)
    
    # Run the tests
    print(f"Discovered {len(test_files)} test scripts. Running as subprocesses...\n")
    unittest.main(verbosity=2)
