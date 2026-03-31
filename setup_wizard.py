#!/usr/bin/env python3
"""
PhD Literature Extraction Pipeline — Setup Wizard
====================================================
Interactive CLI orchestrator that bootstraps a new research project:
  - Collects project metadata interactively or from existing config
  - Generates all pipeline Python files via codegen
  - Creates Google Sheets (main + auto)
  - Creates local directory structure
  - Optionally creates Google Drive folders
  - Prints a rich summary panel

Usage:
    python setup_wizard.py                  # Interactive mode
    python setup_wizard.py --from-config    # Read existing research_config.yaml
    python setup_wizard.py --generate-only  # Generate Python files only (no sheets/folders)
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich import box

from codegen.config_loader import (
    ResearchConfig,
    ProjectConfig,
    PaperConfig,
    ScholarConfig,
    DatabaseConfig,
    ResearchContext,
    CustomSection,
    ColumnDef,
    GoogleSheetsConfig,
    ApiConfig,
    load_config,
    save_config,
)

console = Console()

# ─── CONSTANTS ───────────────────────────────────────────────

DEFAULT_CONFIG_PATH = "research_config.yaml"
PIPELINE_DIR = Path(__file__).parent

# Earthy color palette (matches terminal_ui.py / main.py)
STYLE_TITLE = "bold cyan"
STYLE_SUBTITLE = "dim"
STYLE_SUCCESS = "bold green"
STYLE_WARNING = "yellow"
STYLE_ERROR = "bold red"
STYLE_ACCENT = "bold magenta"
STYLE_MUTED = "dim"


# ─── WELCOME ────────────────────────────────────────────────


def _show_welcome():
    """Display the welcome banner."""
    content = Text()
    content.append("PhD LITERATURE EXTRACTION PIPELINE\n", style=STYLE_TITLE)
    content.append("Setup Wizard\n\n", style=STYLE_ACCENT)
    content.append(
        "This wizard will configure your research project and generate\n"
        "all pipeline files, Google Sheets, and folder structures.\n\n",
        style=STYLE_SUBTITLE,
    )
    content.append("Steps:\n", style="bold")
    content.append("  1. Project info\n")
    content.append("  2. Paper definitions\n")
    content.append("  3. Research context\n")
    content.append("  4. Key scholars & theories\n")
    content.append("  5. Custom extraction sections\n")
    content.append("  6. Dropdown values\n")
    content.append("  7. API configuration\n")
    content.append("  8. Generate pipeline files\n")
    content.append("  9. Create Google Sheets & folders\n")
    console.print(Panel(content, border_style="cyan", box=box.DOUBLE))
    console.print()


# ─── INTERACTIVE COLLECTORS ─────────────────────────────────


def _collect_project_info() -> ProjectConfig:
    """Step 1: Collect project title and researcher name."""
    console.rule("[bold cyan]Step 1: Project Info", style="cyan")
    console.print()

    title = Prompt.ask(
        "  Full project title",
        default="Board Gender Diversity and Corporate Risk-Taking",
    )
    short_title = Prompt.ask(
        "  Short title (for filenames/sheets)",
        default=title.split(" and ")[0].strip() if " and " in title else title[:30],
    )
    researcher = Prompt.ask("  Researcher name", default="Researcher")

    console.print()
    return ProjectConfig(title=title, short_title=short_title, researcher_name=researcher)


def _collect_papers() -> list[PaperConfig]:
    """Step 2: Collect paper definitions."""
    console.rule("[bold cyan]Step 2: Paper Definitions", style="cyan")
    console.print()
    console.print(
        "  [dim]Define the papers in your literature review.\n"
        "  Each paper has a short label and a research focus.[/]\n"
    )

    count = IntPrompt.ask("  How many papers to define now?", default=0)
    papers = []

    for i in range(1, count + 1):
        console.print(f"\n  [bold]Paper {i}:[/]")
        label = Prompt.ask(f"    Label (e.g., 'Adams_2009')")
        focus = Prompt.ask(f"    Focus/topic", default="")
        papers.append(
            PaperConfig(id=f"P{i:03d}", label=label, focus=focus)
        )

    console.print()
    return papers


def _collect_research_context() -> ResearchContext:
    """Step 3: Collect research context."""
    console.rule("[bold cyan]Step 3: Research Context", style="cyan")
    console.print()

    summary = Prompt.ask(
        "  Research summary\n  (brief description of your study)",
        default="",
    )
    critical_note = Prompt.ask(
        "  Critical note\n  (key methodological or theoretical concern)",
        default="",
    )

    # Databases
    databases = []
    console.print()
    if Confirm.ask("  Add research databases?", default=False):
        while True:
            db_name = Prompt.ask("    Database name (or 'done' to finish)")
            if db_name.lower() == "done":
                break
            db_purpose = Prompt.ask("    Purpose", default="Literature search")
            databases.append(DatabaseConfig(name=db_name, purpose=db_purpose))

    console.print()
    return ResearchContext(
        summary=summary, critical_note=critical_note, databases=databases
    )


def _collect_scholars() -> list[ScholarConfig]:
    """Step 4a: Collect key scholars."""
    console.rule("[bold cyan]Step 4: Key Scholars & Theories", style="cyan")
    console.print()

    scholars = []
    if Confirm.ask("  Define key scholars?", default=False):
        while True:
            name = Prompt.ask("    Scholar name (or 'done' to finish)")
            if name.lower() == "done":
                break
            key = Prompt.ask("    Key identifier (e.g., 'Adams')")
            ctx = Prompt.ask("    Context (their contribution)", default="")
            scholars.append(ScholarConfig(name=name, key=key, context=ctx))

    console.print()
    return scholars


def _collect_theories() -> list[str]:
    """Step 4b: Collect theories."""
    theories_input = Prompt.ask(
        "  Theories (comma-separated, or leave blank)",
        default="",
    )
    theories = [t.strip() for t in theories_input.split(",") if t.strip()]
    console.print()
    return theories


def _collect_custom_sections() -> list[CustomSection]:
    """Step 5: Collect custom extraction sections beyond the standard 11."""
    console.rule("[bold cyan]Step 5: Custom Extraction Sections", style="cyan")
    console.print()
    console.print(
        "  [dim]Standard sections 1-11 (+ CONNECTIONS) are always included.\n"
        "  Add custom sections for domain-specific extraction.[/]\n"
    )

    sections = []
    if not Confirm.ask("  Add custom extraction sections?", default=False):
        console.print()
        return sections

    while True:
        section_id = Prompt.ask("    Section ID (e.g., '12_BOARD_CHARS' or 'done')")
        if section_id.lower() == "done":
            break
        label = Prompt.ask("    Section label", default=section_id)

        columns = []
        console.print("    [dim]Define columns (type 'done' when finished):[/]")
        while True:
            col_name = Prompt.ask("      Column name (or 'done')")
            if col_name.lower() == "done":
                break
            col_type = Prompt.ask("      Type", default="text")
            columns.append(ColumnDef(name=col_name, type=col_type))

        sections.append(CustomSection(id=section_id, label=label, columns=columns))

    console.print()
    return sections


def _collect_dropdowns() -> dict:
    """Step 6: Collect dropdown values for classification."""
    console.rule("[bold cyan]Step 6: Dropdown Values", style="cyan")
    console.print()

    primary_themes_input = Prompt.ask(
        "  Primary themes (comma-separated)",
        default="",
    )
    primary_themes = [t.strip() for t in primary_themes_input.split(",") if t.strip()]

    dv_categories_input = Prompt.ask(
        "  DV categories (comma-separated)",
        default="",
    )
    dv_categories = [t.strip() for t in dv_categories_input.split(",") if t.strip()]

    console.print()
    return {
        "primary_themes": primary_themes,
        "dv_categories": dv_categories,
    }


def _collect_api_config() -> ApiConfig:
    """Step 7: Collect API configuration."""
    console.rule("[bold cyan]Step 7: API Configuration", style="cyan")
    console.print()

    mailto = Prompt.ask(
        "  Email for OpenAlex/Unpaywall (polite pool)",
        default="",
    )

    console.print()
    return ApiConfig(mailto=mailto)


# ─── CONFIG ASSEMBLY ─────────────────────────────────────────


def collect_interactive_config() -> ResearchConfig:
    """Run all interactive collection steps and return a ResearchConfig."""
    _show_welcome()

    project = _collect_project_info()
    papers = _collect_papers()
    context = _collect_research_context()
    scholars = _collect_scholars()
    theories = _collect_theories()
    custom_sections = _collect_custom_sections()
    dropdowns = _collect_dropdowns()
    api = _collect_api_config()

    return ResearchConfig(
        project=project,
        papers=papers,
        research_context=context,
        key_scholars=scholars,
        theories=theories,
        custom_sections=custom_sections,
        dropdowns=dropdowns,
        google_sheets=GoogleSheetsConfig(),
        api=api,
    )


# ─── CODE GENERATORS ────────────────────────────────────────


def run_generators(config: ResearchConfig, pipeline_dir: str = ".") -> list[str]:
    """
    Run all code generators to produce pipeline files.

    Returns list of generated file paths.
    """
    from codegen.generate_extraction_prompt import generate as gen_extraction_prompt
    from codegen.generate_schemas import generate as gen_schemas
    from codegen.generate_config import generate as gen_config
    from codegen.generate_discovery_config import generate as gen_discovery_config
    from codegen.generate_gap_prompts import generate as gen_gap_prompts

    pipeline_path = Path(pipeline_dir)
    generated = []

    generators = [
        ("extraction_prompt.py", lambda: gen_extraction_prompt(config, str(pipeline_path / "extraction_prompt.py"))),
        ("schemas.py", lambda: gen_schemas(config, str(pipeline_path / "schemas.py"))),
        ("config.py", lambda: gen_config(config, str(pipeline_path / "config.py"))),
        ("discovery_config.py", lambda: gen_discovery_config(config, str(pipeline_path / "discovery_config.py"))),
        ("gap prompts", lambda: gen_gap_prompts(config, str(pipeline_path))),
    ]

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Generating pipeline files...", total=len(generators))

        for name, gen_func in generators:
            progress.update(task, description=f"Generating {name}...")
            try:
                gen_func()
                generated.append(name)
                progress.advance(task)
            except Exception as e:
                console.print(f"  [red]Failed to generate {name}: {e}[/]")
                progress.advance(task)

    return generated


# ─── SHEET CREATION ──────────────────────────────────────────


def _create_sheets(config: ResearchConfig, config_path: str) -> tuple[str, str]:
    """Create both Google Sheets and update config. Returns (main_id, auto_id)."""
    from sheet_factory import create_main_sheet, create_auto_sheet, update_config_sheet_ids

    main_id = ""
    auto_id = ""

    # Main sheet
    console.print()
    if Confirm.ask("Create main extraction sheet?", default=True):
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Creating main sheet...", total=None)
            main_id = create_main_sheet(config)
            progress.stop_task(task)

    # Auto sheet
    if Confirm.ask("Create auto discovery sheet?", default=True):
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Creating auto sheet...", total=None)
            auto_id = create_auto_sheet(config)
            progress.stop_task(task)

    # Update config YAML
    if main_id or auto_id:
        console.print("\n[bold blue]Updating configuration...[/]")
        update_config_sheet_ids(config_path, main_id, auto_id)

    return main_id, auto_id


# ─── LOCAL FOLDERS ───────────────────────────────────────────


def _create_local(pipeline_dir: str) -> list[str]:
    """Create local directory structure."""
    from sheet_factory import create_local_folders

    console.print("\n[bold blue]Creating local folders...[/]")
    return create_local_folders(Path(pipeline_dir))


# ─── DRIVE FOLDERS ───────────────────────────────────────────


def _create_drive(config: ResearchConfig) -> dict:
    """Optionally create Google Drive folder structure."""
    from sheet_factory import create_drive_folders

    if Confirm.ask("\nCreate Google Drive folders?", default=False):
        return create_drive_folders(config)
    return {}


# ─── SUMMARY ────────────────────────────────────────────────


def _show_summary(
    config: ResearchConfig,
    generated: list[str],
    main_id: str = "",
    auto_id: str = "",
    local_folders: list[str] | None = None,
    drive_folders: dict | None = None,
):
    """Display a rich summary panel with results and next steps."""
    console.print()

    # Results table
    table = Table(
        title="Setup Results",
        box=box.DOUBLE,
        border_style="cyan",
        show_lines=True,
    )
    table.add_column("Component", style="bold")
    table.add_column("Status")
    table.add_column("Details", style="dim")

    # Project
    table.add_row(
        "Project",
        "[green]Configured[/]",
        config.project.short_title,
    )

    # Papers
    table.add_row(
        "Papers",
        f"[green]{len(config.papers)} defined[/]",
        ", ".join(p.label for p in config.papers[:5])
        + ("..." if len(config.papers) > 5 else ""),
    )

    # Generated files
    if generated:
        table.add_row(
            "Generated Files",
            f"[green]{len(generated)} files[/]",
            ", ".join(generated),
        )
    else:
        table.add_row("Generated Files", "[yellow]Skipped[/]", "")

    # Main sheet
    if main_id:
        table.add_row(
            "Main Sheet",
            "[green]Created[/]",
            main_id,
        )
    else:
        table.add_row("Main Sheet", "[yellow]Not created[/]", "")

    # Auto sheet
    if auto_id:
        table.add_row(
            "Auto Sheet",
            "[green]Created[/]",
            auto_id,
        )
    else:
        table.add_row("Auto Sheet", "[yellow]Not created[/]", "")

    # Local folders
    if local_folders:
        table.add_row(
            "Local Folders",
            f"[green]{len(local_folders)} dirs[/]",
            ", ".join(Path(f).name for f in local_folders),
        )
    else:
        table.add_row("Local Folders", "[yellow]Not created[/]", "")

    # Drive folders
    if drive_folders:
        table.add_row(
            "Drive Folders",
            f"[green]{len(drive_folders)} dirs[/]",
            ", ".join(drive_folders.keys()),
        )
    else:
        table.add_row("Drive Folders", "[yellow]Not created[/]", "")

    console.print(table)

    # Next steps
    console.print()
    next_steps = Text()
    next_steps.append("NEXT STEPS\n\n", style="bold cyan")

    step_num = 1
    if not generated:
        next_steps.append(
            f"  {step_num}. Run generators: python setup_wizard.py --from-config\n"
        )
        step_num += 1

    if not main_id:
        next_steps.append(
            f"  {step_num}. Create main sheet: python sheet_factory.py --config research_config.yaml\n"
        )
        step_num += 1

    next_steps.append(
        f"  {step_num}. Place PDFs in the Literature Review folder\n"
    )
    step_num += 1
    next_steps.append(
        f"  {step_num}. Run extraction: python main.py\n"
    )
    step_num += 1
    next_steps.append(
        f"  {step_num}. Run discovery: python discover.py\n"
    )

    console.print(Panel(next_steps, border_style="cyan", box=box.DOUBLE))
    console.print()


# ─── CHECK CLIENT SECRET ────────────────────────────────────


def _has_client_secret() -> bool:
    """Check if client_secret.json exists for Google OAuth."""
    from config import CLIENT_SECRET_FILE

    exists = CLIENT_SECRET_FILE.exists()
    if not exists:
        console.print(
            "\n[yellow]client_secret.json not found.[/]\n"
            "  Google Sheets/Drive creation will be skipped.\n"
            "  To enable: download OAuth credentials from Google Cloud Console\n"
            f"  and place at: {CLIENT_SECRET_FILE}\n"
        )
    return exists


# ─── MODE: INTERACTIVE ──────────────────────────────────────


def run_interactive(config_path: str):
    """Full interactive wizard mode."""
    config = collect_interactive_config()

    # Save config
    console.rule("[bold cyan]Saving Configuration", style="cyan")
    console.print()
    save_config(config, config_path)
    console.print(f"  [green]>[/] Saved to {config_path}")
    console.print()

    # Run generators
    console.rule("[bold cyan]Step 8: Generate Pipeline Files", style="cyan")
    console.print()
    generated = run_generators(config, str(PIPELINE_DIR))

    # Sheets and folders
    main_id = ""
    auto_id = ""
    local_folders = None
    drive_folders = None

    console.rule("[bold cyan]Step 9: Infrastructure", style="cyan")

    if _has_client_secret():
        main_id, auto_id = _create_sheets(config, config_path)

    # Local folders
    console.print()
    if Confirm.ask("Create local pipeline folders?", default=True):
        local_folders = _create_local(str(PIPELINE_DIR))

    # Drive folders
    if _has_client_secret():
        drive_folders = _create_drive(config)

    # Summary
    _show_summary(config, generated, main_id, auto_id, local_folders, drive_folders)


# ─── MODE: FROM CONFIG ──────────────────────────────────────


def run_from_config(config_path: str):
    """Load existing config, run generators, optionally create sheets."""
    console.print()
    content = Text()
    content.append("PhD LITERATURE EXTRACTION PIPELINE\n", style=STYLE_TITLE)
    content.append("Setup from Existing Config\n", style=STYLE_ACCENT)
    console.print(Panel(content, border_style="cyan", box=box.DOUBLE))
    console.print()

    # Load config
    console.print(f"[bold blue]Loading {config_path}...[/]")
    try:
        config = load_config(config_path)
    except FileNotFoundError:
        console.print(f"[red]Config file not found: {config_path}[/]")
        console.print("  Run without --from-config for interactive mode.")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Failed to load config: {e}[/]")
        sys.exit(1)

    console.print(f"  [green]>[/] Project: {config.project.title}")
    console.print(f"  [green]>[/] Papers:  {len(config.papers)}")
    console.print(f"  [green]>[/] Custom sections: {len(config.custom_sections)}")
    console.print()

    # Run generators
    console.print("[bold blue]Running code generators...[/]")
    generated = run_generators(config, str(PIPELINE_DIR))
    console.print()

    # Sheets — create if IDs are empty
    main_id = config.google_sheets.spreadsheet_id
    auto_id = config.google_sheets.auto_spreadsheet_id
    local_folders = None
    drive_folders = None

    needs_main = not main_id
    needs_auto = not auto_id

    if (needs_main or needs_auto) and _has_client_secret():
        console.print("[bold blue]Creating missing Google Sheets...[/]")

        if needs_main:
            from sheet_factory import create_main_sheet

            main_id = create_main_sheet(config)

        if needs_auto:
            from sheet_factory import create_auto_sheet

            auto_id = create_auto_sheet(config)

        if main_id or auto_id:
            from sheet_factory import update_config_sheet_ids

            update_config_sheet_ids(config_path, main_id, auto_id)
    elif not needs_main and not needs_auto:
        console.print(
            "[dim]Sheet IDs already set in config — skipping creation.[/]"
        )
    console.print()

    # Local folders
    console.print("[bold blue]Creating local folders...[/]")
    local_folders = _create_local(str(PIPELINE_DIR))

    # Summary
    _show_summary(config, generated, main_id, auto_id, local_folders, drive_folders)


# ─── MODE: GENERATE ONLY ────────────────────────────────────


def run_generate_only(config_path: str):
    """Load config, run generators, print summary. No sheets or folders."""
    console.print()
    content = Text()
    content.append("PhD LITERATURE EXTRACTION PIPELINE\n", style=STYLE_TITLE)
    content.append("Generate Files Only\n", style=STYLE_ACCENT)
    console.print(Panel(content, border_style="cyan", box=box.DOUBLE))
    console.print()

    # Load config
    console.print(f"[bold blue]Loading {config_path}...[/]")
    try:
        config = load_config(config_path)
    except FileNotFoundError:
        console.print(f"[red]Config file not found: {config_path}[/]")
        console.print("  Run without --generate-only for interactive mode.")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Failed to load config: {e}[/]")
        sys.exit(1)

    console.print(f"  [green]>[/] Project: {config.project.title}")
    console.print()

    # Run generators
    console.print("[bold blue]Running code generators...[/]")
    generated = run_generators(config, str(PIPELINE_DIR))

    # Summary (no sheets or folders)
    _show_summary(config, generated)


# ─── CLI ENTRY POINT ────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="PhD Literature Pipeline — Setup Wizard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python setup_wizard.py                  # Interactive mode\n"
            "  python setup_wizard.py --from-config    # From existing YAML\n"
            "  python setup_wizard.py --generate-only  # Files only, no infra\n"
        ),
    )
    parser.add_argument(
        "--from-config",
        action="store_true",
        help="Read existing research_config.yaml instead of interactive prompts",
    )
    parser.add_argument(
        "--generate-only",
        action="store_true",
        help="Generate Python files only (no sheets/folders)",
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to research_config.yaml (default: {DEFAULT_CONFIG_PATH})",
    )

    args = parser.parse_args()

    # Mutually exclusive modes
    if args.from_config and args.generate_only:
        console.print("[red]Cannot use --from-config and --generate-only together.[/]")
        sys.exit(1)

    if args.generate_only:
        run_generate_only(args.config)
    elif args.from_config:
        run_from_config(args.config)
    else:
        run_interactive(args.config)


if __name__ == "__main__":
    main()
