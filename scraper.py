from fastapi import FastAPI, HTTPException, Form, Request
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

@app.get("/")
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/stream")
async def read_stream(request: Request):
    return templates.TemplateResponse("stream.html", {"request": request})

@app.get("/bluepitch")
async def read_bluepitch(request: Request):
    return templates.TemplateResponse("bluepitch.html", {"request": request})

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
    
    if not current_url:
        logger.warning("No URL set for standings fetch")
        return JSONResponse(
            status_code=400,
            content={"error": "No URL set. Please set a URL first."}
        )
    
    try:
        logger.info(f"Fetching standings from: {current_url}")
        async with aiohttp.ClientSession() as session:
            async with session.get(current_url) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch standings: HTTP {response.status}")
                    return JSONResponse(
                        status_code=503,
                        content={"error": "Unable to fetch standings"}
                    )
                
                html = await response.text()
                logger.debug(f"Received HTML content length: {len(html)}")
                
        soup = BeautifulSoup(html, 'html.parser')
        table = soup.find('table')
        
        if not table:
            logger.error("No standings table found in the response")
            return JSONResponse(
                status_code=404,
                content={"error": "No standings found"}
            )
        
        standings = []
        dropped_players = []
        is_dropped = False
        
        for row in table.find_all('tr')[1:]:  # Skip header row
            cols = row.find_all('td')
            if len(cols) >= 3:
                rank = cols[0].text.strip()
                if rank == 'Dropped':
                    is_dropped = True
                    continue
                    
                player_data = {
                    'rank': rank,
                    'player': cols[1].text.strip(),
                    'wins': cols[2].text.strip()
                }
                
                if is_dropped:
                    dropped_players.append(player_data)
                else:
                    standings.append(player_data)
        
        # Only apply row range filter if not from bluepitch
        if source != 'bluepitch':
            standings = standings[row_range["start"]:row_range["end"]]
            logger.info(f"Returning standings rows {row_range['start'] + 1}-{row_range['end']} of {len(standings)} total entries")
        else:
            logger.info(f"Returning all standings for bluepitch view")
        
        return JSONResponse(content={
            "standings": standings,
            "droppedPlayers": dropped_players,
            "total": len(standings),
            "showing": "all" if source == 'bluepitch' else f"{row_range['start'] + 1}-{row_range['end']}"
        })
        
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

@app.get("/get-round")
async def get_round():
    global current_round
    return JSONResponse(content={"round": current_round})

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv('PORT', 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
