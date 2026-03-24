import sys
import logging
sys.stdout.reconfigure(encoding="utf-8")

from rich.console import Console
from rich.markdown import Markdown
from rich.rule import Rule
from src.jira_analyser import ask
from src.colors import ColorFormatter

console = Console()


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
BANNER_1 = """
[bold cyan]╔══════════════════════════════════════════════════════╗[/]
[bold cyan]║[/]       [bold white]Jira Whisperer[/]  [yellow]✦[/]  [dim][/]        [bold cyan]║[/]
[bold cyan]║[/]  Ask anything about your Jira project in plain    [bold cyan]║[/]
[bold cyan]║[/]  English — no JQL required.                       [bold cyan]║[/]
[bold cyan]║[/]                                                    [bold cyan]║[/]
[bold cyan]║[/]  Type [bold green]jw help[/] for examples   [bold red]jw quit[/] to exit      [bold cyan]║[/]
[bold cyan]╚══════════════════════════════════════════════════════╝[/]
"""

HELP = """
Examples:
  > Find all transition states of KAFKA-1645 and tabulate time in each status
  > Show all bugs in project MYAPP opened this quarter
  > Which features exceeded 10 days in QA last sprint?
  > Summarise workload distribution for team alpha in Sprint 42
  > List unresolved issues assigned to john.doe@company.com

Commands:
  jw help     Show this message
  jw quit     Exit
  jw history  Show question history
"""


def repl():
    console.print(BORDER_UP)
    BANNER = create_jw_banner(banner="Jira Whisperer",
                       sub_text="Ask anything about your Jira project in plain English\n")
    console.print(BORDER_DWN)

    history: list[str] = []

    while True:
        try:
            user_input = console.input("[bold cyan]\[jwhisper]#[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n\n[dim]Goodbye.[/]")
            break

        if not user_input:
            continue

        if user_input.lower() in ("jw quit", "jw exit", "jw q"):
            console.print("\n[dim]Goodbye.[/]")
            break

        if user_input.lower() in ("jw help", "jw ?"):
            console.print(Markdown(HELP))
            continue

        if user_input.lower() == "jw history":
            if not history:
                console.print("  [dim]No questions asked yet.[/]")
            else:
                for i, q in enumerate(history, 1):
                    console.print(f"  [dim]{i}.[/] {q}")
            continue

        history.append(user_input)

        console.print()
        try:
            answer = ask(user_input)
            console.print(Rule(style="dim cyan"))
            console.print(Markdown(answer))
            console.print(Rule(style="dim cyan"))
        except KeyboardInterrupt:
            console.print("\n[dim][interrupted][/]")
        except Exception as e:
            import traceback
            console.print(f"[bold red]Error:[/] {e}")
            console.print(traceback.format_exc())

        console.print()


if __name__ == "__main__":
    repl()
