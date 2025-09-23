"""Main CLI entry point for SnapRecon."""

import asyncio
import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from .config import AppConfig
from .discover import resolve_targets, resolve_targets_from_scope
from .browser import screenshot_many
from .analysis import LocalKeywordAnalyzer
from .reporting import write_results_and_reports
from .safety import enforce_scope
from .models import Target, RunResult, SafeConfig
from .utils import setup_logging
from .port_scanner import scan_ports_for_hosts

app = typer.Typer(add_completion=False, help="SnapRecon: Authorized reconnaissance with screenshot analysis")
console = Console()


@app.command()
def run(
    domain: Optional[str] = typer.Option(None, "--domain", "-d", help="Domain to discover subdomains for"),
    input_file: Optional[str] = typer.Option(None, "--input-file", "-i", help="File containing target hosts (one per line)"),
    domains_file: Optional[str] = typer.Option(
        None,
        "--domains-file",
        help="Path to domains.txt containing targets (short for --input-file)",
        show_default=False,
    ),
    scope_file: str = typer.Option(..., "--scope-file", "-s", help="File containing allowed domains/suffixes"),
    output_dir: str = typer.Option("runs", "--output-dir", "-o", help="Output directory for results"),
    gemini_model: Optional[str] = typer.Option(None, "--model", "-m", help="Gemini model to use (overrides config.toml)"),
    max_cost: float = typer.Option(10.0, "--max-cost", help="Maximum cost in USD"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Skip LLM analysis"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
    concurrency: int = typer.Option(5, "--concurrency", "-c", help="Concurrent operations (1-20)"),
    fullpage: bool = typer.Option(False, "--fullpage", help="Take full page screenshots"),
    timeout: int = typer.Option(30000, "--timeout", help="Page timeout in milliseconds"),
    proxy: Optional[str] = typer.Option(None, "--proxy", help="Proxy URL if needed"),
    subfinder_bin: str = typer.Option("subfinder", "--subfinder-bin", help="Path to subfinder binary"),
    enable_port_scan: bool = typer.Option(False, "--enable-port-scan", help="Include an 'Open Ports' section in the HTML report"),
    port_ranges: str = typer.Option("80,443", "--port-ranges", help="Comma-separated port tokens/ranges to scan (e.g., 80,443,8080-8090)"),
    skip_availability_check: bool = typer.Option(
        False,
        "--skip-availability-check",
        help="Disable pre-scan availability checks before screenshots",
    ),
):
    """Main entry: discover → port scan → screenshot → analyze → report."""
    
    # Setup logging
    setup_logging(verbose=verbose)
    logger = logging.getLogger(__name__)
    
    try:
        # Parse port ranges
        port_ranges_list = [p.strip() for p in port_ranges.split(",") if p.strip()]
        
        # Create configuration
        config = AppConfig.from_cli(
            output_dir=Path(output_dir),
            gemini_model=gemini_model,
            max_cost_usd=max_cost,
            dry_run=dry_run,
            verbose=verbose,
            concurrency=concurrency,
            fullpage=fullpage,
            timeout_ms=timeout,
            proxy=proxy,
            subfinder_bin=subfinder_bin,
            port_scan_enabled=enable_port_scan,
            port_ranges=port_ranges_list,
            availability_check_enabled=not skip_availability_check,
        )
        
        console.print(f"[bold blue]SnapRecon[/bold blue] - Starting reconnaissance run")
        console.print(f"Output directory: [green]{config.run_dir}[/green]")
        
        if enable_port_scan:
            console.print(f"[yellow]Ports sidecar enabled[/yellow] - Ports: {port_ranges}")
        
        # Resolve targets
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Resolving targets...", total=None)
            
            if domain:
                targets = resolve_targets(config=config, domain=domain)
                progress.update(task, description=f"Discovered {len(targets)} targets from {domain}")
            elif domains_file:
                file_path = Path(domains_file)
                targets = resolve_targets(config=config, input_file=str(file_path))
                progress.update(task, description=f"Loaded {len(targets)} targets from {file_path}")
            elif input_file:
                file_path = Path(input_file)
                targets = resolve_targets(config=config, input_file=str(file_path))
                progress.update(task, description=f"Loaded {len(targets)} targets from {file_path}")
            else:
                default_domains = Path("domains.txt")
                if default_domains.exists():
                    targets = resolve_targets(config=config, input_file=str(default_domains))
                    progress.update(
                        task,
                        description=f"Loaded {len(targets)} targets from {default_domains}",
                    )
                    console.print(
                        f"[yellow]Using default domains file:[/yellow] {default_domains.resolve()}"
                    )
                else:
                    # Fallback: use scope file both as scope and as seeds/hosts list
                    targets = resolve_targets_from_scope(config=config, scope_file=scope_file)
                    progress.update(task, description=f"Resolved {len(targets)} targets from scope file seeds")
        
        # Enforce scope
        console.print(f"[yellow]Enforcing scope from:[/yellow] {scope_file}")
        targets = enforce_scope(targets, scope_file)
        console.print(f"[green]✓[/green] {len(targets)} targets in scope")
        
        # No in-pipeline port scan; sidecar runs post-report if enabled

        # Optionally filter targets by availability before screenshots
        targets_to_process = targets
        if config.availability_check_enabled:
            console.print("[yellow]Checking availability before screenshots...[/yellow]")
            from .browser import test_domain_resolution

            availability_candidates = [
                Target(host=t.host, domain=t.domain, subdomain=t.subdomain)
                for t in targets
            ]
            targets_to_process = asyncio.run(test_domain_resolution(availability_candidates, config))
            if not targets_to_process:
                console.print("[red]No targets passed availability checks. Exiting.[/red]")
                raise typer.Exit(1)
            console.print(f"[green]✓[/green] {len(targets_to_process)} targets passed availability check")

        console.print(f"[yellow]Taking screenshots...[/yellow]")
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Processing targets...", total=len(targets_to_process))

            # Take screenshots
            targets = asyncio.run(screenshot_many(targets_to_process, config))

            # Update progress
            successful = len([t for t in targets if t.metadata and t.metadata.screenshot_path])
            failed = len([t for t in targets if t.error])
            progress.update(task, description=f"Screenshots: {successful} success, {failed} failed")
        
        console.print(f"[green]✓[/green] Screenshots completed")
        
        # Analyze with local keyword analysis (if not dry run)
        if not dry_run:
            console.print(f"[yellow]Analyzing screenshots (local heuristics)...[/yellow]")
            analyzer = LocalKeywordAnalyzer(config)
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("Analyzing targets...", total=len(targets))
                
                # Analyze targets
                targets = asyncio.run(analyzer.analyze_many(targets))
                
                # Update progress
                analyzed = len([t for t in targets if t.llm_result])
                failed_analysis = len([t for t in targets if t.error and not t.metadata])
                progress.update(task, description=f"Analysis: {analyzed} success, {failed_analysis} failed")
            
            console.print(f"[green]✓[/green] Analysis completed")
        else:
            console.print(f"[yellow]Skipping LLM analysis (dry run mode)[/yellow]")
        
        # Create results
        results = RunResult(
            config=SafeConfig(
                output_dir=str(config.output_dir),
                run_dir=str(config.run_dir),
                gemini_model=config.gemini_model,
                max_cost_usd=config.max_cost_usd,
                user_agent=config.user_agent,
                proxy=config.proxy,
                timeout_ms=config.timeout_ms,
                fullpage=config.fullpage,
                subfinder_bin=config.subfinder_bin,
                concurrency=config.concurrency,
                dry_run=config.dry_run,
                verbose=config.verbose,
                availability_check_enabled=config.availability_check_enabled,
            ),
            targets=targets,
            total_cost_usd=sum(t.llm_result.cost_usd for t in targets if t.llm_result),
            success_count=len([t for t in targets if t.metadata and t.metadata.screenshot_path]),
            error_count=len([t for t in targets if t.error])
        )
        
        # Optional: compute ports map for HTML if enabled
        ports_map = None
        scanned_ports = None
        if enable_port_scan:
            unique_hosts = sorted({t.host for t in targets})
            console.print(f"[yellow]Scanning ports (sidecar)...[/yellow]")
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("Scanning ports...", total=None)
                ports_map = asyncio.run(
                    scan_ports_for_hosts(unique_hosts, config.port_ranges, max(1, config.concurrency * 10))
                )
                progress.update(task, description=f"Ports scanned for {len(ports_map)} hosts")
            from .port_scanner import parse_port_tokens
            scanned_ports = parse_port_tokens(config.port_ranges)

        # Write results and reports
        console.print(f"[yellow]Generating reports...[/yellow]")
        write_results_and_reports(results, config, ports_map=ports_map, scanned_ports=scanned_ports)
        
        console.print(f"[green]✓[/green] Reconnaissance completed successfully!")
        console.print(f"Results saved to: [green]{config.run_dir}[/green]")
        
        # Display summary
        display_summary(results)
        
    except Exception as e:
        logger.error(f"Reconnaissance failed: {e}")
        console.print(f"[red]✗[/red] Reconnaissance failed: {e}")
        raise typer.Exit(1)


def display_summary(results: RunResult):
    """Display a summary of the reconnaissance run."""
    console.print(f"\n[bold green]✓ Run completed successfully![/bold green]")
    
    summary_table = Table(title="Run Summary")
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="green")
    
    summary_table.add_row("Total Targets", str(len(results.targets)))
    summary_table.add_row("Successful Screenshots", str(results.success_count))
    summary_table.add_row("Failed Screenshots", str(results.error_count))
    
    if not results.config.dry_run:
        summary_table.add_row("Total Cost", f"${results.total_cost_usd:.4f}")
    
    summary_table.add_row("Output Directory", str(results.config.run_dir))
    
    console.print(summary_table)
    
    # No inline port scan summary; ports are reported separately when enabled
    
    # Show output files
    console.print(f"\n[bold]Output Files:[/bold]")
    console.print(f"  [green]•[/green] Results: {results.config.run_dir}/results.json")
    console.print(f"  [green]•[/green] Markdown Report: {results.config.run_dir}/report.md")
    console.print(f"  [green]•[/green] HTML Report: {results.config.run_dir}/report.html")
    console.print(f"  [green]•[/green] Screenshots: {results.config.run_dir}/screenshots/")


@app.command()
def estimate(
    domain: Optional[str] = typer.Option(None, "--domain", "-d", help="Domain to estimate costs for"),
    input_file: Optional[str] = typer.Option(None, "--input-file", "-i", help="File containing target hosts"),
    model: str = typer.Option("gemini-1.5-flash", "--model", "-m", help="Gemini model to use"),
):
    """Estimate costs for a reconnaissance run."""
    
    try:
        # Get target count
        if domain:
            # Rough estimate based on domain
            estimated_targets = 50  # Conservative estimate
            console.print(f"Estimated targets for {domain}: ~{estimated_targets}")
        elif input_file:
            with open(input_file, 'r') as f:
                estimated_targets = len([line.strip() for line in f if line.strip() and '.' in line])
            console.print(f"Targets in {input_file}: {estimated_targets}")
        else:
            console.print("[red]Error:[/red] Provide either --domain or --input-file")
            raise typer.Exit(1)
        
        # Estimate cost
        from .cost import estimate_run_cost
        estimated_cost = estimate_run_cost(estimated_targets, model)
        
        console.print(f"\n[bold]Cost Estimate:[/bold]")
        console.print(f"Model: [cyan]{model}[/cyan]")
        console.print(f"Targets: [cyan]{estimated_targets}[/cyan]")
        console.print(f"Estimated Cost: [green]${estimated_cost:.4f}[/green]")
        
        # Show pricing info
        from .cost import CostManager
        cost_mgr = CostManager(model)
        pricing = cost_mgr.PRICING[model]
        
        console.print(f"\n[bold]Pricing (per 1K tokens):[/bold]")
        console.print(f"Vision Input: [yellow]${pricing['vision_input']:.3f}[/yellow]")
        console.print(f"Text Output: [yellow]${pricing['output']:.3f}[/yellow]")
        
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)


@app.command()
def validate(
    scope_file: str = typer.Option(..., "--scope-file", "-s", help="Scope file to validate"),
):
    """Validate a scope file."""
    
    try:
        from .safety import validate_scope_file
        
        console.print(f"[yellow]Validating scope file:[/yellow] {scope_file}")
        validate_scope_file(scope_file)
        
        # Show contents
        with open(scope_file, 'r') as f:
            lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        
        console.print(f"[green]✓[/green] Scope file is valid")
        console.print(f"Contains {len(lines)} allowed domains/suffixes:")
        
        for line in lines[:10]:  # Show first 10
            console.print(f"  [cyan]•[/cyan] {line}")
        
        if len(lines) > 10:
            console.print(f"  ... and {len(lines) - 10} more")
        
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)


@app.command()
def test(
    domain: Optional[str] = typer.Option(None, "--domain", "-d", help="Domain to test with"),
    scope_file: str = typer.Option(..., "--scope-file", "-s", help="File containing allowed domains/suffixes"),
    test_count: int = typer.Option(10, "--test-count", "-n", help="Number of subdomains to test (default: 10)"),
    output_dir: str = typer.Option("test-runs", "--output-dir", "-o", help="Output directory for test results"),
    gemini_model: str = typer.Option(None, "--model", "-m", help="Gemini model to use (defaults to config)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
    concurrency: int = typer.Option(3, "--concurrency", "-c", help="Concurrent operations (1-10)"),
    fullpage: bool = typer.Option(False, "--fullpage", help="Take full page screenshots"),
    timeout: int = typer.Option(30000, "--timeout", help="Page timeout in milliseconds"),
    proxy: Optional[str] = typer.Option(None, "--proxy", help="Proxy URL if needed"),
    subfinder_bin: str = typer.Option("subfinder", "--subfinder-bin", help="Path to subfinder binary"),
):
    """Quick test run with limited subdomains for benchmarking and validation."""
    
    # Setup logging
    from .utils import setup_logging
    setup_logging(verbose=verbose)
    logger = logging.getLogger(__name__)
    
    try:
        # Create configuration
        config = AppConfig.from_cli(
            output_dir=Path(output_dir),
            gemini_model=gemini_model if gemini_model else None,  # Only override if explicitly provided
            max_cost_usd=5.0,  # Lower cost limit for testing
            dry_run=False,  # Always run analysis for testing
            verbose=verbose,
            concurrency=min(concurrency, 10),  # Cap concurrency for testing
            fullpage=fullpage,
            timeout_ms=timeout,
            proxy=proxy,
            subfinder_bin=subfinder_bin
        )
        
        console.print(f"[bold blue]SnapRecon Test Mode[/bold blue] - Quick benchmark run")
        console.print(f"Test targets: [yellow]{test_count}[/yellow] subdomains")
        console.print(f"Output directory: [green]{config.run_dir}[/green]")
        console.print(f"Model: [cyan]{config.gemini_model}[/cyan]")
        
        # Resolve targets
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Resolving targets...", total=None)
            
            if domain:
                all_targets = resolve_targets(config=config, domain=domain)
                # Limit to test_count
                targets = all_targets[:test_count]
                progress.update(task, description=f"Testing {len(targets)} of {len(all_targets)} discovered targets")
            else:
                console.print("[red]Error:[/red] Domain is required for test mode")
                raise typer.Exit(1)
        
        # Enforce scope
        console.print(f"[yellow]Enforcing scope from:[/yellow] {scope_file}")
        targets = enforce_scope(targets, scope_file)
        console.print(f"[green]✓[/green] {len(targets)} targets in scope for testing")
        
        # Take screenshots
        console.print(f"[yellow]Taking screenshots...[/yellow]")
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Processing targets...", total=len(targets))
            
            # Take screenshots
            targets = asyncio.run(screenshot_many(targets, config))
            
            # Update progress
            successful = len([t for t in targets if t.metadata and t.metadata.screenshot_path])
            failed = len([t for t in targets if t.error])
            progress.update(task, description=f"Screenshots: {successful} success, {failed} failed")
        
        console.print(f"[green]✓[/green] Screenshots completed")
        
        # Analyze with local keyword analysis
        console.print(f"[yellow]Analyzing screenshots with local keyword analysis...[/yellow]")
        analyzer = LocalKeywordAnalyzer(config)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Analyzing targets...", total=len(targets))
            
            # Analyze targets
            targets = asyncio.run(analyzer.analyze_many(targets))
            
            # Update progress
            analyzed = len([t for t in targets if t.llm_result])
            failed_analysis = len([t for t in targets if t.error and not t.metadata])
            progress.update(task, description=f"Analysis: {analyzed} success, {failed_analysis} failed")
        
        console.print(f"[green]✓[/green] Analysis completed")
        
        # Create results
        total_cost = sum(t.llm_result.cost_usd for t in targets if t.llm_result)
        success_count = len([t for t in targets if not t.error])
        error_count = len([t for t in targets if t.error])
        
        # Create safe config without sensitive data
        safe_config = SafeConfig(
            output_dir=str(config.output_dir),
            run_dir=str(config.run_dir),
            gemini_model=config.gemini_model,
            max_cost_usd=config.max_cost_usd,
            user_agent=config.user_agent,
            proxy=config.proxy,
            timeout_ms=config.timeout_ms,
            fullpage=config.fullpage,
            subfinder_bin=config.subfinder_bin,
            concurrency=config.concurrency,
            dry_run=config.dry_run,
            verbose=config.verbose,
            availability_check_enabled=config.availability_check_enabled,
        )
        
        results = RunResult(
            config=safe_config,
            targets=targets,
            total_cost_usd=total_cost,
            success_count=success_count,
            error_count=error_count
        )
        
        # Write reports
        console.print(f"[yellow]Generating test reports...[/yellow]")
        output_files = write_results_and_reports(results, config)
        
        # Display test summary
        console.print(f"\n[bold green]✓ Test run completed![/bold green]")
        
        summary_table = Table(title="Test Run Summary")
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="green")
        
        summary_table.add_row("Test Targets", str(len(targets)))
        summary_table.add_row("Successful Screenshots", str(success_count))
        summary_table.add_row("Failed Screenshots", str(error_count))
        summary_table.add_row("Total Cost", f"${total_cost:.4f}")
        summary_table.add_row("Output Directory", str(config.run_dir))
        summary_table.add_row("Model Used", config.gemini_model)
        
        console.print(summary_table)
        
        # Show output files
        console.print(f"\n[bold]Test Output Files:[/bold]")
        for file_type, file_path in output_files.items():
            console.print(f"  [green]•[/green] {file_type}: {file_path}")
        
        # Performance metrics
        console.print(f"\n[bold]Performance Metrics:[/bold]")
        console.print(f"  [cyan]•[/cyan] Cost per target: ${total_cost/len(targets):.4f}")
        console.print(f"  [cyan]•[/cyan] Success rate: {(success_count/len(targets)*100):.1f}%")
        console.print(f"  [cyan]•[/cyan] Ready for full run: {'Yes' if success_count/len(targets) > 0.8 else 'No'}")
        
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        if verbose:
            import traceback
            console.print(traceback.format_exc())
        raise typer.Exit(1)


@app.command()
def quick(
    domain: Optional[str] = typer.Option(None, "--domain", "-d", help="Domain to discover subdomains for"),
    input_file: Optional[str] = typer.Option(None, "--input-file", "-i", help="File containing target hosts (one per line)"),
    domains_file: Optional[str] = typer.Option(
        None,
        "--domains-file",
        help="Path to domains.txt containing targets (short for --input-file)",
        show_default=False,
    ),
    output_dir: str = typer.Option("runs", "--output-dir", "-o", help="Output directory for results"),
    gemini_model: Optional[str] = typer.Option(None, "--model", "-m", help="Gemini model to use (overrides config.toml)"),
    max_cost: float = typer.Option(10.0, "--max-cost", help="Maximum cost in USD"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Skip LLM analysis"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
    concurrency: int = typer.Option(5, "--concurrency", "-c", help="Concurrent operations (1-20)"),
    fullpage: bool = typer.Option(False, "--fullpage", help="Take full page screenshots"),
    timeout: int = typer.Option(30000, "--timeout", help="Page timeout in milliseconds"),
    proxy: Optional[str] = typer.Option(None, "--proxy", help="Proxy URL if needed"),
    subfinder_bin: str = typer.Option("subfinder", "--subfinder-bin", help="Path to subfinder binary"),
    enable_port_scan: bool = typer.Option(False, "--enable-port-scan", help="Include an 'Open Ports' section in the HTML report"),
    port_ranges: str = typer.Option("80,443", "--port-ranges", help="Comma-separated port tokens/ranges (e.g., 80,443,8080-8090)"),
    skip_availability_check: bool = typer.Option(
        False,
        "--skip-availability-check",
        help="Disable pre-scan availability checks before screenshots",
    ),
):
    """Quick reconnaissance without scope file - automatically filters to resolving domains only."""
    
    # Setup logging
    setup_logging(verbose=verbose)
    logger = logging.getLogger(__name__)
    
    try:
        # Parse port ranges
        port_ranges_list = [p.strip() for p in port_ranges.split(",") if p.strip()]

        # Create configuration
        config = AppConfig.from_cli(
            output_dir=Path(output_dir),
            gemini_model=gemini_model,
            max_cost_usd=max_cost,
            dry_run=dry_run,
            verbose=verbose,
            concurrency=concurrency,
            fullpage=fullpage,
            timeout_ms=timeout,
            proxy=proxy,
            subfinder_bin=subfinder_bin,
            port_scan_enabled=enable_port_scan,
            port_ranges=port_ranges_list,
            availability_check_enabled=not skip_availability_check,
        )
        
        console.print(f"[bold blue]SnapRecon Quick Mode[/bold blue] - No scope file required")
        console.print(f"Output directory: [green]{config.run_dir}[/green]")
        if enable_port_scan:
            console.print(f"[yellow]Ports sidecar enabled[/yellow] - Ports: {port_ranges}")
        if config.availability_check_enabled:
            console.print(f"[yellow]Note:[/yellow] Only domains that return a working HTTP response (2xx/3xx/401/403) will be processed")
        else:
            console.print(f"[yellow]Availability checks disabled[/yellow] - all listed targets will be processed")
        
        # Resolve targets
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Resolving targets...", total=None)
            
            if domain:
                targets = resolve_targets(config=config, domain=domain)
                progress.update(task, description=f"Discovered {len(targets)} targets from {domain}")
            else:
                file_arg = domains_file or input_file
                file_path: Path
                if file_arg:
                    file_path = Path(file_arg)
                else:
                    default_domains = Path("domains.txt")
                    if not default_domains.exists():
                        console.print("[red]Error:[/red] Provide --domain, --domains-file, --input-file, or place domains.txt in the working directory")
                        raise typer.Exit(1)
                    file_path = default_domains
                    console.print(f"[yellow]Using default domains file:[/yellow] {file_path.resolve()}")

                targets = resolve_targets(config=config, input_file=str(file_path))
                progress.update(task, description=f"Loaded {len(targets)} targets from {file_path}")
        
        # No in-pipeline port scan
        targets_to_process = targets
        if config.availability_check_enabled:
            console.print(f"[yellow]Discovered {len(targets)} targets - testing availability...[/yellow]")

            # Test domain resolution using lightweight HTTP checks (no browser)
            from .browser import test_domain_resolution

            targets_for_availability = [
                Target(host=t.host, domain=t.domain, subdomain=t.subdomain)
                for t in targets
            ]
            targets_to_process = asyncio.run(test_domain_resolution(targets_for_availability, config))

            console.print(f"[green]✓[/green] {len(targets_to_process)} targets returned a working HTTP response")

            if not targets_to_process:
                console.print("[red]No targets returned a working HTTP response. Exiting.[/red]")
                raise typer.Exit(1)
        else:
            console.print(f"[yellow]Processing {len(targets)} targets without availability checks...[/yellow]")
        
        # Take screenshots
        console.print(f"[yellow]Taking screenshots...[/yellow]")
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Processing targets...", total=len(targets_to_process))
            
            # Take screenshots
            targets = asyncio.run(screenshot_many(targets_to_process, config))
            
            # Update progress
            successful = len([t for t in targets if t.metadata and t.metadata.screenshot_path])
            failed = len([t for t in targets if t.error])
            progress.update(task, description=f"Screenshots: {successful} success, {failed} failed")
        
        console.print(f"[green]✓[/green] Screenshots completed")
        
        # Analyze with local keyword analysis (if not dry run)
        if not dry_run:
            console.print(f"[yellow]Analyzing screenshots with local keyword analysis...[/yellow]")
            analyzer = LocalKeywordAnalyzer(config)
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("Analyzing targets...", total=len(targets))
                
                # Analyze targets
                targets = asyncio.run(analyzer.analyze_many(targets))
                
                # Update progress
                analyzed = len([t for t in targets if t.llm_result])
                failed_analysis = len([t for t in targets if t.error and not t.metadata])
                progress.update(task, description=f"Analysis: {analyzed} success, {failed_analysis} failed")
            
            console.print(f"[green]✓[/green] Analysis completed")
        else:
            console.print(f"[yellow]Skipping LLM analysis (dry run mode)[/yellow]")
        
        # Create results
        total_cost = sum(t.llm_result.cost_usd for t in targets if t.llm_result)
        success_count = len([t for t in targets if not t.error])
        error_count = len([t for t in targets if t.error])

        # Create safe config without sensitive data
        safe_config = SafeConfig(
            output_dir=str(config.output_dir),
            run_dir=str(config.run_dir),
            gemini_model=config.gemini_model,
            max_cost_usd=config.max_cost_usd,
            user_agent=config.user_agent,
            proxy=config.proxy,
            timeout_ms=config.timeout_ms,
            fullpage=config.fullpage,
            subfinder_bin=config.subfinder_bin,
            concurrency=config.concurrency,
            dry_run=config.dry_run,
            verbose=config.verbose,
            availability_check_enabled=config.availability_check_enabled,
        )

        results = RunResult(
            config=safe_config,
            targets=targets,
            total_cost_usd=total_cost,
            success_count=success_count,
            error_count=error_count,
        )
        
        # Prepare ports map for HTML if enabled
        ports_map = None
        scanned_ports = None
        if enable_port_scan:
            unique_hosts = sorted({t.host for t in targets_to_process})
            console.print(f"[yellow]Scanning ports (sidecar)...[/yellow]")
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("Scanning ports...", total=None)
                ports_map = asyncio.run(
                    scan_ports_for_hosts(unique_hosts, config.port_ranges, max(1, config.concurrency * 10))
                )
                progress.update(task, description=f"Ports scanned for {len(ports_map)} hosts")
            from .port_scanner import parse_port_tokens
            scanned_ports = parse_port_tokens(config.port_ranges)

        # Write reports (pass optional ports context)
        console.print(f"[yellow]Generating reports...[/yellow]")
        output_files = write_results_and_reports(results, config, ports_map=ports_map, scanned_ports=scanned_ports)
        
        # Display summary
        console.print(f"\n[bold green]✓ Quick run completed successfully![/bold green]")
        
        summary_table = Table(title="Quick Run Summary")
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="green")
        
        summary_table.add_row("Targets Loaded", str(len(targets)))
        if config.availability_check_enabled:
            summary_table.add_row("Passed Availability", str(len(targets_to_process)))
        else:
            summary_table.add_row("Availability Checks", "Skipped")
        summary_table.add_row("Successful Screenshots", str(success_count))
        summary_table.add_row("Failed Screenshots", str(error_count))
        if not dry_run:
            summary_table.add_row("Total Cost", f"${total_cost:.4f}")
        summary_table.add_row("Output Directory", str(config.run_dir))
        
        console.print(summary_table)
        
        # Show output files
        console.print(f"\n[bold]Output Files:[/bold]")
        for file_type, file_path in output_files.items():
            console.print(f"  [green]•[/green] {file_type}: {file_path}")
        
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        if verbose:
            import traceback
            console.print(traceback.format_exc())
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
