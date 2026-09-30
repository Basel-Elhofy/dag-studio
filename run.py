"""Entry point for the Dynamic DAG Multi-Agent Code Generation Studio.

Usage:
    python run.py                # starts on http://localhost:8000
    python run.py --port 9000
"""
import argparse
import uvicorn

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DAG Multi-Agent Studio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    uvicorn.run("server.main:app", host=args.host, port=args.port, reload=args.reload)
