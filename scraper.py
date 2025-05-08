from fastapi import FastAPI, HTTPException, Form, Request, File, UploadFile
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
import json
import shutil

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

# Settings file path
SETTINGS_FILE = "settings.json"

# Default settings
DEFAULT_SETTINGS = {
    "rankColor": "#CBA655",
    "playerNameColor": "#CBA655",
    "playerScoreColor": "#000000",
    "roundTitleColor": "#CBA655"
}

# Load settings from file
def load_settings():
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                return json.load(f)
        return DEFAULT_SETTINGS
    except Exception as e:
        logger.error(f"Error loading settings: {e}")
        return DEFAULT_SETTINGS

# Save settings to file
def save_settings(settings):
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f)
        return True
    except Exception as e:
        logger.error(f"Error saving settings: {e}")
        return False

# Get current settings
current_settings = load_settings()

# Store the list of players to watch
WATCHED_PLAYERS = []

@app.get("/")
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/stream-management")
async def stream_management(request: Request):
    return templates.TemplateResponse("stream_management.html", {"request": request})

@app.get("/stream")
async def read_stream(request: Request):
    # Get color parameters from query string
    rank_color = request.query_params.get("rankColor", current_settings["rankColor"])
    player_name_color = request.query_params.get("playerNameColor", current_settings["playerNameColor"])
    player_score_color = request.query_params.get("playerScoreColor", current_settings["playerScoreColor"])
    round_title_color = request.query_params.get("roundTitleColor", current_settings["roundTitleColor"])
    
    return templates.TemplateResponse("stream.html", {
        "request": request,
        "rankColor": rank_color,
        "playerNameColor": player_name_color,
        "playerScoreColor": player_score_color,
        "roundTitleColor": round_title_color
    })

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

@app.get("/players-management")
async def read_players_management(request: Request):
    return templates.TemplateResponse("players_management.html", {"request": request})

@app.post("/save-players")
async def save_players(players: dict):
    global WATCHED_PLAYERS
    WATCHED_PLAYERS = players.get("players", [])
    return {"message": "Players saved successfully"}

@app.get("/players")
async def read_players(request: Request, players: str = None):
    # If players are provided in the query, use those
    if players:
        try:
            player_list = json.loads(players)
        except:
            player_list = WATCHED_PLAYERS
    else:
        player_list = WATCHED_PLAYERS

    # Get color parameters from query string
    player_name_color = request.query_params.get("playerNameColor", current_settings.get("playerNameColor", "#CBA655"))
    player_score_color = request.query_params.get("playerScoreColor", current_settings.get("playerScoreColor", "#000000"))

    return templates.TemplateResponse("players.html", {
        "request": request,
        "players": player_list,
        "playerNameColor": player_name_color,
        "playerScoreColor": player_score_color
    })

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
        
        rows = table.find_all('tr')[1:]
        for row in rows:
            cols = row.find_all('td')
            if len(cols) >= 3:  # We need at least rank, player, and wins
                rank = cols[0].text.strip()
                player_cell = cols[1]
                
                # Find the wins column - it's either the last column or second to last
                wins = None
                for col in reversed(cols[2:]):  # Check from right to left
                    if col.text.strip().isdigit():
                        wins = col.text.strip()
                        break
                
                if not wins:
                    continue
                
                # Extract flag from player cell
                flag = None
                flag_element = player_cell.find(class_='flag')
                if flag_element:
                    flag_classes = [c for c in flag_element['class'] if c != 'flag']
                    if flag_classes:
                        flag = flag_classes[0].upper()
                
                # Hero is optional - only include if we have a 4th column and it's not the wins column
                hero = ''
                if len(cols) >= 4 and not cols[2].text.strip().isdigit():
                    hero = cols[2].text.strip()
                
                player_data = {
                    'rank': rank,
                    'player': player_cell.text.strip(),
                    'wins': wins,
                    'flag': flag,
                    'isDropped': rank == 'Dropped',
                    'hero': hero
                }
                
                if rank == 'Dropped':
                    dropped_players.append(player_data)
                else:
                    standings.append(player_data)
        
        logger.info(f"Found {len(standings)} active players and {len(dropped_players)} dropped players")
        
        # Only apply row range filter if not from a team page
        if source not in ['bluepitch', 'runaways', 'armory', 'sigil', 'vampires', 'players']:
            standings = standings[row_range["start"]:row_range["end"]]
            logger.info(f"Returning standings rows {row_range['start'] + 1}-{row_range['end']} of {len(standings)} total entries")
        else:
            # For team pages, return all standings without filtering
            logger.info(f"Returning all standings for team view")
        
        return JSONResponse(content={
            "standings": standings,
            "droppedPlayers": dropped_players,
            "total": len(standings) + len(dropped_players),
            "showing": "all" if source in ['bluepitch', 'runaways', 'armory', 'sigil', 'vampires', 'players'] else f"{row_range['start'] + 1}-{row_range['end']}"
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

@app.post("/upload-background")
async def upload_background(background: UploadFile = File(...)):
    try:
        # Ensure static directory exists
        static_dir = Path("static")
        static_dir.mkdir(exist_ok=True)
        
        # Save the uploaded file
        file_path = static_dir / "background.png"
        
        # Read the file content
        content = await background.read()
        
        # Save the file
        with file_path.open("wb") as buffer:
            buffer.write(content)
            
        logger.info(f"Background image uploaded successfully to {file_path}")
        return JSONResponse(content={"success": True, "message": "Background uploaded successfully"})
    except Exception as e:
        logger.error(f"Error uploading background: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"Error uploading background: {str(e)}"}
        )

@app.post("/save-settings")
async def save_stream_settings(settings: dict):
    global current_settings
    try:
        # Update current settings
        current_settings.update(settings)
        if save_settings(current_settings):
            return JSONResponse(content={"success": True, "message": "Settings saved successfully"})
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "message": "Failed to save settings"}
            )
    except Exception as e:
        logger.error(f"Error saving settings: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"Error saving settings: {str(e)}"}
        )

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv('PORT', 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
