from minio import Minio
import os
try:
    client = Minio(
        "localhost:9005",
        access_key=os.environ.get("MINIO_ROOT_USER", "minioadmin"),
        secret_key=os.environ.get("MINIO_ROOT_PASSWORD", "minioadmin"),
        secure=False
    )
    objects = client.list_objects("vault", prefix="uc3_ground_subsidence", recursive=True)
    for obj in objects:
        print(obj.object_name)
except Exception as e:
    print(e)
