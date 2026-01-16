"""
Codebase Context Provider

Provides codebase-aware context for story enrichment using Agent SDK.
Manages local repository syncing and agentic exploration.

Reference: docs/architecture/dual-format-story-architecture.md
"""

import glob
import logging
import re
import shlex
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

from .codebase_security import (
    APPROVED_REPOS,
    REPO_BASE_PATH,
    filter_exploration_results,
    get_repo_path,
    redact_secrets,
    validate_path,
    validate_repo_name,
)

logger = logging.getLogger(__name__)


# Configuration constants
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB - skip files larger than this

# Characters not allowed in glob patterns (prevent injection)
UNSAFE_GLOB_CHARS = frozenset(['[', ']', '!', '?', '{', '}', '`', '$', '|', ';', '&', '\n', '\r'])


# Data classes for type safety

@dataclass
class SyncResult:
    """Result of a repository sync operation."""

    repo_name: str
    success: bool
    fetch_duration_ms: int = 0
    pull_duration_ms: int = 0
    error: Optional[str] = None
    synced_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class FileReference:
    """Reference to a file location in the codebase."""

    path: str
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    relevance: str = ""


@dataclass
class CodeSnippet:
    """Code snippet extracted from exploration."""

    file_path: str
    line_start: int
    line_end: int
    content: str
    language: str = "python"
    context: str = ""


@dataclass
class ExplorationResult:
    """Result of agentic codebase exploration."""

    relevant_files: List[FileReference] = field(default_factory=list)
    code_snippets: List[CodeSnippet] = field(default_factory=list)
    investigation_queries: List[str] = field(default_factory=list)
    exploration_duration_ms: int = 0
    success: bool = True
    error: Optional[str] = None


@dataclass
class StaticContext:
    """Static codebase map context (fallback)."""

    component: str
    tables: List[str] = field(default_factory=list)
    api_patterns: List[str] = field(default_factory=list)
    source: str = "codebase_map"


class CodebaseContextProvider:
    """
    Provides codebase-aware context for story enrichment.

    This service manages:
    1. Background syncing of approved local repositories (every 6 hours)
    2. Agentic exploration using Agent SDK tools (Glob, Grep, Read)
    3. Static context fallback from codebase map
    4. Security validation and secrets redaction

    Architecture:
    - Primary: Agent SDK for dynamic codebase exploration
    - Fallback: Static codebase map for stable references
    - Security: Path validation, command injection prevention, secrets redaction

    Usage:
        provider = CodebaseContextProvider()

        # Ensure repo is fresh (called by background job)
        sync_result = provider.ensure_repo_fresh("aero")

        # Explore codebase for theme context
        theme_data = {"title": "Login timeout", "technical_area": "auth"}
        result = provider.explore_for_theme(theme_data, "aero")

        # Get static context as fallback
        static = provider.get_static_context("auth")
    """

    def __init__(self, repos_path: Optional[Path] = None):
        """
        Initialize the codebase context provider.

        Args:
            repos_path: Optional override for repository base path.
                       Defaults to REPO_BASE_PATH from environment.
        """
        self.repos_path = repos_path or REPO_BASE_PATH
        logger.info(f"CodebaseContextProvider initialized with repos_path: {self.repos_path}")

        # Validate that repos path exists
        if not self.repos_path.exists():
            logger.warning(f"Repos path does not exist: {self.repos_path}")

    def ensure_repo_fresh(self, repo_name: str) -> SyncResult:
        """
        Ensure a repository is up-to-date via git fetch/pull.

        This method will be called by a background job every 6 hours to keep
        local repositories synchronized with their remotes.

        Security:
        - Validates repo_name against APPROVED_REPOS allowlist (via get_repo_path)
        - Uses subprocess with shell=False to prevent command injection
        - Validates paths to prevent traversal attacks
        - Times out operations after 30 seconds

        Args:
            repo_name: Name of the repository (must be in APPROVED_REPOS)

        Returns:
            SyncResult with timing metrics and success status

        Raises:
            ValueError: If repo_name is not in APPROVED_REPOS

        TODO: Implement git fetch/pull logic with:
        - subprocess.run() with shell=False
        - Timeout handling (30s default)
        - Timing metrics (fetch_duration_ms, pull_duration_ms)
        - Error capture and logging
        - Use validate_git_command_args() from codebase_security
        """
        # Validates repo_name and raises ValueError if unauthorized
        repo_path = get_repo_path(repo_name)

        logger.info(f"Syncing repository: {repo_name} at {repo_path}")

        # TODO: Implement git fetch/pull
        # Example implementation outline:
        # 1. Run git fetch with timing using subprocess.run(["git", ...], shell=False, timeout=30)
        # 2. Run git pull with timing
        # 3. Use validate_git_command_args() before running commands
        # 4. Return SyncResult with metrics

        raise NotImplementedError(
            "Git sync implementation pending. Will use subprocess.run() with shell=False."
        )

    def explore_for_theme(
        self,
        theme_data: Dict,
        target_repo: str
    ) -> ExplorationResult:
        """
        Explore codebase using local file operations to find relevant context for a theme.

        This is the primary mechanism for enriching stories with codebase context.
        Uses local file search (glob, grep) to explore the codebase and extract
        relevant files, code snippets, and patterns.

        The exploration is guided by theme metadata:
        - product_area: Product context (e.g., 'scheduling')
        - component: Technical component (e.g., 'csv_import')
        - user_intent: What user is trying to do
        - symptoms: List of error messages or symptoms

        Security:
        - Validates target_repo against APPROVED_REPOS (via get_repo_path)
        - Applies secrets redaction to all extracted content (redact_secrets)
        - Filters out sensitive files (filter_exploration_results)
        - Validates all paths before reading (validate_path)

        Args:
            theme_data: Dictionary containing theme metadata (product_area, component, etc.)
            target_repo: Repository name to explore (must be in APPROVED_REPOS)

        Returns:
            ExplorationResult containing:
            - relevant_files: List of file references with line numbers
            - code_snippets: Extracted code with context
            - investigation_queries: Queries used for exploration
            - exploration_duration_ms: Total time taken

        Raises:
            ValueError: If target_repo is not in APPROVED_REPOS
        """
        start_time = time.time()

        # Validates target_repo and raises ValueError if unauthorized
        repo_path = get_repo_path(target_repo)

        logger.info(
            f"Exploring {target_repo} for theme",
            extra={
                "repo": target_repo,
                "product_area": theme_data.get("product_area"),
                "component": theme_data.get("component"),
            }
        )

        try:
            # Build search patterns from theme metadata
            search_patterns = self._build_search_patterns(theme_data)
            logger.debug(f"Built {len(search_patterns)} search patterns", extra={"patterns": search_patterns})

            # Find relevant files using glob patterns
            raw_files = self._find_relevant_files(repo_path, search_patterns)
            logger.debug(f"Found {len(raw_files)} files before filtering")

            # Apply security filtering
            filtered_files = filter_exploration_results(raw_files)
            logger.info(f"Filtered to {len(filtered_files)} safe files")

            # Search for keywords in content
            keywords = self._extract_keywords(theme_data)
            file_references = self._search_for_keywords(repo_path, filtered_files, keywords)

            # Extract code snippets from top matches
            code_snippets = self._extract_snippets(file_references[:10])  # Top 10 files

            # Generate investigation queries
            investigation_queries = self._generate_queries(theme_data, file_references)

            duration_ms = int((time.time() - start_time) * 1000)

            logger.info(
                f"Exploration complete",
                extra={
                    "duration_ms": duration_ms,
                    "files_found": len(file_references),
                    "snippets_extracted": len(code_snippets),
                }
            )

            return ExplorationResult(
                relevant_files=file_references,
                code_snippets=code_snippets,
                investigation_queries=investigation_queries,
                exploration_duration_ms=duration_ms,
                success=True,
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                f"Exploration failed: {e}",
                extra={"repo": target_repo, "error": str(e)},
                exc_info=True,
            )

            # Return partial results on error
            return ExplorationResult(
                relevant_files=[],
                code_snippets=[],
                investigation_queries=[],
                exploration_duration_ms=duration_ms,
                success=False,
                error=str(e),
            )

    def _sanitize_for_glob(self, value: str) -> str:
        """
        Sanitize a string for safe use in glob patterns.

        Removes or escapes characters that could be used for glob injection attacks.

        Args:
            value: Raw string from theme data

        Returns:
            Sanitized string safe for glob patterns
        """
        if not value:
            return ""

        # Remove any unsafe glob characters
        sanitized = ''.join(c for c in value if c not in UNSAFE_GLOB_CHARS)

        # Only allow alphanumeric, underscore, hyphen, and dot
        sanitized = re.sub(r'[^a-zA-Z0-9_\-.]', '_', sanitized)

        # Limit length to prevent excessively long patterns
        return sanitized[:50]

    def _build_search_patterns(self, theme_data: Dict) -> List[str]:
        """
        Generate glob patterns from theme metadata.

        Builds patterns based on product_area and component to focus
        the search on relevant parts of the codebase.

        Security: All theme data is sanitized before use in glob patterns
        to prevent glob injection attacks.

        Args:
            theme_data: Theme metadata dict

        Returns:
            List of glob patterns to search
        """
        patterns = []

        # Focus on source directories first (exclude tests/docs)
        source_dirs = ["src", "app", "lib", "core", "components", "services", "api"]
        for dir_name in source_dirs:
            patterns.extend([
                f"{dir_name}/**/*.py",
                f"{dir_name}/**/*.js", 
                f"{dir_name}/**/*.ts",
                f"{dir_name}/**/*.tsx",
            ])
        
        # Add backend/frontend specific patterns
        patterns.extend([
            "backend/**/*.py",
            "frontend/**/*.js",
            "frontend/**/*.ts",
            "frontend/**/*.tsx",
        ])

        # Add product area patterns (sanitized)
        product_area = self._sanitize_for_glob(
            theme_data.get("product_area", "").lower().replace(" ", "_")
        )
        if product_area:
            patterns.extend([
                f"**/{product_area}/**/*",
                f"**/*{product_area}*/**/*",
                f"**/*{product_area}*.*",
            ])

        # Add component patterns (sanitized)
        component = self._sanitize_for_glob(
            theme_data.get("component", "").lower().replace(" ", "_")
        )
        if component:
            patterns.extend([
                f"**/{component}/**/*",
                f"**/*{component}*/**/*",
                f"**/*{component}*.*",
            ])

        return patterns

    def _find_relevant_files(self, repo_path: Path, patterns: List[str]) -> List[str]:
        """
        Find files matching patterns using glob.

        Args:
            repo_path: Root path of repository
            patterns: List of glob patterns to match

        Returns:
            List of file paths (deduplicated)
        """
        files: Set[str] = set()

        for pattern in patterns:
            try:
                matches = glob.glob(str(repo_path / pattern), recursive=True)
                # Filter to only files (not directories)
                file_matches = [m for m in matches if Path(m).is_file()]
                files.update(file_matches)
            except Exception as e:
                logger.warning(f"Glob pattern failed: {pattern}", extra={"error": str(e)})
                continue

        return list(files)

    def _extract_keywords(self, theme_data: Dict) -> List[str]:
        """
        Extract search keywords from theme data.

        Args:
            theme_data: Theme metadata dict

        Returns:
            List of keywords to search for
        """
        keywords = []

        # Extract from component (split camelCase and snake_case)
        component = theme_data.get("component", "")
        if component:
            # Split on underscores and camelCase boundaries
            words = re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\b)', component)
            words.extend(component.split("_"))
            keywords.extend([w.lower() for w in words if len(w) > 2])

        # Extract from symptoms
        symptoms = theme_data.get("symptoms", [])
        if symptoms:
            for symptom in symptoms[:3]:  # Top 3 symptoms
                # Extract quoted strings and technical terms
                quoted = re.findall(r'"([^"]+)"', symptom)
                keywords.extend(quoted)

                # Extract error codes (e.g., E123, ERR_CODE)
                error_codes = re.findall(r'\b[A-Z_]+\d+\b|\bERR_[A-Z_]+\b', symptom)
                keywords.extend(error_codes)

        # Extract from user_intent
        user_intent = theme_data.get("user_intent", "")
        if user_intent:
            # Extract action verbs and nouns (simple heuristic)
            words = re.findall(r'\b[a-z]{4,}\b', user_intent.lower())
            keywords.extend(words[:5])  # Top 5 words

        # Deduplicate and filter
        return list(set([k for k in keywords if len(k) > 2]))

    def _search_for_keywords(
        self,
        repo_path: Path,
        files: List[str],
        keywords: List[str],
        max_results: int = 20
    ) -> List[FileReference]:
        """
        Search for keywords in file contents.

        Args:
            repo_path: Repository root path
            files: List of files to search
            keywords: Keywords to search for
            max_results: Maximum file references to return

        Returns:
            List of FileReference objects with relevance scores
        """
        file_matches = []

        for file_path in files[:100]:  # Limit to first 100 files for performance
            if not validate_path(file_path):
                continue

            try:
                # Check file size before reading (security: prevent DoS from large files)
                file_size = Path(file_path).stat().st_size
                if file_size > MAX_FILE_SIZE_BYTES:
                    logger.debug(
                        f"Skipping large file: {file_path} ({file_size} bytes > {MAX_FILE_SIZE_BYTES})"
                    )
                    continue

                # Read file content
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

                # Count keyword matches
                match_count = 0
                matched_keywords = []
                line_numbers = []

                for keyword in keywords:
                    # Case-insensitive search
                    pattern = re.compile(re.escape(keyword), re.IGNORECASE)
                    matches = list(pattern.finditer(content))

                    if matches:
                        match_count += len(matches)
                        matched_keywords.append(keyword)

                        # Get line numbers for first match
                        if matches:
                            first_match_pos = matches[0].start()
                            line_num = content[:first_match_pos].count('\n') + 1
                            line_numbers.append(line_num)

                if match_count > 0:
                    # Make path relative to repo for cleaner display
                    rel_path = str(Path(file_path).relative_to(repo_path))

                    file_matches.append({
                        'path': file_path,
                        'rel_path': rel_path,
                        'match_count': match_count,
                        'keywords': matched_keywords,
                        'line_numbers': line_numbers,
                    })

            except Exception as e:
                logger.debug(f"Could not read file {file_path}: {e}")
                continue

        # Sort by match count AND path priority
        def get_path_priority(path):
            """Higher score = higher priority"""
            path_lower = path.lower()
            if '/test' in path_lower or '/tests' in path_lower:
                return 0  # Lowest priority
            if '/docs' in path_lower or '/doc' in path_lower:
                return 1
            if '/examples' in path_lower or '/sample' in path_lower:
                return 2
            if '/src/' in path_lower or '/app/' in path_lower:
                return 10  # Highest priority
            if '/lib/' in path_lower or '/core/' in path_lower:
                return 9
            if '/api/' in path_lower or '/services/' in path_lower:
                return 8
            return 5  # Default priority
        
        # Sort by priority first, then match count
        file_matches.sort(key=lambda x: (get_path_priority(x['rel_path']), x['match_count']), reverse=True)

        # Convert to FileReference objects
        references = []
        for match in file_matches[:max_results]:
            references.append(FileReference(
                path=match['rel_path'],
                line_start=match['line_numbers'][0] if match['line_numbers'] else None,
                relevance=f"{match['match_count']} matches: {', '.join(match['keywords'][:3])}"
            ))

        return references

    def _extract_snippets(self, file_references: List[FileReference]) -> List[CodeSnippet]:
        """
        Extract code snippets from file references.

        Args:
            file_references: List of file references with line numbers

        Returns:
            List of CodeSnippet objects with redacted secrets
        """
        snippets = []

        for ref in file_references[:5]:  # Top 5 files
            try:
                # Reconstruct full path (refs have relative paths)
                # We need to find the file in repos directory
                full_path = None
                for repo in APPROVED_REPOS:
                    candidate = REPO_BASE_PATH / repo / ref.path
                    if candidate.exists():
                        full_path = candidate
                        break

                if not full_path or not validate_path(str(full_path)):
                    continue

                # Check file size before reading (security: prevent DoS from large files)
                file_size = full_path.stat().st_size
                if file_size > MAX_FILE_SIZE_BYTES:
                    logger.debug(
                        f"Skipping large file for snippet: {full_path} ({file_size} bytes)"
                    )
                    continue

                with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()

                # Extract snippet around line_start
                line_start = ref.line_start or 1
                context_lines = 10

                start_idx = max(0, line_start - context_lines - 1)
                end_idx = min(len(lines), line_start + context_lines)

                snippet_lines = lines[start_idx:end_idx]
                snippet_content = ''.join(snippet_lines)

                # Apply secrets redaction
                redacted_content = redact_secrets(snippet_content)

                # Detect language from file extension
                language = self._detect_language(ref.path)

                snippets.append(CodeSnippet(
                    file_path=ref.path,
                    line_start=start_idx + 1,
                    line_end=end_idx,
                    content=redacted_content,
                    language=language,
                    context=ref.relevance,
                ))

            except Exception as e:
                logger.debug(f"Could not extract snippet from {ref.path}: {e}")
                continue

        return snippets

    def _detect_language(self, file_path: str) -> str:
        """Detect programming language from file extension."""
        ext = Path(file_path).suffix.lower()
        language_map = {
            '.py': 'python',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.tsx': 'typescript',
            '.jsx': 'javascript',
            '.java': 'java',
            '.go': 'go',
            '.rb': 'ruby',
            '.php': 'php',
            '.sql': 'sql',
        }
        return language_map.get(ext, 'text')

    def _sanitize_sql_identifier(self, value: str) -> str:
        """
        Sanitize a value for use as SQL identifier (table/column name).

        Prevents SQL injection by allowing only alphanumeric and underscore.

        Args:
            value: Raw value from theme data

        Returns:
            Sanitized SQL identifier safe for queries
        """
        if not value:
            return ""

        # Only allow alphanumeric and underscore
        sanitized = re.sub(r'[^a-zA-Z0-9_]', '', value)

        # SQL identifiers can't start with a number
        if sanitized and sanitized[0].isdigit():
            sanitized = '_' + sanitized

        # PostgreSQL identifier length limit
        return sanitized[:63]

    def _generate_queries(self, theme_data: Dict, files: List[FileReference]) -> List[str]:
        """
        Generate investigation queries based on theme and discovered files.

        These queries are SUGGESTIONS only (not executed). However, they are
        sanitized for defense-in-depth to prevent issues if:
        - A user copies them to a shell (social engineering risk)
        - Future code executes them directly
        - They're displayed in a UI without escaping

        Args:
            theme_data: Theme metadata dict
            files: List of discovered file references

        Returns:
            List of investigation query strings (SQL, search terms, etc.)
        """
        queries = []

        # Database queries based on component
        component = theme_data.get("component", "")
        product_area = theme_data.get("product_area", "")

        if component:
            # Sanitize for SQL injection prevention
            table_name = self._sanitize_sql_identifier(component.lower().replace(" ", "_"))
            if table_name:
                queries.append(
                    f"SELECT * FROM {table_name} WHERE updated_at > NOW() - INTERVAL '7 days' LIMIT 10;"
                )

        if product_area:
            # Sanitize product area for comment (no executable code in SQL comments)
            safe_area = self._sanitize_sql_identifier(product_area)
            if safe_area:
                queries.append(
                    f"-- Search logs for {safe_area} errors in last 24h"
                )

        # File-based queries (shell-escaped)
        if files:
            keywords = self._extract_keywords(theme_data)
            if keywords:
                # Use shlex.quote for shell escaping to prevent command injection
                safe_keyword = shlex.quote(keywords[0])
                safe_path = shlex.quote(files[0].path.split('/')[0] + '/')
                queries.append(
                    f"grep -r {safe_keyword} {safe_path}"
                )

        # Symptom-based queries (shell-escaped)
        symptoms = theme_data.get("symptoms", [])
        if symptoms and symptoms[0]:
            error_match = re.search(r'"([^"]+)"', symptoms[0])
            if error_match:
                error_msg = error_match.group(1)
                # Use shlex.quote for shell escaping
                safe_error = shlex.quote(error_msg)
                queries.append(
                    f"grep -r {safe_error} src/"
                )

        return queries

    def get_static_context(self, component: str) -> StaticContext:
        """
        Get static codebase map context as fallback.

        This provides stable, curated references when Agent SDK exploration
        is unavailable or as supplementary context. Sources data from
        docs/tailwind-codebase-map.md or similar static documentation.

        Use cases:
        - Fallback when exploration fails
        - Supplement exploration with stable references
        - Quick lookups for well-known components

        Args:
            component: Component name (e.g., "auth", "billing", "messaging")

        Returns:
            StaticContext containing:
            - tables: Database tables associated with component
            - api_patterns: Common API endpoints/patterns
            - source: Always "codebase_map"

        TODO: Implement static map lookup with:
        - Load from docs/tailwind-codebase-map.md
        - Cache parsed data for performance
        - Handle missing components gracefully
        """
        logger.info(f"Getting static context for component: {component}")

        # TODO: Implement static map lookup
        # Example implementation outline:
        # 1. Load codebase map from docs/
        # 2. Parse component section
        # 3. Extract tables and API patterns
        # 4. Return StaticContext

        raise NotImplementedError(
            "Static context lookup implementation pending. "
            "Will load from docs/tailwind-codebase-map.md."
        )
