"""
Seed demo topics script:
Pre-fetches and caches OpenAlex & Semantic Scholar responses for 3 core topics:
1. "AI in diabetic healthcare"
2. "Federated learning client drift"
3. "Graph neural networks for cybersecurity"
Run this script to prime the disk cache for offline / instant demo loading.
"""
import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend_dir))

from app.database import SessionLocal
from app.services.discovery import DiscoveryService


DEMO_TOPICS = [
    "AI in diabetic healthcare",
    "Federated learning client drift",
    "Graph neural networks for cybersecurity",
]


def seed_demo_cache():
    ds = DiscoveryService()
    print("=" * 60)
    print("Seeding Discovery Cache for Demo Topics")
    print("=" * 60)

    for topic in DEMO_TOPICS:
        print(f"\n[Topic] Expanding: {topic}")
        queries = ds._expand_queries(topic)
        for q in queries:
            print(f"  -> Caching OpenAlex: '{q}'")
            try:
                oa_papers = ds._fetch_openalex(q, limit=10)
                print(f"     Found {len(oa_papers)} papers.")
            except Exception as e:
                print(f"     OpenAlex warning: {e}")

            print(f"  -> Caching Semantic Scholar: '{q}'")
            try:
                s2_papers = ds._fetch_semantic_scholar(q, limit=5)
                print(f"     Found {len(s2_papers)} papers.")
            except Exception as e:
                print(f"     Semantic Scholar warning: {e}")

    print("\n[Done] Demo topic cache successfully primed.")


if __name__ == "__main__":
    seed_demo_cache()
