import sys
import logging
sys.stdout.reconfigure(encoding="utf-8")

from rich.console import Console
from rich.markdown import Markdown
from rich.rule import Rule
from src.jira_analyser import ask, get_all_fields
from src.colors import ColorFormatter
from src import config

console = Console()


def display_token_usage(summary: dict) -> None:
    calls = summary.get("calls", [])
    if not any(c["input"] + c["output"] > 0 for c in calls):
        return  # provider didn't return usage data — skip silently
    console.print()
    console.print("[dim]── Token Usage ──────────────────────────────[/]")
    for c in calls:
        console.print(
            f"  [dim]{c['call']:<22}[/]  "
            f"in [cyan]{c['input']:>5}[/]  out [cyan]{c['output']:>5}[/]"
        )
    console.print(
        f"  [dim]{'TOTAL':<22}[/]  "
        f"in [bold cyan]{summary['total_input']:>5}[/]  "
        f"out [bold cyan]{summary['total_output']:>5}[/]  "
        f"([bold]{summary['total']:>6}[/] total)"
    )
    console.print("[dim]────────────────────────────────────────────[/]")


def create_jw_banner(banner="Jira Whisperer", sub_text=""):
    from pyfiglet import Figlet

    f_small = Figlet(font="slant")  # more compact
    console.print(f_small.renderText(banner))
    console.print((sub_text))




handler = logging.StreamHandler()
handler.setFormatter(ColorFormatter(
    fmt="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
))
logging.basicConfig(level=logging.INFO, handlers=[handler])

BORDER_UP = """
[bold yellow]╔═════════════════════════════════════════════════════════════════════════╗[/]\n
"""



BORDER_DWN = """
[bold yellow]╚═════════════════════════════════════════════════════════════════════════╝[/]\n
"""

HELP = """
## Example Questions

- Show all Blocker and Critical bugs still unresolved in project MYAPP
- Which stories in Sprint 42 are still In Progress with less than 2 days left?
- List issues that have been sitting in QA for more than 5 days
- How many bugs were opened vs resolved this week in project MYAPP?
- Who has more than 5 open issues assigned to them in the current sprint?
- Show unresolved issues by priority in project CORE as a bar chart
- List everything assigned to john.doe that has not moved in the last 5 days

## Commands

| Command        | Description                                      |
|----------------|--------------------------------------------------|
| `jw help`      | Show this message                                |
| `jw history`   | Show question history                            |
| `jw fields`    | List all custom fields from your Jira instance   |
| `jw quit`      | Exit                                             |
"""


def repl():
    console.print(BORDER_UP)
    if config.LLM_PROVIDER == "anthropic":
        provider_info = f"anthropic  /  {config.ANTHROPIC_MODEL}"
    else:
        provider_info = f"huggingface  /  {config.HF_MODEL}"
    BANNER = create_jw_banner(
        banner="Jira Whisperer",
        sub_text=f"Ask anything about your Jira project in plain English\n\n[dim]LLM provider:[/] [cyan]{provider_info}[/]\n",
    )
    console.print(BORDER_DWN)

    history: list[str] = []

    while True:
        try:
            user_input = console.input(r"[bold cyan]\[jwhisper]#[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n\n[dim]Goodbye.[/]")
            break

        if not user_input:
            continue

        if user_input.lower() in ("jw quit", "jw exit", "jw q"):
            console.print("\n[dim]Goodbye.[/]")
            break

        if user_input.lower() in ("jw help", "jw ?", "?"):
            console.print(Markdown(HELP))
            continue

        if user_input.lower() == "jw history":
            if not history:
                console.print("  [dim]No questions asked yet.[/]")
            else:
                for i, q in enumerate(history, 1):
                    console.print(f"  [dim]{i}.[/] {q}")
            continue

        if user_input.lower() == "jw fields":
            console.print("\n[bold cyan]Fetching custom fields from Jira...[/]\n")
            try:
                _, custom_fields = get_all_fields()
                rows = sorted(custom_fields.items(), key=lambda x: x[1])
                console.print(f"  [dim]{'Field ID':<30} Display Name[/]")
                console.print(f"  [dim]{'─' * 30} {'─' * 40}[/]")
                for fid, name in rows:
                    console.print(f"  [cyan]{fid:<30}[/] {name}")
                console.print(f"\n  [dim]{len(rows)} custom fields total.[/]")
                console.print(
                    "\n  [dim]To track a field, add its display name (lowercase) to[/] "
                    "[bold]_SEMANTIC_FIELD_VARIANTS[/] [dim]in src/jira_analyser.py[/]\n"
                )
            except Exception as e:
                console.print(f"[bold red]Error:[/] {e}")
            continue

        history.append(user_input)

        console.print()
        try:
            answer, token_summary = ask(user_input)
            console.print(Rule(style="dim cyan"))
            console.print(Markdown(answer))
            console.print(Rule(style="dim cyan"))
            display_token_usage(token_summary)
        except KeyboardInterrupt:
            console.print("\n[dim][interrupted][/]")
        except Exception as e:
            import traceback
            console.print(f"[bold red]Error:[/] {e}")
            console.print(traceback.format_exc())

        console.print()


if __name__ == "__main__":
    repl()
