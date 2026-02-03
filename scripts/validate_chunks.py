#!/usr/bin/env python3
"""
Validate Chunk Tags in Markdown Documents

Checks for:
- Proper <Chunk> tag syntax
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


class ValidationError(NamedTuple):
    line: int
    message: str
    severity: str  # 'error' or 'warning'


def validate_file(filepath: Path) -> list[ValidationError]:
    """Validate chunk tags in a single file."""
    errors = []
    content = filepath.read_text(encoding='utf-8')
    lines = content.split('\n')
    
    # Track state
    chunk_ids = {}  # id -> line number
    open_chunks = []  # stack of (id, line_number)
    
    # Patterns
    open_pattern = re.compile(r'<Chunk\s+id=["\']([^"\']+)["\']>', re.IGNORECASE)
    close_pattern = re.compile(r'</Chunk>', re.IGNORECASE)
    
    for i, line in enumerate(lines, 1):
        # Check for opening tags
        for match in open_pattern.finditer(line):
            chunk_id = match.group(1)
            
            # Check for duplicate IDs
            if chunk_id in chunk_ids:
                errors.append(ValidationError(
                    i, 
                    f"Duplicate chunk ID '{chunk_id}' (first seen at line {chunk_ids[chunk_id]})",
                    'error'
                ))
            else:
                chunk_ids[chunk_id] = i
            
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
