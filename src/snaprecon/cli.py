"""Main CLI entry point for SnapRecon."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table

from .analysis import analyze_targets
from .browser import screenshot_many
from .config import AppConfig
from .discover import resolve_targets
from .errors import DependencyError
from .models import RunResult, SafeConfig, Target
from .reporting import write_results_and_reports
from .tech import detect_technologies
from .utils import check_optional_dependencies, check_required_dependencies, setup_logging

app = typer.Typer(
    add_completion=False,
    help="SnapRecon CLI for authorized reconnaissance via discovery, screenshots, and local analysis.",
)
console = Console()


def _run_wappalyzer(targets: list[Target], config: AppConfig, console: Console) -> list[Target]:
    """Execute the optional Wappalyzer fingerprinting step."""

    if not config.wappalyzer_enabled or not targets:
        return targets

    console.print("[yellow]Running Wappalyzer technology detection...[/yellow]")

    tech_completed = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None),
        TextColumn("{task.completed}/{task.total}", justify="right"),
        console=console,
    ) as progress:
        task = progress.add_task("Fingerprinting targets...", total=len(targets))

        def update(_: Target) -> None:
            nonlocal tech_completed
            tech_completed += 1
            progress.update(task, completed=tech_completed)

        try:
            return asyncio.run(detect_technologies(targets, config, progress_callback=update))
        except RuntimeError as exc:
            console.print(f"[red]✗[/red] Technology detection unavailable: {exc}")
            raise typer.Exit(1) from exc


def _ensure_dependencies(
    config: AppConfig,
    *,
    console: Console,
    wants_wappalyzer: bool,
) -> None:
    """Validate external dependencies before proceeding with the run."""

    try:
        check_required_dependencies(subfinder_bin=config.subfinder_bin, headless=config.headless)
        check_optional_dependencies(wants_wappalyzer=wants_wappalyzer)
    except DependencyError as exc:
        console.print("[red]✗[/red] Missing required dependencies.")
        for line in str(exc).splitlines():
            if not line:
                continue
            console.print(f"[red]-[/red] {line}")
        raise typer.Exit(1) from exc

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    domain: Optional[str] = typer.Option(
        None,
        "--domain",
        "-d",
        help="Run subfinder against a single root domain",
    ),
    targets_file: Optional[str] = typer.Option(
        None,
        "--targets-file",
        "-t",
        help="Load targets from a text file (one host per line)",
        show_default=False,
    ),
    output_dir: str = typer.Option(
        "runs",
        "--output-dir",
        "-o",
        help="Folder to write reports and screenshots",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Skip analysis step and only capture screenshots"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
    scan_profile: str = typer.Option(
        "balanced",
        "--scan-profile",
        help="Preset balance: fast (screenshots only), balanced, full (tech fingerprinting)",
    ),
    concurrency: int = typer.Option(5, "--concurrency", "-c", help="Concurrent browser workers (1-20)"),
    fullpage: bool = typer.Option(False, "--fullpage", help="Capture full-page screenshots instead of viewport"),
    headless: bool = typer.Option(True, "--headless/--headed", help="Run Chromium in headless mode"),
    timeout: int = typer.Option(30000, "--timeout", help="Navigation timeout per target in milliseconds"),
    subfinder_bin: str = typer.Option("subfinder", "--subfinder-bin", help="Executable used for subdomain discovery"),
    enable_wappalyzer: bool = typer.Option(
        False,
        "--wappalyzer",
        help="Enable Wappalyzer technology fingerprinting",
    ),
    wappalyzer_scan: str = typer.Option(
        "balanced",
        "--wappalyzer-scan",
        help="Wappalyzer scan depth",
    ),
    wappalyzer_threads: int = typer.Option(
        3,
        "--wappalyzer-threads",
        help="Wappalyzer thread count (HTTP probes)",
    ),
):
    """Run a full reconnaissance cycle against discovered or pre-supplied targets."""

    if ctx.invoked_subcommand is None:
        run(
            domain=domain,
            targets_file=targets_file,
            output_dir=output_dir,
            dry_run=dry_run,
            debug=debug,
            concurrency=concurrency,
            fullpage=fullpage,
            timeout=timeout,
            subfinder_bin=subfinder_bin,
            headless=headless,
            scan_profile=scan_profile,
            enable_wappalyzer=enable_wappalyzer,
            wappalyzer_scan=wappalyzer_scan,
            wappalyzer_threads=wappalyzer_threads,
        )


@app.command()
def run(
    domain: Optional[str] = typer.Option(
        None,
        "--domain",
        "-d",
        help="Run subfinder against a single root domain",
    ),
    targets_file: Optional[str] = typer.Option(
        None,
        "--targets-file",
        "-t",
        help="Load targets from a text file (one host per line)",
        show_default=False,
    ),
    output_dir: str = typer.Option(
        "runs",
        "--output-dir",
        "-o",
        help="Folder to write reports and screenshots",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Skip analysis step and only capture screenshots"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
    concurrency: int = typer.Option(5, "--concurrency", "-c", help="Concurrent browser workers (1-20)"),
    fullpage: bool = typer.Option(False, "--fullpage", help="Capture full-page screenshots instead of viewport"),
    headless: bool = typer.Option(True, "--headless/--headed", help="Run Chromium in headless mode"),
    timeout: int = typer.Option(30000, "--timeout", help="Navigation timeout per target in milliseconds"),
    subfinder_bin: str = typer.Option("subfinder", "--subfinder-bin", help="Executable used for subdomain discovery"),
    scan_profile: str = typer.Option(
        "balanced",
        "--scan-profile",
        help="Preset: fast (screenshots only), balanced (default), full (with Wappalyzer)",
    ),
    enable_wappalyzer: bool = typer.Option(
        False,
        "--wappalyzer",
        help="Enable Wappalyzer technology fingerprinting",
        show_default=False,
    ),
    wappalyzer_scan: str = typer.Option(
        "balanced",
        "--wappalyzer-scan",
        help="Wappalyzer scan depth",
        show_default=False,
    ),
    wappalyzer_threads: int = typer.Option(
        3,
        "--wappalyzer-threads",
        help="Wappalyzer thread count (HTTP probes)",
        show_default=False,
    ),
):
    """Run a full reconnaissance cycle against discovered or pre-supplied targets."""
    
    # Setup logging
    setup_logging(debug=debug)
    
    try:
        normalized_profile = (scan_profile or "balanced").strip().lower()
        normalized_wapp_scan = (wappalyzer_scan or "balanced").strip().lower()

        enable_wappalyzer = enable_wappalyzer or normalized_profile == "full"
        if normalized_wapp_scan != "balanced":
            enable_wappalyzer = True

        config = AppConfig.from_cli(
            output_dir=Path(output_dir),
            dry_run=dry_run,
            debug=debug,
            concurrency=concurrency,
            fullpage=fullpage,
            timeout_ms=timeout,
            subfinder_bin=subfinder_bin,
            headless=headless,
            scan_profile=normalized_profile,
            wappalyzer_enabled=enable_wappalyzer,
            wappalyzer_scan_type=normalized_wapp_scan,
            wappalyzer_threads=wappalyzer_threads,
        )

        _ensure_dependencies(
            config,
            console=console,
            wants_wappalyzer=config.wappalyzer_enabled,
        )

        console.print("[bold blue]SnapRecon[/bold blue] - Starting reconnaissance run")
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
            elif targets_file:
                file_path = Path(targets_file)
                targets = resolve_targets(config=config, input_file=str(file_path))
                progress.update(task, description=f"Loaded {len(targets)} targets from {file_path}")
            else:
                raise typer.BadParameter(
                    "Missing input: provide --domain or --targets-file. Run 'snaprecon --help' for usage details."
                )

        console.print("[yellow]Taking screenshots...[/yellow]")
        completed = 0

        def update_progress(_: Target) -> None:
            nonlocal completed
            completed += 1
            progress.update(task, completed=completed)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=None),
            TextColumn("{task.completed}/{task.total}", justify="right"),
            console=console,
        ) as progress:
            task = progress.add_task("Processing targets...", total=len(targets))

            targets = asyncio.run(
                screenshot_many(targets, config, progress_callback=update_progress)
            )

        successful = len([t for t in targets if t.metadata and t.metadata.screenshot_path])
        failed = len([t for t in targets if t.error])
        console.print(f"[green]✓[/green] Screenshots completed: {successful} success, {failed} failed")

        targets = _run_wappalyzer(targets, config, console)
        
        # Analyze with local keyword analysis (if not dry run)
        if not dry_run:
            console.print("[yellow]Analyzing screenshots (local heuristics)...[/yellow]")

            analyzed = 0

            def update_analysis(_: Target) -> None:
                nonlocal analyzed
                analyzed += 1
                progress.update(task, completed=analyzed)

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(bar_width=None),
                TextColumn("{task.completed}/{task.total}", justify="right"),
                console=console,
            ) as progress:
                task = progress.add_task("Analyzing targets...", total=len(targets))

                targets = asyncio.run(analyze_targets(targets, progress_callback=update_analysis))

            successful_analysis = len([t for t in targets if t.analysis])
            failed_analysis = len([t for t in targets if t.error and not t.metadata])
            console.print(f"[green]✓[/green] Analysis completed: {successful_analysis} success, {failed_analysis} failed")
        else:
            console.print("[yellow]Skipping analysis (dry run mode)")
        
        # Create results
        results = RunResult(
            config=SafeConfig(
                output_dir=str(config.output_dir),
                run_dir=str(config.run_dir),
                user_agent=config.user_agent,
                timeout_ms=config.timeout_ms,
                fullpage=config.fullpage,
                subfinder_bin=config.subfinder_bin,
                concurrency=config.concurrency,
                dry_run=config.dry_run,
                debug=config.debug,
                headless=config.headless,
                scan_profile=config.scan_profile,
                wappalyzer_enabled=config.wappalyzer_enabled,
                wappalyzer_scan_type=config.wappalyzer_scan_type,
                wappalyzer_threads=config.wappalyzer_threads,
            ),
            targets=targets,
            success_count=len([t for t in targets if t.metadata and t.metadata.screenshot_path]),
            error_count=len([t for t in targets if t.error])
        )

        # Write results and reports
        console.print("[yellow]Generating reports...[/yellow]")
        write_results_and_reports(results, config)
        
        console.print("[green]✓[/green] Reconnaissance completed successfully!")
        console.print(f"Results saved to: [green]{config.run_dir}[/green]")
        
        # Display summary
        display_summary(results)
        
    except typer.Exit:
        raise
    except Exception as e:
        logging.getLogger(__name__).error("Reconnaissance failed: %s", e)
        console.print(f"[red]✗[/red] Reconnaissance failed: {e}")
        raise typer.Exit(1)


def display_summary(results: RunResult):
    """Display a summary of the reconnaissance run."""
    console.print("\n[bold green]✓ Run completed successfully![/bold green]")
    
    summary_table = Table(title="Run Summary")
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="green")
    
    summary_table.add_row("Total Targets", str(len(results.targets)))
    summary_table.add_row("Successful Screenshots", str(results.success_count))
    summary_table.add_row("Failed Screenshots", str(results.error_count))
    summary_table.add_row("Output Directory", str(results.config.run_dir))
    
    console.print(summary_table)
    
    # No inline port scan summary; ports are reported separately when enabled
    
    # Show output files
    console.print("\n[bold]Output Files:[/bold]")
    console.print(f"  [green]•[/green] Results: {results.config.run_dir}/results.json")
    console.print(f"  [green]•[/green] Markdown Report: {results.config.run_dir}/report.md")
    console.print(f"  [green]•[/green] HTML Report: {results.config.run_dir}/report.html")
    console.print(f"  [green]•[/green] Screenshots: {results.config.run_dir}/screenshots/")


@app.command()
def test(
    domain: Optional[str] = typer.Option(
        None,
        "--domain",
        "-d",
        help="Domain to benchmark; uses subfinder before slicing",
    ),
    test_count: int = typer.Option(10, "--test-count", "-n", help="Number of discovered subdomains to exercise"),
    output_dir: str = typer.Option("test-runs", "--output-dir", "-o", help="Folder to write test artefacts"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
    concurrency: int = typer.Option(3, "--concurrency", "-c", help="Concurrent browser workers (1-10)"),
    fullpage: bool = typer.Option(False, "--fullpage", help="Capture full-page screenshots instead of viewport"),
    timeout: int = typer.Option(30000, "--timeout", help="Navigation timeout per target in milliseconds"),
    subfinder_bin: str = typer.Option("subfinder", "--subfinder-bin", help="Executable used for subdomain discovery"),
):
    """Benchmark a domain with a capped number of targets."""
    
    # Setup logging
    setup_logging(debug=debug)
    
    try:
        # Create configuration
        config = AppConfig.from_cli(
            output_dir=Path(output_dir),
            dry_run=False,  # Always run analysis for testing
            debug=debug,
            concurrency=min(concurrency, 10),  # Cap concurrency for testing
            fullpage=fullpage,
            timeout_ms=timeout,
            subfinder_bin=subfinder_bin
        )

        _ensure_dependencies(
            config,
            console=console,
            wants_wappalyzer=config.wappalyzer_enabled,
        )
        
        console.print("[bold blue]SnapRecon Test Mode[/bold blue] - Quick benchmark run")
        console.print(f"Test targets: [yellow]{test_count}[/yellow] subdomains")
        console.print(f"Output directory: [green]{config.run_dir}[/green]")
        console.print(f"Headless mode: {'on' if config.headless else 'off'}")
        
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
        
        # Take screenshots
        console.print("[yellow]Taking screenshots...[/yellow]")
        completed = 0

        def update_progress(_: Target) -> None:
            nonlocal completed
            completed += 1
            progress.update(task, completed=completed)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=None),
            TextColumn("{task.completed}/{task.total}", justify="right"),
            console=console,
        ) as progress:
            task = progress.add_task("Processing targets...", total=len(targets))

            targets = asyncio.run(screenshot_many(targets, config, progress_callback=update_progress))

        successful = len([t for t in targets if t.metadata and t.metadata.screenshot_path])
        failed = len([t for t in targets if t.error])
        console.print(f"[green]✓[/green] Screenshots completed: {successful} success, {failed} failed")
        
        # Analyze with local keyword analysis
        console.print("[yellow]Analyzing screenshots with local keyword analysis...[/yellow]")

        analyzed_count = 0

        def update_analysis(_: Target) -> None:
            nonlocal analyzed_count
            analyzed_count += 1
            progress.update(task, completed=analyzed_count)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Analyzing targets...", total=len(targets))

            targets = asyncio.run(analyze_targets(targets, progress_callback=update_analysis))

        analyzed_success = len([t for t in targets if t.analysis])
        failed_analysis = len([t for t in targets if t.error and not t.metadata])
        console.print(f"[green]✓[/green] Analysis completed: {analyzed_success} success, {failed_analysis} failed")
        
        # Create results
        success_count = len([t for t in targets if not t.error])
        error_count = len([t for t in targets if t.error])
        
        safe_config = SafeConfig(
            output_dir=str(config.output_dir),
            run_dir=str(config.run_dir),
            user_agent=config.user_agent,
            timeout_ms=config.timeout_ms,
            fullpage=config.fullpage,
            subfinder_bin=config.subfinder_bin,
            concurrency=config.concurrency,
            dry_run=config.dry_run,
            debug=config.debug,
            headless=config.headless,
            scan_profile=config.scan_profile,
            wappalyzer_enabled=config.wappalyzer_enabled,
            wappalyzer_scan_type=config.wappalyzer_scan_type,
            wappalyzer_threads=config.wappalyzer_threads,
        )
        
        results = RunResult(
            config=safe_config,
            targets=targets,
            success_count=success_count,
            error_count=error_count
        )
        
        # Write reports
        console.print("[yellow]Generating test reports...[/yellow]")
        output_files = write_results_and_reports(results, config)
        
        # Display test summary
        console.print("\n[bold green]✓ Test run completed![/bold green]")
        
        summary_table = Table(title="Test Run Summary")
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="green")
        
        summary_table.add_row("Test Targets", str(len(targets)))
        summary_table.add_row("Successful Screenshots", str(success_count))
        summary_table.add_row("Failed Screenshots", str(error_count))
        summary_table.add_row("Output Directory", str(config.run_dir))
        
        console.print(summary_table)
        
        # Show output files
        console.print("\n[bold]Test Output Files:[/bold]")
        for file_type, file_path in output_files.items():
            console.print(f"  [green]•[/green] {file_type}: {file_path}")
        
        # Performance metrics
        console.print("\n[bold]Performance Metrics:[/bold]")
        console.print(f"  [cyan]•[/cyan] Success rate: {(success_count/len(targets)*100):.1f}%")
        console.print(f"  [cyan]•[/cyan] Ready for full run: {'Yes' if success_count/len(targets) > 0.8 else 'No'}")
        
    except typer.Exit:
        raise
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        if debug:
            import traceback
            console.print(traceback.format_exc())
        raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        if debug:
            import traceback
            console.print(traceback.format_exc())
        raise typer.Exit(1)
        return


@app.command()
def quick(
    domain: Optional[str] = typer.Option(
        None,
        "--domain",
        "-d",
        help="Run subfinder against a single root domain",
    ),
    targets_file: Optional[str] = typer.Option(
        None,
        "--targets-file",
        "-t",
        help="Load targets from a text file (one host per line)",
        show_default=False,
    ),
    output_dir: str = typer.Option("runs", "--output-dir", "-o", help="Folder to write reports and screenshots"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Skip analysis step and only capture screenshots"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
    concurrency: int = typer.Option(5, "--concurrency", "-c", help="Concurrent browser workers (1-20)"),
    fullpage: bool = typer.Option(False, "--fullpage", help="Capture full-page screenshots instead of viewport"),
    headless: bool = typer.Option(True, "--headless/--headed", help="Run Chromium in headless mode"),
    timeout: int = typer.Option(30000, "--timeout", help="Navigation timeout per target in milliseconds"),
    subfinder_bin: str = typer.Option("subfinder", "--subfinder-bin", help="Executable used for subdomain discovery"),
):
    """Recon without a scope file."""
    
    setup_logging(debug=debug)
    
    try:
        config = AppConfig.from_cli(
            output_dir=Path(output_dir),
            dry_run=dry_run,
            debug=debug,
            concurrency=concurrency,
            fullpage=fullpage,
            timeout_ms=timeout,
            subfinder_bin=subfinder_bin,
            headless=headless,
        )
        
        console.print("[bold blue]SnapRecon Quick Mode[/bold blue] - Fast screenshots without analysis")
        console.print(f"Output directory: [green]{config.run_dir}[/green]")
        
        _ensure_dependencies(
            config,
            console=console,
            wants_wappalyzer=config.wappalyzer_enabled,
        )

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
                if not targets_file:
                    console.print("[red]Error:[/red] Provide either --domain or --targets-file")
                    raise typer.Exit(1)
                file_path = Path(targets_file)
                targets = resolve_targets(config=config, input_file=str(file_path))
                progress.update(task, description=f"Loaded {len(targets)} targets from {file_path}")
        
        console.print("[yellow]Taking screenshots...[/yellow]")
        completed = 0

        def update_progress(_: Target) -> None:
            nonlocal completed
            completed += 1
            progress.update(task, completed=completed)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=None),
            TextColumn("{task.completed}/{task.total}", justify="right"),
            console=console,
        ) as progress:
            task = progress.add_task("Processing targets...", total=len(targets))

            targets = asyncio.run(screenshot_many(targets, config, progress_callback=update_progress))

        successful = len([t for t in targets if t.metadata and t.metadata.screenshot_path])
        failed = len([t for t in targets if t.error])
        console.print(f"[green]✓[/green] Screenshots completed: {successful} success, {failed} failed")
        
        if not dry_run:
            console.print("[yellow]Analyzing screenshots with local keyword analysis...[/yellow]")

            analyzed_count = 0

            def update_analysis(_: Target) -> None:
                nonlocal analyzed_count
                analyzed_count += 1
                progress.update(task, completed=analyzed_count)

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(bar_width=None),
                TextColumn("{task.completed}/{task.total}", justify="right"),
                console=console,
            ) as progress:
                task = progress.add_task("Analyzing targets...", total=len(targets))

                targets = asyncio.run(analyze_targets(targets, progress_callback=update_analysis))

            analyzed_success = len([t for t in targets if t.analysis])
            failed_analysis = len([t for t in targets if t.error and not t.metadata])
            console.print(f"[green]✓[/green] Analysis completed: {analyzed_success} success, {failed_analysis} failed")
        else:
            console.print("[yellow]Skipping analysis (dry run mode)")
        
        success_count = len([t for t in targets if not t.error])
        error_count = len([t for t in targets if t.error])
        
        safe_config = SafeConfig(
            output_dir=str(config.output_dir),
            run_dir=str(config.run_dir),
            user_agent=config.user_agent,
            timeout_ms=config.timeout_ms,
            fullpage=config.fullpage,
            subfinder_bin=config.subfinder_bin,
            concurrency=config.concurrency,
            dry_run=config.dry_run,
            debug=config.debug,
            headless=config.headless,
            scan_profile=config.scan_profile,
            wappalyzer_enabled=config.wappalyzer_enabled,
            wappalyzer_scan_type=config.wappalyzer_scan_type,
            wappalyzer_threads=config.wappalyzer_threads,
        )
        
        results = RunResult(
            config=safe_config,
            targets=targets,
            success_count=success_count,
            error_count=error_count,
        )
        
        console.print("[yellow]Generating reports...[/yellow]")
        output_files = write_results_and_reports(results, config)
        
        console.print("\n[bold green]✓ Quick run completed successfully![/bold green]")
        
        summary_table = Table(title="Quick Run Summary")
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="green")
        
        summary_table.add_row("Targets Processed", str(len(targets)))
        summary_table.add_row("Successful Screenshots", str(success_count))
        summary_table.add_row("Failed Screenshots", str(error_count))
        summary_table.add_row("Output Directory", str(config.run_dir))
        
        console.print(summary_table)
        
        console.print("\n[bold]Output Files:[/bold]")
        for file_type, file_path in output_files.items():
            console.print(f"  [green]•[/green] {file_type}: {file_path}")
        
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        if debug:
            import traceback
            console.print(traceback.format_exc())
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
