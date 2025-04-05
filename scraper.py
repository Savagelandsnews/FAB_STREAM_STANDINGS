from fastapi import FastAPI, HTTPException, Form, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import aiohttp
from bs4 import BeautifulSoup
import logging
import os
from pathlib import Path
import asyncio
import json
import time

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup templates
templates = Jinja2Templates(directory="templates")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add row range state
current_url = ""
row_range = {"start": 0, "end": 10}  # Default to first 10 rows
cache = {}  # URL -> (data, timestamp)
CACHE_DURATION = 30  # seconds

# Add to the global variables at the top
current_round = 1

# Add WebSocket manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                # Remove disconnected clients
                self.active_connections.remove(connection)

manager = ConnectionManager()

@app.get("/")
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/stream")
async def read_stream(request: Request):
    return templates.TemplateResponse("stream.html", {"request": request})

@app.get("/bluepitch")
async def read_bluepitch(request: Request):
    return templates.TemplateResponse("bluepitch.html", {"request": request})

@app.get("/runaways")
async def read_runaways(request: Request):
    return templates.TemplateResponse("runaways.html", {"request": request})

@app.get("/armory")
async def read_armory(request: Request):
    return templates.TemplateResponse("armory.html", {"request": request})

@app.get("/sigil")
async def read_sigil(request: Request):
    return templates.TemplateResponse("sigil.html", {"request": request})

@app.get("/vampires")
async def read_vampires(request: Request):
    return templates.TemplateResponse("vampires.html", {"request": request})

class RowRange(BaseModel):
    start: int
    end: int

@app.post("/update-range")
async def update_range(range_data: RowRange):
    global row_range
    logger.info(f"Updating row range to: {range_data.start}-{range_data.end}")
    row_range = {"start": range_data.start, "end": range_data.end}
    return JSONResponse(content={
        "success": True,
        "message": f"Now showing rows {range_data.start + 1}-{range_data.end}"
    })

@app.get("/standings")
async def get_standings(source: str = None):
    global current_url, cache, row_range
    
    try:
        if not current_url:
            return JSONResponse(
                status_code=400,
                content={"error": "No URL set"}
            )

        # Check if we need to refresh the cache
        if not cache or time.time() - cache['timestamp'] > CACHE_DURATION:
            logger.info(f"Fetching standings from: {current_url}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(current_url) as response:
                    html_content = await response.text()
                    logger.debug(f"Received HTML content length: {len(html_content)}")
                    
                    # Parse standings
                    active_players, dropped_players = parse_standings(html_content)
                    logger.info(f"Found {len(active_players)} active players and {len(dropped_players)} dropped players")
                    
                    # Update cache
                    cache = {
                        'timestamp': time.time(),
                        'active_players': active_players,
                        'dropped_players': dropped_players
                    }

        # Get players from cache
        active_players = cache['active_players']
        dropped_players = cache['dropped_players']

        # For bluepitch view, return all players
        if source == 'bluepitch':
            standings = active_players
        else:
            # Apply row range filter
            start = row_range['start']
            end = min(row_range['end'], len(active_players))
            standings = active_players[start:end]
            logger.info(f"Returning standings rows {start + 1}-{end} of {len(active_players)} total entries")

        # Prepare response data
        response_data = {
            "standings": standings,
            "droppedPlayers": dropped_players,
            "total": len(active_players) + len(dropped_players),
            "showing": "all" if source == 'bluepitch' else f"{row_range['start'] + 1}-{row_range['end']}"
        }
        
        # Broadcast to all WebSocket clients
        await manager.broadcast(json.dumps(response_data))
        
        return JSONResponse(content=response_data)
        
    except Exception as e:
        logger.error(f"Error fetching standings: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Internal server error: {str(e)}"}
        )

@app.post("/update-url")
async def update_url(url: str = Form(...)):
    global current_url
    logger.info(f"Updating URL to: {url}")
    current_url = url
    
    # Validate the URL works
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(f"URL validation failed with status {response.status}")
                    return JSONResponse(
                        status_code=400,
                        content={"success": False, "message": "Invalid URL - could not fetch standings"}
                    )
                logger.info("URL validation successful")
    except Exception as e:
        logger.error(f"URL validation error: {e}")
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": f"Invalid URL - {str(e)}"}
        )
    
    return JSONResponse(content={"success": True, "message": "URL updated successfully"})

@app.post("/update-round")
async def update_round(round_data: dict):
    global current_round
    logger.info(f"Updating round number to: {round_data['round']}")
    current_round = round_data['round']
    return JSONResponse(content={
        "success": True,
        "message": f"Updated to Round {current_round}"
    })

@app.get("/round")
async def get_round():
    global current_round
    return JSONResponse(content={"round": current_round})

@app.get("/get-round")
async def get_round_legacy():
    global current_round
    return JSONResponse(content={"round": current_round})

# Add WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv('PORT', 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
