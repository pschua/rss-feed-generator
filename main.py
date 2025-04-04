import requests
from bs4 import BeautifulSoup
from datetime import timezone, datetime
from feedgen.feed import FeedGenerator
from urllib.parse import urlparse
import datefinder
import pytz

from fastapi import FastAPI, HTTPException, Response, BackgroundTasks
from pydantic import BaseModel, HttpUrl
from typing import Optional, Union, Dict, Any
from google.cloud import firestore
from datetime import datetime, timezone

from fastapi.middleware.cors import CORSMiddleware


app = FastAPI(title="RSS Feed Generator", 
              description="Create an RSS feed from a website",)
db = firestore.Client()


# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)


# region Pydantic models
class FeedSourceCreate(BaseModel):
    name: str
    url: str
    selector: str
    description: Optional[str] = None


class FeedSource(FeedSourceCreate):
    id: str
    last_refreshed: Optional[datetime] = None
# endregion


# region Helper functions
def scrape_website(feed_source):
    """Scrape a website for articles"""
    try:
        response = requests.get(str(feed_source['url']))
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        articles = soup.select(feed_source["selector"])

        items = []
        for i, article in enumerate(articles):
            title_elem = article.select_one("h1, h2, h3, h4, h5, h6 .title")
            link_elem = article.select_one('a') if article.select_one('a') else article

            if not title_elem or not link_elem:
                continue

            title = title_elem.text.strip() if title_elem else f"Article {i+1}"
            link = link_elem['href'] if link_elem else None

            # Fix relative links
            if link and not link.startswith(("http")):
                domain = urlparse(str(feed_source["url"])).netloc
                link = f"https://{domain}{'' if link.startswith('/') else '/'}{link}"
            
            # Extract description
            desc_elem = article.select("p, .summary, .description")
            if desc_elem:
                # Find the longest description element
                longest_desc_elem = max(desc_elem, key=lambda x: len(x.text)) if desc_elem else None
                description = longest_desc_elem.text.strip() if longest_desc_elem else ""
            else:
                description = article.get_text(" ", strip=True).replace(title, "").strip() 
            
            # Try to find date
            all_text = article.get_text(" ", strip=True) # get all text content
            matches = list(datefinder.find_dates(str(all_text), strict=True))
            if matches:
                pub_date = matches[0]
                time_aware_pub_date = pub_date.replace(tzinfo=pytz.UTC)
            else:
                print("No date found.")
                pub_date = None

            items.append({
                'title': title,
                'link': link,
                'description': description,
                'pub_date': time_aware_pub_date,
            })

        return items
    
    except Exception as e:
        print(f"Error scraping {feed_source['name']}: {str(e)}")
        return []
    

def generate_rss(feed_source, items):
    """Generate an RSS feed from a list of items"""
    fg = FeedGenerator()
    fg.title(feed_source.get('name', 'RSS Feed'))
    fg.description(feed_source.get('description', f"RSS feed for {feed_source['name']}"))
    fg.link(href=str(feed_source["url"]))
    fg.language("en")

    # Add the current date and time
    fg.pubDate(datetime.now(timezone.utc))

    # Add items to the feed
    for item in items:
        entry = fg.add_entry()
        entry.title(item.get('title', 'No Title'))
        entry.link(href= item.get('link'))
        entry.description(item.get('description', 'No Description'))
        entry.pubDate(item.get('pub_date', datetime.now(timezone.utc)))

    # Generate the feed
    return fg.rss_str(pretty=True)


def refresh_feed_task(feed_source):
    """Background task to refresh a feed"""
    items = scrape_website(feed_source)

    if not items:
        print(f"No items found for {feed_source['name']}")
        return
    
    rss_content = generate_rss(feed_source, items)

    # Store in Firestore
    content_ref = db.collection("feed_contents").document(feed_source["id"])
    content_ref.set({
        "content": rss_content.decode('utf-8'),  # Store as string
        "generated_at": datetime.now()
    })
    
    # Update timestamp
    source_ref = db.collection("feed_sources").document(feed_source["id"])
    source_ref.update({"last_refreshed": datetime.now()})
    
    print(f"Feed refreshed: {feed_source['name']} ({len(items)} items)")
# endregion 


# region API endpoints
@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "RSS Feed Generator API", "version": "1.0.0"}


# Add a new feed source
@app.post("/sources/", response_model=FeedSource)
async def add_source(source: FeedSourceCreate, background_tasks: BackgroundTasks):
    """Add a new feed source"""
    # Create source in Firestore
    source_data = source.dict()
    source_data["created_at"] = datetime.now()
    source_data["last_refreshed"] = None

    doc_ref = db.collection("feed_sources").document()
    doc_ref.set(source_data)

    # Prepare response data
    source_data["id"] = doc_ref.id
    
    # Queue background task to generate the feed immediately
    background_tasks.add_task(refresh_feed_task, source_data)

    return source_data


# List all sources
@app.get("/sources/", response_model=list[FeedSource])
async def list_sources():
    """List all feed sources"""
    sources = []
    for doc in db.collection("feed_sources").stream():
        source = doc.to_dict()
        source["id"] = doc.id
        sources.append(source)
    return sources


# Get a specific source
@app.get("/sources/{source_id}", response_model=FeedSource)
async def get_source(source_id: str):
    """Get a specific feed source"""
    doc_ref = db.collection("feed_sources").document(source_id)
    doc = doc_ref.get()

    if not doc.exists:
        raise HTTPException(status_code=404, detail="Feed source not found")
    
    source = doc.to_dict()
    source["id"] = doc.id
    return source


@app.delete("/sources/{source_id}")
async def delete_source(source_id: str):
    """Delete a feed source and its content"""
    doc_ref = db.collection("feed_sources").document(source_id)
    doc = doc_ref.get()
    
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Feed source not found")
    
    # Delete the source
    doc_ref.delete()
    
    # Delete associated content if it exists
    content_ref = db.collection("feed_contents").document(source_id)
    content_doc = content_ref.get()
    if content_doc.exists:
        content_ref.delete()
    
    return {"message": f"Feed source {source_id} deleted"}


@app.get("/feed/{source_id}")
async def get_feed(source_id: str, background_tasks: BackgroundTasks):
    """Get the RSS feed for a source"""
    # Get the source
    source_ref = db.collection("feed_sources").document(source_id)
    source_doc = source_ref.get()
    
    if not source_doc.exists:
        raise HTTPException(status_code=404, detail="Feed source not found")
    
    source = source_doc.to_dict()
    source["id"] = source_doc.id

    # Try to get the existing content
    content_ref = db.collection("feed_contents").document(source_id)
    content_doc = content_ref.get()

    # If no content exists, generate one now
    if not content_doc.exists:
        items = scrape_website(source)
        if not items:
            raise HTTPException(status_code=500, detail="Could not generate feed content")
            
        rss_content = generate_rss(source, items)
        
        # Store it
        content_ref.set({
            "content": rss_content.decode('utf-8'),
            "generated_at": datetime.now()
        })
        
        # Update timestamp
        source_ref.update({"last_refreshed": datetime.now()})
        
        return Response(content=rss_content, media_type="application/rss+xml")
    else:
        # Get the stored content
        content = content_doc.to_dict()
        
        # If content is old (more than 1 hour), refresh in background
        generated_at = content.get("generated_at")
        if not generated_at or (datetime.now(timezone.utc) - generated_at).total_seconds() > 3600:
            background_tasks.add_task(refresh_feed_task, source)
        
        return Response(content=content["content"], media_type="application/rss+xml")


@app.post("/refresh/{source_id}")
async def refresh_feed(source_id: str, background_tasks: BackgroundTasks):
    """Refresh a specific feed"""
    # Get the source
    source_ref = db.collection("feed_sources").document(source_id)
    source_doc = source_ref.get()
    
    if not source_doc.exists:
        raise HTTPException(status_code=404, detail="Feed source not found")
    
    source = source_doc.to_dict()
    source["id"] = source_doc.id
    
    # Refresh in background
    background_tasks.add_task(refresh_feed_task, source)
    
    return {"message": f"Feed refresh started for {source['name']}"}


@app.post("/refresh-all")
async def refresh_all_feeds(background_tasks: BackgroundTasks):
    """Refresh all feeds - endpoint for Cloud Scheduler"""
    count = 0
    for doc in db.collection("feed_sources").stream():
        source = doc.to_dict()
        source["id"] = doc.id
        background_tasks.add_task(refresh_feed_task, source)
        count += 1
    
    return {"message": f"Refreshing {count} feeds"}
# endregion


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)