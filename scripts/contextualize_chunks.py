#!/usr/bin/env python3
"""
Contextualize Chunks - Anthropic Contextual Retrieval Implementation

Generate contextual descriptions for each chunk in a CtxFST document
using Claude with prompt caching for cost efficiency.

Based on Anthropic's Contextual Retrieval method:
https://www.anthropic.com/news/contextual-retrieval

Usage:
    python contextualize_chunks.py <input.md> [--output <output.md>]
    python contextualize_chunks.py <input.md> --dry-run  # Preview without API calls

Requirements:
    pip install anthropic
    export ANTHROPIC_API_KEY="your-api-key"
"""

import argparse
import os
import re
import sys
from dataclasses import dataclass
from typing import Optional

try:
    import anthropic
except ImportError:
    print("Error: anthropic package not installed. Run: pip install anthropic")
    sys.exit(1)


# Anthropic's official prompt template for contextual retrieval
DOCUMENT_CONTEXT_PROMPT = """
<document>
{doc_content}
</document>
"""

CHUNK_CONTEXT_PROMPT = """
Here is the chunk we want to situate within the whole document
<chunk>
{chunk_content}
</chunk>
Please give a short succinct context to situate this chunk within the overall document for the purposes of improving search retrieval of the chunk. Answer only with the succinct context and nothing else.
"""

MODEL_NAME = "claude-3-haiku-20240307"


@dataclass
class Chunk:
    """Represents a chunk extracted from markdown."""
    id: str
    content: str
    start_pos: int
    end_pos: int
    context: Optional[str] = None


class ContextualRetrieval:
    """Implements Anthropic's Contextual Retrieval with prompt caching."""

    def __init__(self, api_key: Optional[str] = None):
        if api_key is None:
            api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY not set. "
                "Set it via environment variable or pass api_key parameter."
            )
        self.client = anthropic.Anthropic(api_key=api_key)
        self.token_counts = {
            "input": 0,
            "output": 0,
            "cache_read": 0,
            "cache_creation": 0
        }

    def situate_context(self, document: str, chunk_content: str) -> str:
        """
        Generate contextual description for a chunk.

        Uses Claude with prompt caching - the document is cached to reduce
        costs when processing multiple chunks from the same document.

        Args:
            document: The full document content
            chunk_content: The specific chunk to contextualize

        Returns:
            A 50-100 token contextual description
        """
        response = self.client.messages.create(
            model=MODEL_NAME,
            max_tokens=200,
            temperature=0.0,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": DOCUMENT_CONTEXT_PROMPT.format(doc_content=document),
                            "cache_control": {"type": "ephemeral"}
                        },
                        {
                            "type": "text",
                            "text": CHUNK_CONTEXT_PROMPT.format(chunk_content=chunk_content)
                        }
                    ]
                }
            ],
            extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
        )

        # Track token usage
        usage = response.usage
        self.token_counts["input"] += usage.input_tokens
        self.token_counts["output"] += usage.output_tokens
        if hasattr(usage, 'cache_read_input_tokens'):
            self.token_counts["cache_read"] += usage.cache_read_input_tokens
        if hasattr(usage, 'cache_creation_input_tokens'):
            self.token_counts["cache_creation"] += usage.cache_creation_input_tokens

        return response.content[0].text

    def print_token_stats(self):
        """Print token usage statistics."""
        print("\n" + "=" * 50)
        print("Token Usage Statistics")
        print("=" * 50)
        print(f"Input tokens: {self.token_counts['input']}")
        print(f"Output tokens: {self.token_counts['output']}")
        print(f"Cache creation tokens: {self.token_counts['cache_creation']}")
        print(f"Cache read tokens: {self.token_counts['cache_read']}")

        total = (
            self.token_counts["input"] +
            self.token_counts["cache_read"] +
            self.token_counts["cache_creation"]
        )
        if total > 0:
            savings = (self.token_counts["cache_read"] / total) * 100
            print(f"Cache savings: {savings:.1f}% of input tokens from cache")


def extract_chunks(content: str) -> list[Chunk]:
    """Extract all chunks from a CtxFST markdown document."""
    chunks = []
    pattern = re.compile(
        r'<Chunk\s+id=["\']([^"\']+)["\']>\s*(.*?)\s*</Chunk>',
        re.DOTALL | re.IGNORECASE
    )

    for match in pattern.finditer(content):
        chunks.append(Chunk(
            id=match.group(1),
            content=match.group(2).strip(),
            start_pos=match.start(),
            end_pos=match.end()
        ))

    return chunks


def insert_context_into_chunk(chunk: Chunk, context: str) -> str:
    """Format a chunk with its contextual description."""
    context_comment = f"<!-- Context: {context} -->\n\n"
    return f'<Chunk id="{chunk.id}">\n{context_comment}{chunk.content}\n</Chunk>'


def process_document(
    content: str,
    retrieval: Optional[ContextualRetrieval] = None,
    dry_run: bool = False
) -> str:
    """
    Process a CtxFST document and add contextual descriptions to each chunk.

    Args:
        content: The full markdown document
        retrieval: ContextualRetrieval instance (optional if dry_run)
        dry_run: If True, show what would be done without API calls

    Returns:
        The document with contextualized chunks
    """
    chunks = extract_chunks(content)

    if not chunks:
        print("No chunks found in document.")
        return content

    print(f"Found {len(chunks)} chunks to process.")

    # Process chunks in reverse order to preserve positions
    result = content
    for i, chunk in enumerate(reversed(chunks), 1):
        actual_index = len(chunks) - i + 1
        print(f"Processing chunk {actual_index}/{len(chunks)}: {chunk.id}")

        if dry_run:
            context = f"[DRY RUN] Context would be generated for: {chunk.id}"
        else:
            if retrieval is None:
                raise ValueError("retrieval instance required when not in dry_run mode")
            context = retrieval.situate_context(content, chunk.content)

        chunk.context = context
        new_chunk_text = insert_context_into_chunk(chunk, context)
        result = result[:chunk.start_pos] + new_chunk_text + result[chunk.end_pos:]

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Add contextual descriptions to CtxFST chunks using Anthropic's method"
    )
    parser.add_argument("input", help="Input markdown file with <Chunk> tags")
    parser.add_argument(
        "--output", "-o",
        help="Output file (default: input with .contextualized.md suffix)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be done without making API calls"
    )
    parser.add_argument(
        "--api-key",
        help="Anthropic API key (or set ANTHROPIC_API_KEY env var)"
    )

    args = parser.parse_args()

    # Read input file
    try:
        with open(args.input, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"Error: File not found: {args.input}")
        sys.exit(1)

    # Determine output path
    if args.output:
        output_path = args.output
    else:
        base, ext = os.path.splitext(args.input)
        output_path = f"{base}.contextualized{ext}"

    # Initialize retrieval (skip if dry run)
    retrieval = None
    if not args.dry_run:
        try:
            retrieval = ContextualRetrieval(api_key=args.api_key)
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)

    # Process document
    print(f"Processing: {args.input}")
    if args.dry_run:
        print("(DRY RUN - no API calls will be made)")

    result = process_document(content, retrieval, args.dry_run)

    # Write output
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(result)

    print(f"\nOutput written to: {output_path}")

    # Print stats if not dry run
    if retrieval:
        retrieval.print_token_stats()


if __name__ == "__main__":
    main()
