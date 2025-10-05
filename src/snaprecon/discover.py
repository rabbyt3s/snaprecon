"""Subdomain discovery and target resolution."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Iterable, List, Optional, Set, Tuple
from urllib.parse import urlparse

from .errors import DiscoveryError
from .models import Target
from .config import AppConfig


async def run_subfinder(domain: str, config: AppConfig) -> List[str]:
    """Run subfinder to discover subdomains."""
    try:
        cmd = [
            config.subfinder_bin,
            "-d", domain,
            "-silent"
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=300  # 5 minutes max
        )
        
        if process.returncode != 0:
            raise DiscoveryError(
                f"Subfinder failed with return code {process.returncode}",
                code="SUBFINDER_ERROR",
                details={"stderr": stderr.decode()}
            )
        
        subdomains = stdout.decode().strip().split("\n")
        return [s for s in subdomains if s and "." in s]
        
    except asyncio.TimeoutError:
        raise DiscoveryError(
            "Subfinder timed out after 5 minutes",
            code="SUBFINDER_TIMEOUT"
        )
    except FileNotFoundError:
        raise DiscoveryError(
            f"Subfinder binary not found: {config.subfinder_bin}",
            code="SUBFINDER_NOT_FOUND"
        )


def read_targets_file(file_path: Path) -> List[str]:
    """Read targets from a file (one per line)."""
    try:
        with open(file_path, "r") as f:
            lines = f.readlines()
        return [line.strip() for line in lines if line.strip() and "." in line]
    except FileNotFoundError:
        raise DiscoveryError(
            f"Targets file not found: {file_path}",
            code="FILE_NOT_FOUND"
        )
    except Exception as e:
        raise DiscoveryError(
            f"Error reading targets file: {e}",
            code="FILE_READ_ERROR"
        )


def _target_from_host(host: str) -> Target:
    """Normalize a host string into a Target."""
    host_clean = (host or "").strip().lower()
    if not host_clean or "." not in host_clean:
        raise DiscoveryError(
            f"Invalid host entry: {host!r}",
            code="INVALID_HOST",
        )

    parts = host_clean.split(".")
    if len(parts) < 2:
        raise DiscoveryError(
            f"Host must contain at least one dot: {host}",
            code="INVALID_HOST",
        )

    domain_part = ".".join(parts[-2:])
    subdomain_part = ".".join(parts[:-2]) if len(parts) > 2 else None

    return Target(host=host_clean, domain=domain_part, subdomain=subdomain_part)


def resolve_targets_from_hosts(hosts: Iterable[str]) -> List[Target]:
    """Create Target objects from an iterable of host strings."""
    seen: Set[str] = set()
    targets: List[Target] = []

    for host in hosts:
        if not host:
            continue
        target = _target_from_host(host)
        if target.host in seen:
            continue
        seen.add(target.host)
        targets.append(target)

    if not targets:
        raise DiscoveryError(
            "No valid hosts provided",
            code="NO_HOSTS",
        )

    return targets


def resolve_targets(
    config: AppConfig,
    domain: Optional[str] = None,
    input_file: Optional[str] = None
) -> List[Target]:
    """Resolve targets from domain discovery or a pre-existing host list."""
    if domain:
        subdomains = asyncio.run(run_subfinder(domain, config))
        if not subdomains:
            raise DiscoveryError(
                f"Subfinder returned no subdomains for {domain}",
                code="NO_SUBDOMAINS",
            )
        return resolve_targets_from_hosts(subdomains)

    if input_file:
        file_path = Path(input_file)
        hosts = read_targets_file(file_path)
        return resolve_targets_from_hosts(hosts)

    raise DiscoveryError(
        "No targets found. Provide either --domain or --input-file",
        code="NO_TARGETS",
    )


def _normalize_scope_entry(entry: str) -> Tuple[Optional[str], Optional[str]]:
    """Normalize a single scope entry into either a seed domain or a direct host.

    Returns a tuple (seed_domain, direct_host) where only one is non-None.
    - URLs → direct_host (their netloc)
    - Patterns like "*.example.com" or ".example.com" → seed_domain "example.com"
    - Plain domains with two labels (e.g., example.com) → seed_domain
    - Plain hosts with >=3 labels (e.g., app.example.com) → direct_host
    """
    value = entry.strip().lower()
    if not value or value.startswith("#"):
        return (None, None)

    # URLs
    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        host = parsed.netloc.split(":")[0]
        return (None, host if "." in host else None)

    # Wildcard or suffix patterns
    if value.startswith("*."):
        value = value[2:]
    elif value.startswith("."):
        value = value[1:]

    # Remove stray wildcard characters
    value_no_wild = value.replace("*", "")
    if "." not in value_no_wild:
        return (None, None)

    labels = value_no_wild.split(".")
    if len(labels) <= 1:
        return (None, None)
    if len(labels) == 2:
        # Root domain → use subfinder
        return (value_no_wild, None)
    # 3+ labels: direct host
    return (None, value_no_wild)


def resolve_targets_from_scope(config: AppConfig, scope_file: str) -> List[Target]:
    """Resolve targets using entries in a scope file.

    Behavior:
    - For root domains/suffixes (e.g., example.com, *.example.org), run subfinder
    - For explicit hosts or URLs, add them directly as targets
    - Duplicates are removed
    """
    scope_path = Path(scope_file)
    if not scope_path.exists():
        raise DiscoveryError(f"Scope file not found: {scope_file}", code="SCOPE_FILE_NOT_FOUND")

    try:
        raw_lines = scope_path.read_text().splitlines()
    except Exception as e:
        raise DiscoveryError(f"Error reading scope file: {e}", code="SCOPE_FILE_READ_ERROR")

    seed_domains: Set[str] = set()
    direct_hosts: Set[str] = set()
    for line in raw_lines:
        seed, host = _normalize_scope_entry(line)
        if seed:
            seed_domains.add(seed)
        if host:
            direct_hosts.add(host)

    # Discover subdomains for seed domains
    discovered_hosts: Set[str] = set(direct_hosts)
    if seed_domains:
        async def _gather_all() -> List[List[str]]:
            tasks = [run_subfinder(d, config) for d in sorted(seed_domains)]
            return await asyncio.gather(*tasks)

        try:
            results_lists = asyncio.run(_gather_all())
        except Exception as e:
            raise DiscoveryError(f"Error during subdomain discovery: {e}", code="DISCOVERY_ERROR")
        for idx, domain in enumerate(sorted(seed_domains)):
            for sub in results_lists[idx]:
                if sub and "." in sub:
                    discovered_hosts.add(sub.lower())

    # Build Target objects
    targets: List[Target] = []
    for host in sorted(discovered_hosts):
        parts = host.split(".")
        if len(parts) >= 2:
            domain_part = ".".join(parts[-2:])
            subdomain_part = ".".join(parts[:-2]) if len(parts) > 2 else None
            targets.append(Target(host=host, domain=domain_part, subdomain=subdomain_part))

    if not targets:
        raise DiscoveryError(
            "No targets found from scope file. Provide --domain or a valid --input-file, or add resolvable entries to the scope file",
            code="NO_TARGETS_FROM_SCOPE",
        )

    return targets
