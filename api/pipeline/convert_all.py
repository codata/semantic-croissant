import os
import sys
import time
from multiprocessing import Pool
from rdflib import Graph

def process_file(filepath):
    try:
        g = Graph()
        g.parse(filepath, format='json-ld')
        return g.serialize(format='nt')
    except Exception as e:
        return f"# ERROR parsing {filepath}: {e}\n"

def main():
    folder = "/mediaquantum/qlever/croissant"
    output_file = "/mediaquantum/qlever/qlever-tests/data/data.nt"
    
    files = [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith('.json')]
    total_files = len(files)
    print(f"Found {total_files} JSON files to process.")
    
    start_time = time.time()
    
    # Process files in parallel
    with open(output_file, "w") as out_f:
        with Pool() as pool:
            for idx, ntriples in enumerate(pool.imap_unordered(process_file, files, chunksize=100)):
                out_f.write(ntriples)
                
                if (idx + 1) % 1000 == 0:
                    elapsed = time.time() - start_time
                    rate = (idx + 1) / elapsed
                    eta = (total_files - (idx + 1)) / rate
                    print(f"Processed {idx + 1}/{total_files} files... Elapsed: {elapsed:.2f}s | Rate: {rate:.2f} files/s | ETA: {eta:.2f}s", flush=True)

    print(f"Conversion complete in {time.time() - start_time:.2f}s!")

if __name__ == "__main__":
    main()
