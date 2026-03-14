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
from datetime import datetime

try:
    import yaml
except ImportError:
    print("Error: PyYAML required. Install with: pip install pyyaml")
    sys.exit(1)


class ValidationError(NamedTuple):
    line: int
    message: str
    severity: str  # 'error' or 'warning'


VALID_ENTITY_TYPES = {
    # v1.1 descriptive types
    'skill', 'tool', 'library', 'framework', 'platform',
    'database', 'architecture', 'protocol', 'concept',
    'domain', 'product',
    # v2.0 operational types
    'state', 'action', 'goal', 'agent', 'evidence',
}

VALID_PRIORITIES = {'low', 'medium', 'high', 'critical'}


def validate_temporal_fields(chunk_def: dict, chunk_id: str, line_num: int) -> list[ValidationError]:
    """Validate temporal fields (created_at, version)."""
    errors = []

    if 'created_at' in chunk_def:
        try:
            datetime.fromisoformat(chunk_def['created_at'])
        except (ValueError, TypeError):
            errors.append(ValidationError(
                line_num,
                f"Chunk '{chunk_id}': Invalid 'created_at' format (use YYYY-MM-DD)",
                'error'
            ))

    if 'version' in chunk_def:
        if not isinstance(chunk_def['version'], int) or chunk_def['version'] < 1:
            errors.append(ValidationError(
                line_num,
                f"Chunk '{chunk_id}': 'version' must be a positive integer",
                'error'
            ))

    return errors


def validate_agentic_fields(chunk_def: dict, chunk_id: str, line_num: int, all_chunk_ids: set) -> list[ValidationError]:
    """Validate agentic fields (priority, dependencies)."""
    errors = []

    if 'priority' in chunk_def:
        if chunk_def['priority'] not in VALID_PRIORITIES:
            errors.append(ValidationError(
                line_num,
                f"Chunk '{chunk_id}': 'priority' must be one of {sorted(VALID_PRIORITIES)}",
                'error'
            ))

    if 'dependencies' in chunk_def:
        if not isinstance(chunk_def['dependencies'], list):
            errors.append(ValidationError(
                line_num,
                f"Chunk '{chunk_id}': 'dependencies' must be a list of chunk IDs",
                'error'
            ))
        else:
            for dep in chunk_def['dependencies']:
                if not isinstance(dep, str):
                    errors.append(ValidationError(
                        line_num,
                        f"Chunk '{chunk_id}': dependency must be string ID, got {type(dep).__name__}",
                        'error'
                    ))
                elif dep not in all_chunk_ids and dep != chunk_id:
                    errors.append(ValidationError(
                        line_num,
                        f"Chunk '{chunk_id}': dependency '{dep}' not found in chunks",
                        'warning'
                    ))

    return errors


def validate_multimodal_fields(chunk_def: dict, chunk_id: str, line_num: int, doc_dir: Path) -> list[ValidationError]:
    """Validate multi-modal fields (type, content_path)."""
    errors = []

    if 'type' in chunk_def:
        valid_types = ['text', 'image', 'video', 'audio']
        if chunk_def['type'] not in valid_types:
            errors.append(ValidationError(
                line_num,
                f"Chunk '{chunk_id}': 'type' must be one of {valid_types}",
                'error'
            ))

    if 'content_path' in chunk_def:
        path_str = chunk_def['content_path']
        if chunk_def.get('type') in ['image', 'video', 'audio']:
            full_path = doc_dir / path_str
            if not full_path.exists():
                errors.append(ValidationError(
                    line_num,
                    f"Chunk '{chunk_id}': content_path '{path_str}' does not exist",
                    'warning'
                ))
        else:
            errors.append(ValidationError(
                line_num,
                f"Chunk '{chunk_id}': content_path should only be used with type=[image,video,audio]",
                'warning'
            ))

    return errors


def validate_world_model_fields(
    definition: dict,
    def_id: str,
    line_num: int,
    doc_entity_types: dict[str, str],
    context: str = 'Chunk',
) -> list[ValidationError]:
    """Validate v2.0 world model fields on entities or chunks."""
    errors = []

    # Validate string array fields
    for field in ('preconditions', 'postconditions', 'related_skills', 'state_refs'):
        if field in definition:
            if not isinstance(definition[field], list):
                errors.append(ValidationError(
                    line_num,
                    f"{context} '{def_id}': '{field}' must be a list of strings",
                    'error'
                ))
            else:
                for item in definition[field]:
                    if not isinstance(item, str):
                        errors.append(ValidationError(
                            line_num,
                            f"{context} '{def_id}': '{field}' items must be strings, got {type(item).__name__}",
                            'error'
                        ))

    # Ensure state_refs, preconditions, postconditions reference state-type entities
    for state_field in ('state_refs', 'preconditions', 'postconditions'):
        if state_field in definition and isinstance(definition[state_field], list):
            for ref in definition[state_field]:
                if not isinstance(ref, str):
                    continue
                # For preconditions, ignore "NOT " prefix for checking existence
                ref_id = ref[4:].strip() if ref.startswith("NOT ") else ref
                
                if ref_id not in doc_entity_types:
                    errors.append(ValidationError(
                        line_num,
                        f"{context} '{def_id}': {state_field} '{ref_id}' not found in document entities",
                        'error'
                    ))
                elif doc_entity_types[ref_id] != 'state':
                    errors.append(ValidationError(
                        line_num,
                        f"{context} '{def_id}': {state_field} '{ref_id}' must point to an entity of type 'state' (got '{doc_entity_types[ref_id]}')",
                        'error'
                    ))

    # Validate cost enum
    if 'cost' in definition:
        if definition['cost'] not in ('low', 'medium', 'high'):
            errors.append(ValidationError(
                line_num,
                f"{context} '{def_id}': 'cost' must be one of ['low', 'medium', 'high']",
                'error'
            ))

    # Validate idempotent bool
    if 'idempotent' in definition:
        if not isinstance(definition['idempotent'], bool):
            errors.append(ValidationError(
                line_num,
                f"{context} '{def_id}': 'idempotent' must be a boolean",
                'error'
            ))

    return errors


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
    doc_dir = filepath.parent

    # Parse frontmatter
    frontmatter, body_content, fm_end_line = parse_frontmatter(content)

    # Get chunk definitions from frontmatter
    fm_chunks = {}
    all_chunk_ids = set()

    doc_entity_types: dict[str, str] = {}
    seen_entities: set[str] = set()
    if frontmatter and 'entities' in frontmatter:
        # First pass: collect all entity types
        if isinstance(frontmatter['entities'], list):
            for entity_def in frontmatter['entities']:
                if isinstance(entity_def, dict) and 'id' in entity_def and 'type' in entity_def:
                    doc_entity_types[entity_def['id']] = entity_def['type']
        if not isinstance(frontmatter['entities'], list):
            errors.append(ValidationError(
                2,
                "'entities' must be a list",
                'error'
            ))
        else:
            for i, entity_def in enumerate(frontmatter['entities']):
                line_idx = i + 2  # Approximate
                if not isinstance(entity_def, dict):
                    errors.append(ValidationError(line_idx, f"Entity {i+1} must be an object", 'error'))
                    continue
                
                if 'id' not in entity_def or 'name' not in entity_def or 'type' not in entity_def:
                    errors.append(ValidationError(
                        line_idx,
                        f"Entity definition {i+1} missing required field ('id', 'name', 'type')",
                        'error'
                    ))
                    continue
                
                ent_id = entity_def['id']
                if ent_id in seen_entities:
                    errors.append(ValidationError(
                        line_idx,
                        f"Duplicate entity ID '{ent_id}' in frontmatter",
                        'error'
                    ))
                else:
                    seen_entities.add(ent_id)

                # Validate entity type against known types
                ent_type = entity_def.get('type', '')
                if ent_type and ent_type not in VALID_ENTITY_TYPES:
                    errors.append(ValidationError(
                        line_idx,
                        f"Entity '{ent_id}': unknown type '{ent_type}', expected one of {sorted(VALID_ENTITY_TYPES)}",
                        'warning'
                    ))

                # Validate v2.0 world model fields on entities
                errors.extend(validate_world_model_fields(
                    entity_def, ent_id, line_idx, doc_entity_types, context='Entity'
                ))

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
            all_chunk_ids.add(chunk_id)
            line_num = i + 2

            if chunk_id in fm_chunks:
                errors.append(ValidationError(
                    line_num,
                    f"Duplicate chunk ID '{chunk_id}' in frontmatter",
                    'error'
                ))
            else:
                fm_chunks[chunk_id] = chunk_def

            # Warn if no context
            if 'context' not in chunk_def:
                errors.append(ValidationError(
                    line_num,
                    f"Chunk '{chunk_id}' missing 'context' field",
                    'warning'
                ))

            # Validate chunk entities
            if 'entities' in chunk_def:
                if not isinstance(chunk_def['entities'], list):
                    errors.append(ValidationError(
                        line_num,
                        f"Chunk '{chunk_id}': 'entities' must be a list of entity IDs",
                        'error'
                    ))
                else:
                    for ent_ref in chunk_def['entities']:
                        if not isinstance(ent_ref, str):
                            errors.append(ValidationError(
                                line_num,
                                f"Chunk '{chunk_id}': entity reference must be a string ID, got {type(ent_ref).__name__}",
                                'error'
                            ))
                        elif ent_ref not in doc_entity_types:
                            errors.append(ValidationError(
                                line_num,
                                f"Chunk '{chunk_id}': entity reference '{ent_ref}' not found in document entities",
                                'error'
                            ))

            # Validate 2026 RAG extension fields
            errors.extend(validate_temporal_fields(chunk_def, chunk_id, line_num))
            errors.extend(validate_agentic_fields(chunk_def, chunk_id, line_num, all_chunk_ids))
            errors.extend(validate_multimodal_fields(chunk_def, chunk_id, line_num, doc_dir))
            # Validate v2.0 world model fields on chunks
            errors.extend(validate_world_model_fields(
                chunk_def, chunk_id, line_num, doc_entity_types, context='Chunk'
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
