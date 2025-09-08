#!/usr/bin/env python
"""Demo script to add papers to manuscript collections."""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from src.database import get_session  
from src.models import Paper, Collection
from src.services.search_service import SearchService

def add_papers_to_collection_demo():
    session = next(get_session())
    search_service = SearchService()
    
    try:
        # Get collections
        collections = session.query(Collection).all()
        print(f"Found {len(collections)} collections:")
        for c in collections:
            print(f"  {c.id}: {c.name}")
        
        # Add ALD papers to first collection (ALD for Membrane Applications)
        if collections:
            collection = collections[0]  # ALD collection
            
            # Search for relevant papers
            ald_results = search_service.search("atomic layer deposition membrane", limit=5)
            print(f"\nFound {len(ald_results)} ALD membrane papers")
            
            added = 0
            for result in ald_results:
                paper = session.query(Paper).filter_by(id=result['id']).first()
                if paper and paper not in collection.papers:
                    collection.papers.append(paper)
                    added += 1
                    print(f"  Added: {paper.title[:50]}...")
            
            session.commit()
            print(f"✓ Added {added} papers to '{collection.name}'")
            
            # Show final count
            print(f"Collection now has {len(collection.papers)} papers")
    
    finally:
        session.close()

if __name__ == "__main__":
    add_papers_to_collection_demo()