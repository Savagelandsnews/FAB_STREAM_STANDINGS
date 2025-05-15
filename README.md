# FAB Tournament Standings Viewer

A web application for displaying and managing Flesh and Blood (FAB) tournament standings in real-time. This application provides a stream-friendly interface for tournament organizers and viewers.

## Features

- Real-time standings updates
- Stream overlay with customizable colors and backgrounds
- Player tracking system
- Team management
- Hero image support
- Flag display for international players
- Round tracking
- Responsive design for stream layouts

## Setup

1. Clone the repository:
```bash
git clone [repository-url]
cd fab-standings-viewer
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run the application:
```bash
python scraper.py
```

The application will be available at `http://localhost:8000`

## Usage

### Main Views
- `/` - Main management interface
- `/stream` - Stream overlay view
- `/players` - Player tracking view
- `/team-management` - Team management interface

### Customization
- Upload custom backgrounds for stream and player views
- Customize text colors for different elements
- Add hero images to the `static/Heroes` directory

## Project Structure

```
├── scraper.py          # Main application file
├── requirements.txt    # Python dependencies
├── static/            # Static assets
│   ├── Heroes/        # Hero images
│   └── teams/         # Team backgrounds
├── templates/         # HTML templates
└── settings.json      # User settings
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

[Your License Here]

## Contact

[Your Contact Information] 