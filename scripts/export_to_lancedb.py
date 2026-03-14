#!/usr/bin/env python3
"""
Export CtxFST Chunks to JSON for LanceDB/Vector DB Ingestion

Parses Markdown files with YAML frontmatter and <Chunk> tags,
outputs structured JSON suitable for LanceDB or other vector databases.

Usage:
    python export_to_lancedb.py <file.md> [--output chunks.json]
    python export_to_lancedb.py <directory> [--output chunks.json]

Output format:
{
  "entities": [
    {
      "id": "entity:python",
      "name": "Python",
      "type": "skill"
    }
  ],
  "chunks": [
    {
      "id": "skill:python",
      "context": "Author's Python skills...",
      "content": "## Python\n...",
      "tags": ["Python", "Backend"],
      "entities": ["entity:python"],
      "created_at": "2026-02-03",
      "version": 1,
      "type": "text",
      "priority": "high",
      "dependencies": [],
      "source": "path/to/file.md"
    }
  ]
}
"""

import sys
import re
import json
import argparse
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("Error: PyYAML required. Install with: pip install pyyaml")
    sys.exit(1)


def parse_frontmatter(content: str) -> tuple[dict | None, str]:
    """Parse YAML frontmatter from content."""
    if not content.startswith('---'):
        return None, content
    
    lines = content.split('\n')
    end_idx = None
    
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == '---':
            end_idx = i
            break
    
    if end_idx is None:
        return None, content
    
    frontmatter_text = '\n'.join(lines[1:end_idx])
    remaining = '\n'.join(lines[end_idx + 1:])
    
    try:
        frontmatter = yaml.safe_load(frontmatter_text)
        return frontmatter, remaining
    except yaml.YAMLError as e:
        print(f"Warning: Failed to parse frontmatter: {e}")
        return None, content


def extract_chunks(content: str) -> dict[str, str]:
    """Extract chunk ID -> content mapping from document body."""
    chunks = {}
    
    # Pattern to match <Chunk id="...">...</Chunk>
    pattern = re.compile(
        r'<Chunk\s+id=["\']([^"\']+)["\']>(.*?)</Chunk>',
        re.DOTALL | re.IGNORECASE
    )
    
    for match in pattern.finditer(content):
        chunk_id = match.group(1)
        chunk_content = match.group(2).strip()
        chunks[chunk_id] = chunk_content
    
    return chunks


def process_file(filepath: Path) -> dict[str, Any]:
    """Process a single file and return chunks and entities."""
    content = filepath.read_text(encoding='utf-8')
    frontmatter, body = parse_frontmatter(content)
    
    if not frontmatter or 'chunks' not in frontmatter:
        print(f"Warning: {filepath} has no frontmatter chunks")
        return {}
    
    # Extract chunk contents from body
    body_chunks = extract_chunks(body)
    
    # Build output records
    chunk_records = []
    for chunk_def in frontmatter['chunks']:
        chunk_id = chunk_def.get('id')
        if not chunk_id:
            continue

        content = body_chunks.get(chunk_id, '')
        if not content:
            print(f"Warning: No content found for chunk '{chunk_id}' in {filepath}")
            continue

        record = {
            'id': chunk_id,
            'context': chunk_def.get('context', ''),
            'content': content,
            'tags': chunk_def.get('tags', []),
            'source': str(filepath)
        }

        # Add entities if present
        if 'entities' in chunk_def:
            record['entities'] = chunk_def['entities']

        # Add optional 2026 RAG extension fields
        if 'created_at' in chunk_def:
            record['created_at'] = chunk_def['created_at']
        if 'version' in chunk_def:
            record['version'] = chunk_def['version']
        if 'type' in chunk_def:
            record['type'] = chunk_def['type']
        if 'priority' in chunk_def:
            record['priority'] = chunk_def['priority']
        if 'dependencies' in chunk_def:
            record['dependencies'] = chunk_def['dependencies']

        # v2.0 world model fields
        if 'state_refs' in chunk_def:
            record['state_refs'] = chunk_def['state_refs']

        chunk_records.append(record)
    
    entities = frontmatter.get('entities', [])

    # v2.0 world model: passthrough optional entity fields
    enriched_entities = []
    for ent in entities:
        enriched = dict(ent)  # shallow copy
        enriched_entities.append(enriched)

    return {'chunks': chunk_records, 'entities': enriched_entities}


def main():
    parser = argparse.ArgumentParser(
        description='Export CtxFST chunks to JSON for LanceDB'
    )
    parser.add_argument('input', help='Input file or directory')
    parser.add_argument(
        '--output', '-o',
        default='chunks.json',
        help='Output JSON file (default: chunks.json)'
    )
    parser.add_argument(
        '--pretty', '-p',
        action='store_true',
        help='Pretty-print JSON output'
    )
    
    args = parser.parse_args()
    target = Path(args.input)
    
    if target.is_file():
        files = [target]
    elif target.is_dir():
        files = list(target.glob('**/*.md'))
    else:
        print(f"Error: '{target}' not found")
        sys.exit(1)
    
    all_chunks = []
    all_entities = {}  # Deduplicate entities by ID
    
    for filepath in files:
        result = process_file(filepath)
        if not result:
            continue
        
        chunks = result.get('chunks', [])
        entities = result.get('entities', [])
        
        all_chunks.extend(chunks)
        for ent in entities:
            ent_id = ent.get('id')
            if ent_id and ent_id not in all_entities:
                all_entities[ent_id] = ent
                
        print(f"📄 {filepath}: {len(chunks)} chunks, {len(entities)} entities")
    
    output_data = {
        "entities": list(all_entities.values()),
        "chunks": all_chunks
    }
    
    # Write output
    output_path = Path(args.output)
    with output_path.open('w', encoding='utf-8') as f:
        if args.pretty:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        else:
            json.dump(output_data, f, ensure_ascii=False)
    
    print(f"\n{'='*50}")
    print(f"✅ Exported {len(all_chunks)} chunks and {len(all_entities)} entities to {output_path}")
    
    # Show sample record
    if all_chunks:
        print(f"\nSample record:")
        sample = all_chunks[0].copy()
        if len(sample.get('content', '')) > 100:
            sample['content'] = sample['content'][:100] + '...'
        print(json.dumps(sample, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
