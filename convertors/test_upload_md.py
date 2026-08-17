import os
import sys

sys.path.append(os.path.join(os.getcwd(), 'convertors'))
from gdrive_utils import upload_to_gdrive

folder_id = "0AAObXJILB1CgUk9PVA"
file_path = "/app/convertors/test_markdown.md"
upload_to_gdrive("test@example.com", [file_path], target_folder_id=folder_id)
