import sys
import os
from fastapi import FastAPI

print('--- MINIMAL FASTAPI STARTUP ---')
print('CWD:', os.getcwd())
print('ENV:', dict(os.environ))
print('Python version:', sys.version)
print('-------------------------------')

app = FastAPI()

@app.get("/")
def root():
    print('Root endpoint hit!')
    return {"status": "ok", "message": "Minimal FastAPI app is running."} 