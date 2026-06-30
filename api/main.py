from fastapi import FastAPI, Request, BackgroundTasks
import os
import time
import subprocess
import shutil
from rdflib import Graph

app = FastAPI(title="Semantic Croissant API")

DATA_DIR = "/data"
INDEX_DIR = "/volumes/server"
DATA_FILE = os.path.join(DATA_DIR, "data.nt")
QLEVER_FILE = os.path.join(INDEX_DIR, "Qleverfile")

def generate_qleverfile():
    content = """[data]
NAME = croissant
GET_DATA_CMD = cat data.nt > croissant.nt
INDEX_INPUT_FILES = croissant.nt

[server]
PORT = 7011
ACCESS_TOKEN = croissant_7643543846_Zs6nw7yi3Z9m
HOST_NAME = server-croissant-live

[runtime]
SERVER_CONTAINER = semantic-croissant-server-croissant-live-1
SYSTEM = native
"""
    with open(QLEVER_FILE, "w") as f:
        f.write(content)

def rebuild_index():
    if not os.path.exists(QLEVER_FILE):
        generate_qleverfile()
    
    # Copy data.nt to INDEX_DIR so qlever-index container can see it
    shutil.copy(DATA_FILE, os.path.join(INDEX_DIR, "data.nt"))
    
    print("Starting QLever index rebuild...")
    try:
        # Change ownership so server-croissant-live (user 65534) can access them
        os.chown(QLEVER_FILE, 65534, 0)
        dest_data = os.path.join(INDEX_DIR, "data.nt")
        os.chown(dest_data, 65534, 0)
        os.chown(DATA_FILE, 65534, 0)
    except Exception as e:
        print(f"Warning: Could not change ownership: {e}")

    try:
        # We run the command in the DATA_DIR where Qleverfile is located
        subprocess.run(
            ["qlever", "rebuild-index", "--restart-when-finished"],
            cwd=INDEX_DIR,
            check=True
        )
        print("Index rebuild completed and server restarted.")
    except subprocess.CalledProcessError as e:
        print(f"Error rebuilding index: {e}")

@app.post("/add_record")
async def add_record(request: Request, background_tasks: BackgroundTasks):
    payload = await request.body()
    
    # 1. Convert JSON-LD to NTriples
    try:
        g = Graph()
        g.parse(data=payload, format='json-ld')
        nt_data = g.serialize(format='nt')
    except Exception as e:
        return {"error": f"Failed to parse JSON-LD: {str(e)}"}, 400

    # 2. Append to data.nt
    try:
        with open(DATA_FILE, "a") as f:
            f.write(nt_data)
            # Add a newline just in case
            if not nt_data.endswith("\n"):
                f.write("\n")
    except Exception as e:
        return {"error": f"Failed to write to {DATA_FILE}: {str(e)}"}, 500

    # 3. Trigger rebuild in background
    background_tasks.add_task(rebuild_index)
    
    return {"status": "success", "message": "Record added and index rebuild scheduled."}

@app.get("/health")
def health():
    return {"status": "ok"}
