# Impact RPA - Send Proposal Automation Tool

Impact RPA is an automated tool for sending proposal requests on the Impact.com platform. It features both a command-line interface and a graphical user interface.

## Features

- **Automated Proposal Sending**: Send multiple "Send Proposal" requests automatically
- **Template Management**: Create and manage multiple message templates
- **Browser Control**: Connect and control Chrome browser for automation
- **Settings Configuration**: Configure delays, sending limits and other parameters
- **GUI Interface**: User-friendly graphical interface with multiple tabs for different functions

## Requirements

- Python 3.11 or higher
- Compatible with Chrome browser

## Installation

This project uses `uv` for package management:

```bash
# Install uv if you don't have it
pip install uv

# Install project dependencies
uv sync

# Run the GUI
uv run python gui.py

# Or run the CLI
uv run python main.py
```

## Usage

### Graphical User Interface (GUI)

Run the GUI interface with:

```bash
uv run python gui.py
```

The GUI provides the following functionality:

1. **🚀 Send Control**: Start/stop sending proposals with progress tracking
2. **📄 Template Management**: Create, edit, delete and activate message templates
3. **⚙️ Settings**: Configure sending limits and delay settings
4. **🌐 Browser Control**: Connect/disconnect browser and navigate to specific pages

### Command Line Interface (CLI)

Run the CLI interface with:

```bash
uv run python main.py
```

Follow the interactive prompts to configure and execute the automation.

## Configuration

Settings and templates are stored in the `config/` directory:
- `settings.json` - Application settings (limits, delays)
- `templates.json` - Message templates