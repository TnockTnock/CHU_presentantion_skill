#!/usr/bin/env python3
"""Search the explicitly configured LOCAL reference catalog; no remote requests."""
import argparse
import json
import os
from pathlib import Path

def search(catalog, query, limit=10):
    path=Path(catalog).expanduser().resolve()
    data=json.loads(path.read_text(encoding="utf-8"))
    words=query.casefold().split();results=[]
    for doc in data['documents']:
        for page in doc['pages']:
            if 'same_pixels_as' in page:continue
            text=doc['path']+' '+page['text']+' '+' '.join(page.get('patterns',[]))
            if all(word in text.casefold() for word in words):
                results.append({'document':doc['path'],'source':str(Path(data['source_root'])/doc['path']),'sha256':doc['sha256'],'page':page['page'],'preview':str(path.parent/page['preview']),'review':page.get('review','unreviewed'),'patterns':page.get('patterns',[]),'excerpt':page['text'][:500]})
    return results[:limit]

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('query');ap.add_argument('--catalog');ap.add_argument('--limit',type=int,default=10);a=ap.parse_args()
    config=Path(__file__).resolve().parents[1]/'local/reference-library.json'
    catalog=a.catalog or os.environ.get('CGU_REFERENCE_LIBRARY')
    if not catalog and config.exists():catalog=json.loads(config.read_text(encoding="utf-8"))['catalog_path']
    if not catalog:ap.error('Use --catalog, CGU_REFERENCE_LIBRARY or personal local/reference-library.json')
    if a.limit<1:ap.error('--limit must be positive')
    print(json.dumps(search(catalog,a.query,a.limit),ensure_ascii=False,indent=2))
