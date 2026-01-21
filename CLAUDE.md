# SD-Helper: Service Delivery Engineer Tool

A CLI tool for Huawei Cloud Service Delivery Engineers to streamline daily operations.

## Project Overview

This tool is designed to help service delivery engineers handle common tasks efficiently, especially for AI-related work on Huawei Cloud.

## Core Features

### 1. Authentication
- Fetch IAM auth tokens from Huawei Cloud
- Token caching and automatic refresh
- Support for multiple regions/projects

### 2. Common API Requests
- Simplified wrappers for frequently used Huawei Cloud APIs
- Request templates for common operations
- Response formatting and error handling

### 3. AI Services Integration
- **LLM Conversation**: CLI interface for interacting with LLM services
- **CV Predict**: Computer Vision model prediction calls
- **Forecast Models**: Time-series forecasting model invocation
- **Visualization**: Data and result visualization capabilities

### 4. Offline Data Collection
- Save data locally when connected to user networks without internet
- Structured storage format for collected data
- Sync mechanism when back online
- Network-aware operation mode

## Technical Stack

- Python 3.12+
- CLI framework: Click or Typer
- HTTP client: httpx/requests
- Data storage: JSON/SQLite for offline data
- Visualization: matplotlib/plotly

## Project Structure

```
sd-helper/
├── main.py              # CLI entry point
├── pyproject.toml       # Project config
├── claude.md            # This file
└── sd_helper/
    ├── __init__.py
    ├── auth.py          # Token fetching and management
    ├── api/             # API wrappers
    │   ├── __init__.py
    │   ├── llm.py       # LLM service calls
    │   ├── cv.py        # CV prediction calls
    │   └── forecast.py  # Forecast model calls
    ├── data/            # Offline data management
    │   ├── __init__.py
    │   ├── collector.py # Data collection
    │   └── storage.py   # Local storage
    └── viz/             # Visualization
        ├── __init__.py
        └── charts.py    # Chart generation
```

## Configuration

The tool uses a config file (`~/.sd-helper/config.json`) to store:
- IAM credentials (encrypted)
- Region preferences
- Project IDs
- Endpoint overrides

## Usage Examples

```bash
# Get auth token
sd-helper auth token

# Chat with LLM
sd-helper llm chat "What is ModelArts?"

# Run CV prediction
sd-helper cv predict --model <model-id> --image <path>

# Collect data offline
sd-helper data collect --output ./collected_data/

# Sync offline data
sd-helper data sync
```
