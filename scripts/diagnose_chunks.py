#!/usr/bin/env python3
"""
Diagnose Chunk Quality in CtxFST Documents

Analyze chunk quality before RAG ingestion with 3 intervention levels:
- diagnose: List problems with explanations
- suggest: Include concrete modification suggestions
- fix: Output patched frontmatter for review

Usage:
    python diagnose_chunks.py <file.md> --level diagnose
    python diagnose_chunks.py <file.md> --level suggest
    python diagnose_chunks.py <file.md> --level fix
    python diagnose_chunks.py <file.md> --json  # JSON output for LLM processing
"""

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("Error: PyYAML required. Install with: pip install pyyaml")
    sys.exit(1)


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class Issue:
    """A single diagnostic issue."""
    category: str  # semantic_similarity, context_quality, tag_overlap, id_naming
    severity: str  # error, warning, info
    chunk_ids: list[str]
    message: str
    suggestion: str = ""
    fix: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChunkData:
    """Parsed chunk with metadata and content."""
    id: str
    context: str
    content: str
    tags: list[str]
    raw_def: dict[str, Any]


@dataclass
class DiagnosticReport:
    """Complete diagnostic result."""
    filepath: str
    issues: list[Issue]
    stats: dict[str, Any]


# ============================================================================
# Parsing
# ============================================================================

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
        return yaml.safe_load(frontmatter_text), remaining
    except yaml.YAMLError:
        return None, content


def extract_chunks(content: str) -> dict[str, str]:
    """Extract chunk ID -> content mapping from document body."""
    pattern = re.compile(
        r'<Chunk\s+id=["\']([^"\']+)["\']\s*>(.*?)</Chunk>',
        re.DOTALL | re.IGNORECASE
    )
    return {m.group(1): m.group(2).strip() for m in pattern.finditer(content)}


def load_document(filepath: Path) -> tuple[list[ChunkData], dict]:
    """Load and parse a CtxFST document."""
    content = filepath.read_text(encoding='utf-8')
    frontmatter, body = parse_frontmatter(content)

    if not frontmatter or 'chunks' not in frontmatter:
        return [], {}

    body_chunks = extract_chunks(body)
    chunks = []

    for chunk_def in frontmatter['chunks']:
        chunk_id = chunk_def.get('id', '')
        if not chunk_id:
            continue

        chunks.append(ChunkData(
            id=chunk_id,
            context=chunk_def.get('context', ''),
            content=body_chunks.get(chunk_id, ''),
            tags=chunk_def.get('tags', []),
            raw_def=chunk_def
        ))

    return chunks, frontmatter


# ============================================================================
# Analysis Functions
# ============================================================================

def tokenize(text: str) -> list[str]:
    """Simple word tokenization for analysis."""
    return re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())


def jaccard_similarity(set1: set, set2: set) -> float:
    """Calculate Jaccard similarity between two sets."""
    if not set1 or not set2:
        return 0.0
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union if union > 0 else 0.0


def check_semantic_similarity(chunks: list[ChunkData]) -> list[Issue]:
    """
    Detect chunk pairs with high semantic overlap.

    Uses keyword overlap in context + content as a proxy for embedding similarity.
    """
    issues = []
    SIMILARITY_THRESHOLD = 0.6

    for i, chunk_a in enumerate(chunks):
        tokens_a = set(tokenize(chunk_a.context + ' ' + chunk_a.content))

        for chunk_b in chunks[i + 1:]:
            tokens_b = set(tokenize(chunk_b.context + ' ' + chunk_b.content))
            similarity = jaccard_similarity(tokens_a, tokens_b)

            if similarity >= SIMILARITY_THRESHOLD:
                shared_words = sorted(tokens_a & tokens_b)[:10]
                issues.append(Issue(
                    category='semantic_similarity',
                    severity='warning',
                    chunk_ids=[chunk_a.id, chunk_b.id],
                    message=(
                        f"Chunks may confuse retrieval (similarity: {similarity:.0%}). "
                        f"Shared keywords: {', '.join(shared_words)}"
                    ),
                    suggestion=(
                        f"Differentiate contexts: emphasize what makes '{chunk_a.id}' "
                        f"unique vs '{chunk_b.id}'. Consider different use cases or examples."
                    )
                ))

    return issues


def check_context_quality(chunks: list[ChunkData]) -> list[Issue]:
    """
    Check context field quality.

    - Length: should be 50-100 tokens (roughly 40-80 words)
    - Specificity: should not just repeat content opener
    """
    issues = []
    MIN_WORDS = 8
    MAX_WORDS = 50
    OPTIMAL_MIN = 12
    OPTIMAL_MAX = 30

    for chunk in chunks:
        context_words = chunk.context.split()
        word_count = len(context_words)

        # Empty or missing context
        if word_count == 0:
            issues.append(Issue(
                category='context_quality',
                severity='error',
                chunk_ids=[chunk.id],
                message="Context is empty",
                suggestion=(
                    f"Add a 15-25 word description that explains what this chunk covers "
                    f"and how it differs from other chunks."
                ),
                fix={'context': f"[TODO: Describe the purpose and unique aspects of {chunk.id}]"}
            ))
            continue

        # Too short
        if word_count < MIN_WORDS:
            issues.append(Issue(
                category='context_quality',
                severity='warning',
                chunk_ids=[chunk.id],
                message=f"Context too short ({word_count} words, recommend {OPTIMAL_MIN}-{OPTIMAL_MAX})",
                suggestion=(
                    "Expand context with: what topic this covers, who would search for it, "
                    "and what makes it distinct from similar chunks."
                )
            ))

        # Too long
        if word_count > MAX_WORDS:
            issues.append(Issue(
                category='context_quality',
                severity='info',
                chunk_ids=[chunk.id],
                message=f"Context may be too verbose ({word_count} words, recommend {OPTIMAL_MIN}-{OPTIMAL_MAX})",
                suggestion="Consider condensing to key differentiating information only."
            ))

        # Check if context just repeats content opener
        if chunk.content:
            content_opener = ' '.join(chunk.content.split()[:15]).lower()
            context_lower = chunk.context.lower()

            # Simple overlap check
            context_tokens = set(tokenize(context_lower))
            content_tokens = set(tokenize(content_opener))

            if context_tokens and content_tokens:
                overlap = jaccard_similarity(context_tokens, content_tokens)
                if overlap > 0.7:
                    issues.append(Issue(
                        category='context_quality',
                        severity='warning',
                        chunk_ids=[chunk.id],
                        message="Context appears to just repeat the content opening",
                        suggestion=(
                            "Rewrite context to explain the chunk's role in the document "
                            "rather than summarizing its content."
                        )
                    ))

    return issues


def check_tag_overlap(chunks: list[ChunkData]) -> list[Issue]:
    """
    Detect tag consistency issues.

    - High overlap: if most chunks share the same tags, filtering is useless
    - Missing coverage: common tags that some chunks lack
    """
    issues = []

    if len(chunks) < 2:
        return issues

    # Count tag frequencies
    all_tags: Counter = Counter()
    chunk_tag_sets = {}

    for chunk in chunks:
        tags = set(chunk.tags)
        chunk_tag_sets[chunk.id] = tags
        all_tags.update(tags)

    # Find tags that appear in >80% of chunks (too common to be useful)
    threshold = len(chunks) * 0.8
    ubiquitous_tags = [tag for tag, count in all_tags.items() if count >= threshold]

    if ubiquitous_tags and len(ubiquitous_tags) > 1:
        issues.append(Issue(
            category='tag_overlap',
            severity='info',
            chunk_ids=[c.id for c in chunks],
            message=(
                f"Tags appear in most chunks, reducing filtering effectiveness: "
                f"{', '.join(ubiquitous_tags)}"
            ),
            suggestion=(
                "Consider using more specific sub-tags or adding differentiating tags "
                "to enable precise filtering."
            )
        ))

    # Check for chunks with identical tag sets
    tag_set_to_chunks: dict[frozenset, list[str]] = {}
    for chunk_id, tags in chunk_tag_sets.items():
        frozen = frozenset(tags)
        tag_set_to_chunks.setdefault(frozen, []).append(chunk_id)

    for tag_set, chunk_ids in tag_set_to_chunks.items():
        if len(chunk_ids) > 1 and tag_set:  # Multiple chunks, non-empty tags
            issues.append(Issue(
                category='tag_overlap',
                severity='warning',
                chunk_ids=chunk_ids,
                message=f"Identical tags: {sorted(tag_set)}",
                suggestion=(
                    "Add differentiating tags to each chunk based on their specific focus "
                    "(e.g., level:beginner vs level:advanced, or use:api vs use:cli)."
                )
            ))

    return issues


def check_id_naming(chunks: list[ChunkData]) -> list[Issue]:
    """
    Check ID naming consistency.

    - Format: category:topic-name
    - Consistent category usage
    """
    issues = []
    ID_PATTERN = re.compile(r'^[a-z]+:[a-z0-9-]+$')

    categories: Counter = Counter()

    for chunk in chunks:
        # Check format
        if not ID_PATTERN.match(chunk.id):
            issues.append(Issue(
                category='id_naming',
                severity='warning',
                chunk_ids=[chunk.id],
                message=f"ID format should be 'category:topic-name' (lowercase, kebab-case)",
                suggestion=f"Rename to follow pattern, e.g., 'skill:python-async'"
            ))
        else:
            # Extract category
            category = chunk.id.split(':')[0]
            categories[category] += 1

    # Check for single-use categories (may indicate inconsistency)
    if len(categories) > 1:
        singletons = [cat for cat, count in categories.items() if count == 1]
        if singletons and len(singletons) < len(categories):
            issues.append(Issue(
                category='id_naming',
                severity='info',
                chunk_ids=[c.id for c in chunks if c.id.split(':')[0] in singletons],
                message=f"Uncommon category prefixes: {', '.join(singletons)}",
                suggestion=(
                    "Consider grouping related chunks under the same category prefix "
                    "for better organization."
                )
            ))

    return issues


# ============================================================================
# Report Generation
# ============================================================================

def generate_fixes(issues: list[Issue], chunks: list[ChunkData]) -> dict[str, dict]:
    """Generate suggested frontmatter fixes for each chunk."""
    fixes: dict[str, dict] = {}

    for chunk in chunks:
        chunk_issues = [i for i in issues if chunk.id in i.chunk_ids and i.fix]
        if chunk_issues:
            fixes[chunk.id] = {}
            for issue in chunk_issues:
                fixes[chunk.id].update(issue.fix)

    return fixes


def run_diagnostics(filepath: Path) -> DiagnosticReport:
    """Run all diagnostic checks on a document."""
    chunks, frontmatter = load_document(filepath)

    if not chunks:
        return DiagnosticReport(
            filepath=str(filepath),
            issues=[Issue(
                category='structure',
                severity='error',
                chunk_ids=[],
                message="No valid chunks found in document"
            )],
            stats={
                'chunk_count': 0,
                'avg_context_words': 0,
                'unique_tags': 0,
                'categories': [],
                'issues_by_severity': {'error': 1, 'warning': 0, 'info': 0}
            }
        )

    # Run all checks
    issues = []
    issues.extend(check_semantic_similarity(chunks))
    issues.extend(check_context_quality(chunks))
    issues.extend(check_tag_overlap(chunks))
    issues.extend(check_id_naming(chunks))

    # Calculate stats
    stats = {
        'chunk_count': len(chunks),
        'avg_context_words': sum(len(c.context.split()) for c in chunks) / len(chunks),
        'unique_tags': len(set(t for c in chunks for t in c.tags)),
        'categories': list(set(c.id.split(':')[0] for c in chunks if ':' in c.id)),
        'issues_by_severity': {
            'error': len([i for i in issues if i.severity == 'error']),
            'warning': len([i for i in issues if i.severity == 'warning']),
            'info': len([i for i in issues if i.severity == 'info'])
        }
    }

    return DiagnosticReport(filepath=str(filepath), issues=issues, stats=stats)


# ============================================================================
# Output Formatting
# ============================================================================

def format_text_report(report: DiagnosticReport, level: str) -> str:
    """Format report as human-readable text."""
    lines = []
    lines.append(f"\n📄 {report.filepath}")
    lines.append(f"   Chunks: {report.stats['chunk_count']} | "
                 f"Tags: {report.stats['unique_tags']} | "
                 f"Categories: {', '.join(report.stats['categories'])}")
    lines.append("")

    if not report.issues:
        lines.append("✅ No issues found!")
        return '\n'.join(lines)

    # Group by category
    by_category: dict[str, list[Issue]] = {}
    for issue in report.issues:
        by_category.setdefault(issue.category, []).append(issue)

    category_names = {
        'semantic_similarity': '🔄 Semantic Similarity',
        'context_quality': '📝 Context Quality',
        'tag_overlap': '🏷️  Tag Overlap',
        'id_naming': '🆔 ID Naming',
        'structure': '📦 Structure'
    }

    for category, issues in by_category.items():
        lines.append(f"\n{category_names.get(category, category)}")
        lines.append("-" * 40)

        for issue in issues:
            icon = {'error': '❌', 'warning': '⚠️', 'info': 'ℹ️'}.get(issue.severity, '•')
            chunks_str = ', '.join(issue.chunk_ids) if issue.chunk_ids else 'document'
            lines.append(f"  {icon} [{chunks_str}]")
            lines.append(f"     {issue.message}")

            if level in ('suggest', 'fix') and issue.suggestion:
                lines.append(f"     💡 {issue.suggestion}")

            if level == 'fix' and issue.fix:
                lines.append(f"     🔧 Fix: {json.dumps(issue.fix)}")

            lines.append("")

    # Summary
    s = report.stats['issues_by_severity']
    lines.append("=" * 50)
    lines.append(f"Summary: {s['error']} error(s), {s['warning']} warning(s), {s['info']} info")

    return '\n'.join(lines)


def format_json_report(report: DiagnosticReport, level: str) -> str:
    """Format report as JSON for LLM processing."""
    output = {
        'filepath': report.filepath,
        'stats': report.stats,
        'issues': []
    }

    for issue in report.issues:
        issue_dict = {
            'category': issue.category,
            'severity': issue.severity,
            'chunk_ids': issue.chunk_ids,
            'message': issue.message
        }

        if level in ('suggest', 'fix'):
            issue_dict['suggestion'] = issue.suggestion

        if level == 'fix' and issue.fix:
            issue_dict['fix'] = issue.fix

        output['issues'].append(issue_dict)

    return json.dumps(output, indent=2, ensure_ascii=False)


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Diagnose chunk quality in CtxFST documents'
    )
    parser.add_argument('input', help='Input file or directory')
    parser.add_argument(
        '--level', '-l',
        choices=['diagnose', 'suggest', 'fix'],
        default='diagnose',
        help='Intervention level (default: diagnose)'
    )
    parser.add_argument(
        '--json', '-j',
        action='store_true',
        help='Output as JSON for LLM processing'
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

    all_reports = []
    for filepath in files:
        report = run_diagnostics(filepath)
        all_reports.append(report)

        if not args.json:
            print(format_text_report(report, args.level))

    if args.json:
        if len(all_reports) == 1:
            print(format_json_report(all_reports[0], args.level))
        else:
            combined = [json.loads(format_json_report(r, args.level)) for r in all_reports]
            print(json.dumps(combined, indent=2, ensure_ascii=False))

    # Exit code based on errors
    total_errors = sum(r.stats.get('issues_by_severity', {}).get('error', 0) for r in all_reports)
    sys.exit(1 if total_errors > 0 else 0)


if __name__ == "__main__":
    main()
