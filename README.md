# RSS Generator

A simple RSS feed generator built with Python. Generate and manage RSS feeds from any website by scraping content using custom CSS selectors.

## Features

- Generate RSS feeds from various data sources.
- Customizable feed attributes.
- Lightweight and easy to use.

## Tech Used
- **FastAPI**: Modern, high-performance web framework for building APIs
- **Pydantic**: Data validation and settings management
- **Google Cloud Firestore**: NoSQL document database for cloud storage
- **BeautifulSoup4**: Library for parsing HTML and extracting data
- **FeedGen**: Library for generating RSS/Atom feeds
- **Uvicorn**: ASGI server for serving the FastAPI application
- **Python 3.8+**: Modern Python with type annotations

## Pre-requisites
- Python 3.8 or higher
- Google Cloud account with Firestore enabled
- Google Cloud SDK installed and configured

## Installation

1. Clone the repository:
    ```bash
    git clone https://github.com/pschua/rss-feed-generator.git
    ```
2. Navigate to the project directory:
    ```bash
    cd rss-feed-generator
    ```
3. Create and activate a virtual environment:
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```
4. Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
5. Set up Google Cloud Credentials
    ```bash
    # Set the application default credentials
    gcloud auth application-default login

    # Or set the GOOGLE_APPLICATION_CREDENTIALS environment variable
    export GOOGLE_APPLICATION_CREDENTIALS="path/to/your/service-account-key.json"
    ``` 

## Usage

### Running the API locally
```bash
uvicorn main:app --reload
```
The API will be available at http://localhost:8000

### API Documentations
Once running, access the auto-generated API documentation at:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc


### Creating a New Feed Source
To create a new feed source, send a POST request to /sources/ with a JSON body:

    ```json
    {
        "name": "Example Blog",
        "url": "https://example.com/blog",
        "selector": "article.post",
        "description": "Example blog feed"
    }
    ```

The selector is a CSS selector that identifies each article or content item on the page. The API will look for title elements (h1, h2, h3, .title), links (a), and description elements (p, .summary, .description) within each matched element.

It's recommended to find and test the right selector in a separate bs4 script before adding the feed configuration.

## License

This project is licensed under the [MIT License](LICENSE).