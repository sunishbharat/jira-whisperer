import sys
import logging
sys.stdout.reconfigure(encoding="utf-8")
from src.jira_analyser import ask

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

def main():
    answer = ask("find all the transition states of the issue KAFKA-1645 , tabulate how many days/hrs was spent in each status")
    print(answer)


if __name__ == "__main__":
    main()
