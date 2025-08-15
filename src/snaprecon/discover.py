"""Subdomain discovery and target resolution."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import List, Optional

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


def resolve_targets(
    config: AppConfig,
    domain: Optional[str] = None,
    input_file: Optional[str] = None
) -> List[Target]:
    """Resolve targets from domain or input file."""
    targets = []
    
    if domain:
        # Single domain discovery
        subdomains = asyncio.run(run_subfinder(domain, config))
        for subdomain in subdomains:
            target = Target(
                host=subdomain,
                domain=domain,
                subdomain=subdomain.replace(f".{domain}", "") if subdomain != domain else None
            )
            targets.append(target)
    
    elif input_file:
        # Read from file
        file_path = Path(input_file)
        hosts = read_targets_file(file_path)
        
        for host in hosts:
            # Extract domain from host
            parts = host.split(".")
            if len(parts) >= 2:
                domain_part = ".".join(parts[-2:])
                subdomain_part = ".".join(parts[:-2]) if len(parts) > 2 else None
                
                target = Target(
                    host=host,
                    domain=domain_part,
                    subdomain=subdomain_part
                )
                targets.append(target)
    
    if not targets:
        raise DiscoveryError(
            "No targets found. Provide either --domain or --input-file",
            code="NO_TARGETS"
        )
    
    return targets
