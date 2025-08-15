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
from .discover import resolve_targets
from .browser import screenshot_many
from .analysis import GeminiAnalyzer
from .reporting import write_results_and_reports
from .safety import enforce_scope
from .models import Target, RunResult, SafeConfig
from .utils import setup_logging

app = typer.Typer(add_completion=False, help="SnapRecon: Authorized reconnaissance with screenshot analysis")
console = Console()


@app.command()
def run(
    domain: Optional[str] = typer.Option(None, "--domain", "-d", help="Domain to discover subdomains for"),
    input_file: Optional[str] = typer.Option(None, "--input-file", "-i", help="File containing target hosts (one per line)"),
    scope_file: str = typer.Option(..., "--scope-file", "-s", help="File containing allowed domains/suffixes"),
    output_dir: str = typer.Option("runs", "--output-dir", "-o", help="Output directory for results"),
    gemini_model: str = typer.Option("gemini-1.5-flash", "--model", "-m", help="Gemini model to use"),
    max_cost: float = typer.Option(10.0, "--max-cost", help="Maximum cost in USD"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Skip LLM analysis"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
    concurrency: int = typer.Option(5, "--concurrency", "-c", help="Concurrent operations (1-20)"),
    fullpage: bool = typer.Option(False, "--fullpage", help="Take full page screenshots"),
    timeout: int = typer.Option(30000, "--timeout", help="Page timeout in milliseconds"),
    proxy: Optional[str] = typer.Option(None, "--proxy", help="Proxy URL if needed"),
    subfinder_bin: str = typer.Option("subfinder", "--subfinder-bin", help="Path to subfinder binary"),
):
    """Main entry: discover → screenshot → (optional) analyze → report."""
    
    # Setup logging
    setup_logging(verbose=verbose)
    logger = logging.getLogger(__name__)
    
    try:
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
            subfinder_bin=subfinder_bin
        )
        
        console.print(f"[bold blue]SnapRecon[/bold blue] - Starting reconnaissance run")
        console.print(f"Output directory: [green]{config.run_dir}[/green]")
        
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
                targets = resolve_targets(config=config, input_file=input_file)
                progress.update(task, description=f"Loaded {len(targets)} targets from file")
        
        # Enforce scope
        console.print(f"[yellow]Enforcing scope from:[/yellow] {scope_file}")
        targets = enforce_scope(targets, scope_file)
        console.print(f"[green]✓[/green] {len(targets)} targets in scope")
        
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
        
        # Analyze with Gemini (if not dry run)
        if not dry_run:
            console.print(f"[yellow]Analyzing screenshots with Gemini Vision...[/yellow]")
            analyzer = GeminiAnalyzer(config)
            
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
            verbose=config.verbose
        )
        
        results = RunResult(
            config=safe_config,
            targets=targets,
            total_cost_usd=total_cost,
            success_count=success_count,
            error_count=error_count
        )
        
        # Write reports
        console.print(f"[yellow]Generating reports...[/yellow]")
        output_files = write_results_and_reports(results, config)
        
        # Display summary
        console.print(f"\n[bold green]✓ Run completed successfully![/bold green]")
        
        summary_table = Table(title="Run Summary")
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="green")
        
        summary_table.add_row("Total Targets", str(len(targets)))
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
        
        # Analyze with Gemini
        console.print(f"[yellow]Analyzing screenshots with Gemini Vision...[/yellow]")
        analyzer = GeminiAnalyzer(config)
        
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
            verbose=config.verbose
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
    output_dir: str = typer.Option("runs", "--output-dir", "-o", help="Output directory for results"),
    gemini_model: str = typer.Option("gemini-1.5-flash", "--model", "-m", help="Gemini model to use"),
    max_cost: float = typer.Option(10.0, "--max-cost", help="Maximum cost in USD"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Skip LLM analysis"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
    concurrency: int = typer.Option(5, "--concurrency", "-c", help="Concurrent operations (1-20)"),
    fullpage: bool = typer.Option(False, "--fullpage", help="Take full page screenshots"),
    timeout: int = typer.Option(30000, "--timeout", help="Page timeout in milliseconds"),
    proxy: Optional[str] = typer.Option(None, "--proxy", help="Proxy URL if needed"),
    subfinder_bin: str = typer.Option("subfinder", "--subfinder-bin", help="Path to subfinder binary"),
):
    """Quick reconnaissance without scope file - automatically filters to resolving domains only."""
    
    # Setup logging
    setup_logging(verbose=verbose)
    logger = logging.getLogger(__name__)
    
    try:
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
            subfinder_bin=subfinder_bin
        )
        
        console.print(f"[bold blue]SnapRecon Quick Mode[/bold blue] - No scope file required")
        console.print(f"Output directory: [green]{config.run_dir}[/green]")
        console.print(f"[yellow]Note:[/yellow] Only domains that return a working HTTP response (2xx/3xx/401/403) will be processed")
        
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
                targets = resolve_targets(config=config, input_file=input_file)
                progress.update(task, description=f"Loaded {len(targets)} targets from file")
        
        console.print(f"[yellow]Discovered {len(targets)} targets - testing availability...[/yellow]")
        
        # Test domain resolution and filter to only those that resolve
        from .browser import test_domain_resolution
        resolving_targets = asyncio.run(test_domain_resolution(targets, config))
        
        console.print(f"[green]✓[/green] {len(resolving_targets)} targets returned a working HTTP response")
        
        if not resolving_targets:
            console.print("[red]No targets returned a working HTTP response. Exiting.[/red]")
            raise typer.Exit(1)
        
        # Take screenshots
        console.print(f"[yellow]Taking screenshots...[/yellow]")
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Processing targets...", total=len(resolving_targets))
            
            # Take screenshots
            targets = asyncio.run(screenshot_many(resolving_targets, config))
            
            # Update progress
            successful = len([t for t in targets if t.metadata and t.metadata.screenshot_path])
            failed = len([t for t in targets if t.error])
            progress.update(task, description=f"Screenshots: {successful} success, {failed} failed")
        
        console.print(f"[green]✓[/green] Screenshots completed")
        
        # Analyze with Gemini (if not dry run)
        if not dry_run:
            console.print(f"[yellow]Analyzing screenshots with Gemini Vision...[/yellow]")
            analyzer = GeminiAnalyzer(config)
            
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
            verbose=config.verbose
        )
        
        results = RunResult(
            config=safe_config,
            targets=targets,
            total_cost_usd=total_cost,
            success_count=success_count,
            error_count=error_count
        )
        
        # Write reports
        console.print(f"[yellow]Generating reports...[/yellow]")
        output_files = write_results_and_reports(results, config)
        
        # Display summary
        console.print(f"\n[bold green]✓ Quick run completed successfully![/bold green]")
        
        summary_table = Table(title="Quick Run Summary")
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="green")
        
        summary_table.add_row("Total Discovered", str(len(resolving_targets)))
        summary_table.add_row("Successfully Resolved", str(len(resolving_targets)))
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
