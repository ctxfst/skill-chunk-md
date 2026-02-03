#!/usr/bin/env python3
"""
Validate Chunk Tags in Markdown Documents with Frontmatter Support

Checks for:
- Valid YAML frontmatter with chunk definitions
- Proper <Chunk> tag syntax
- All <Chunk> IDs match frontmatter entries
- Unique chunk IDs
- Balanced opening/closing tags
- No nested chunks

Usage:
    python validate_chunks.py <file.md>
    python validate_chunks.py <directory>
"""

import sys
import re
from pathlib import Path
from typing import NamedTuple

try:
    import yaml
except ImportError:
    print("Error: PyYAML required. Install with: pip install pyyaml")
    sys.exit(1)


class ValidationError(NamedTuple):
    line: int
    message: str
    severity: str  # 'error' or 'warning'


def parse_frontmatter(content: str) -> tuple[dict | None, str, int]:
    """
    Parse YAML frontmatter from content.
    Returns (frontmatter_dict, remaining_content, frontmatter_end_line).
    """
    if not content.startswith('---'):
        return None, content, 0
    
    lines = content.split('\n')
    end_idx = None
    
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == '---':
            end_idx = i
            break
    
    if end_idx is None:
        return None, content, 0
    
    frontmatter_text = '\n'.join(lines[1:end_idx])
    remaining = '\n'.join(lines[end_idx + 1:])
    
    try:
        frontmatter = yaml.safe_load(frontmatter_text)
        return frontmatter, remaining, end_idx + 1
    except yaml.YAMLError:
        return None, content, 0


def validate_file(filepath: Path) -> list[ValidationError]:
    """Validate chunk tags in a single file."""
    errors = []
    content = filepath.read_text(encoding='utf-8')
    
    # Parse frontmatter
    frontmatter, body_content, fm_end_line = parse_frontmatter(content)
    
    # Get chunk definitions from frontmatter
    fm_chunks = {}
    if frontmatter and 'chunks' in frontmatter:
        for i, chunk_def in enumerate(frontmatter['chunks']):
            if 'id' not in chunk_def:
                errors.append(ValidationError(
                    i + 2,  # Approximate line in frontmatter
                    f"Chunk definition {i+1} missing 'id' field",
                    'error'
                ))
                continue
            
            chunk_id = chunk_def['id']
            
            if chunk_id in fm_chunks:
                errors.append(ValidationError(
                    i + 2,
                    f"Duplicate chunk ID '{chunk_id}' in frontmatter",
                    'error'
                ))
            else:
                fm_chunks[chunk_id] = chunk_def
            
            # Warn if no context
            if 'context' not in chunk_def:
                errors.append(ValidationError(
                    i + 2,
                    f"Chunk '{chunk_id}' missing 'context' field",
                    'warning'
                ))
    elif frontmatter is None:
        errors.append(ValidationError(
            1,
            "No YAML frontmatter found",
            'warning'
        ))
    elif 'chunks' not in frontmatter:
        errors.append(ValidationError(
            1,
            "Frontmatter missing 'chunks' array",
            'warning'
        ))
    
    # Validate <Chunk> tags in body
    lines = body_content.split('\n')
    body_chunk_ids = {}  # id -> line number
    open_chunks = []  # stack of (id, line_number)
    
    open_pattern = re.compile(r'<Chunk\s+id=["\']([^"\']+)["\']>', re.IGNORECASE)
    close_pattern = re.compile(r'</Chunk>', re.IGNORECASE)
    
    for i, line in enumerate(lines, fm_end_line + 1):
        # Check for opening tags
        for match in open_pattern.finditer(line):
            chunk_id = match.group(1)
            
            # Check if ID exists in frontmatter
            if fm_chunks and chunk_id not in fm_chunks:
                errors.append(ValidationError(
                    i,
                    f"Chunk ID '{chunk_id}' not found in frontmatter",
                    'error'
                ))
            
            # Check for duplicate IDs in body
            if chunk_id in body_chunk_ids:
                errors.append(ValidationError(
                    i, 
                    f"Duplicate chunk ID '{chunk_id}' (first seen at line {body_chunk_ids[chunk_id]})",
                    'error'
                ))
            else:
                body_chunk_ids[chunk_id] = i
            
            # Check for nesting
            if open_chunks:
                errors.append(ValidationError(
                    i,
                    f"Nested chunk '{chunk_id}' inside '{open_chunks[-1][0]}' (opened at line {open_chunks[-1][1]})",
                    'error'
                ))
            
            open_chunks.append((chunk_id, i))
            
            # Validate ID format
            if not re.match(r'^[a-z]+:[a-z0-9-]+$', chunk_id):
                errors.append(ValidationError(
                    i,
                    f"Invalid chunk ID format '{chunk_id}' - use 'category:topic-name'",
                    'warning'
                ))
        
        # Check for closing tags
        for _ in close_pattern.finditer(line):
            if not open_chunks:
                errors.append(ValidationError(
                    i,
                    "Closing </Chunk> without matching opening tag",
                    'error'
                ))
            else:
                open_chunks.pop()
    
    # Check for unclosed chunks
    for chunk_id, line_num in open_chunks:
        errors.append(ValidationError(
            line_num,
            f"Unclosed chunk '{chunk_id}'",
            'error'
        ))
    
    # Check for frontmatter chunks not used in body
    if fm_chunks:
        for chunk_id in fm_chunks:
            if chunk_id not in body_chunk_ids:
                errors.append(ValidationError(
                    1,
                    f"Frontmatter chunk '{chunk_id}' not found in document body",
                    'warning'
                ))
    
    return errors


def main():
    if len(sys.argv) < 2:
        print("Usage: validate_chunks.py <file.md|directory>")
        sys.exit(1)
    
    target = Path(sys.argv[1])
    
    if target.is_file():
        files = [target]
    elif target.is_dir():
        files = list(target.glob('**/*.md'))
    else:
        print(f"Error: '{target}' not found")
        sys.exit(1)
    
    total_errors = 0
    total_warnings = 0
    
    for filepath in files:
        errors = validate_file(filepath)
        
        if errors:
            print(f"\n📄 {filepath}")
            for err in sorted(errors, key=lambda e: e.line):
                icon = "❌" if err.severity == 'error' else "⚠️"
                print(f"  {icon} Line {err.line}: {err.message}")
                if err.severity == 'error':
                    total_errors += 1
                else:
                    total_warnings += 1
    
    # Summary
    print(f"\n{'='*50}")
    if total_errors == 0 and total_warnings == 0:
        print("✅ All files valid!")
    else:
        print(f"Found {total_errors} error(s) and {total_warnings} warning(s)")
    
    sys.exit(1 if total_errors > 0 else 0)


if __name__ == "__main__":
    main()
