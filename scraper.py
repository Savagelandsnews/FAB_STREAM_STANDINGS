from fastapi import FastAPI, HTTPException, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
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

# Store the current URL and cache
current_url = ""
cache = {}  # URL -> (data, timestamp)
CACHE_DURATION = 30  # seconds

@app.get("/")
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/stream")
async def read_stream(request: Request):
    return templates.TemplateResponse("stream.html", {"request": request})

@app.get("/standings")
async def get_standings():
    global current_url, cache
    
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
            # Log more HTML details
            logger.debug(f"HTML structure: {soup.prettify()[:1000]}...")  # First 1000 chars of formatted HTML
            logger.debug(f"All tables found: {len(soup.find_all('table'))}")
            logger.debug(f"All table-like elements: {soup.find_all(['table', 'div', 'section'])[:5]}")
            return JSONResponse(
                status_code=404,
                content={"error": "No standings found"}
            )
        
        standings = []
        for row in table.find_all('tr')[1:]:  # Skip header row
            cols = row.find_all('td')
            if len(cols) >= 3:
                # Look for country/flag information
                flag = None
                player_cell = cols[1]
                for element in player_cell.find_all(class_='flag'):
                    flag_classes = [c for c in element['class'] if c != 'flag']
                    if flag_classes:
                        flag = flag_classes[0].upper()
                        break
                
                standings.append({
                    'rank': cols[0].text.strip(),
                    'player': cols[1].text.strip(),
                    'wins': cols[2].text.strip(),
                    'flag': flag
                })
        
        logger.info(f"Successfully fetched {len(standings)} standings entries")
        if standings:
            logger.debug(f"First entry: {standings[0]}")
        
        return JSONResponse(content={"standings": standings})
        
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

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv('PORT', 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
