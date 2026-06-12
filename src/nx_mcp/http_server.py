from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from nx_mcp.server import handle
import uvicorn

app = FastAPI()

@app.post("/mcp")
async def mcp_endpoint(request: Request):
    body = await request.json()
    result = handle(body)
    return JSONResponse(content=result)

def main():
    uvicorn.run(app, host="127.0.0.1", port=8765)

if __name__ == "__main__":
    main()