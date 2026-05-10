#!/usr/bin/python3

import asyncio
import os
import re
from typing import Optional, Set

import aiohttp

from github_stats import Stats


################################################################################
# Helper Functions
################################################################################


def env_bool(name: str, default: bool = False) -> bool:
    """
    Read a boolean-like environment variable.
    Accepted truthy values: 1, true, yes, on
    Accepted falsy values: 0, false, no, off
    """
    value = os.getenv(name)

    if value is None:
        return default

    value = value.strip().lower()

    if value in {"1", "true", "yes", "on"}:
        return True

    if value in {"0", "false", "no", "off"}:
        return False

    return default


def env_set(name: str) -> Optional[Set[str]]:
    """
    Read a comma-separated environment variable into a cleaned set.
    """
    value = os.getenv(name)

    if not value:
        return None

    items = {item.strip() for item in value.split(",") if item.strip()}
    return items if items else None


def generate_output_folder() -> None:
    """
    Create the output folder if it does not already exist.
    """
    os.makedirs("generated", exist_ok=True)


def replace_placeholder(output: str, placeholder: str, value: str) -> str:
    """
    Replace a template placeholder safely.
    """
    return re.sub(r"{{\s*" + re.escape(placeholder) + r"\s*}}", value, output)


################################################################################
# Individual Image Generation Functions
################################################################################


async def generate_overview(s: Stats) -> None:
    """
    Generate an SVG badge with summary statistics.

    Important:
    - lines_changed is disabled by default because GitHub's
      /repos/{repo}/stats/contributors endpoint often returns 202 and can make
      GitHub Actions wait for a very long time.
    - Enable it only if you really want it:
      INCLUDE_LINES_CHANGED=true
    """
    with open("templates/overview.svg", "r", encoding="utf-8") as f:
        output = f.read()

    output = replace_placeholder(output, "name", await s.name)
    output = replace_placeholder(output, "stars", f"{await s.stargazers:,}")
    output = replace_placeholder(output, "forks", f"{await s.forks:,}")
    output = replace_placeholder(
        output,
        "contributions",
        f"{await s.total_contributions:,}",
    )

    include_lines_changed = env_bool("INCLUDE_LINES_CHANGED", default=False)

    if include_lines_changed:
        added, deleted = await s.lines_changed
        changed = added + deleted
        output = replace_placeholder(output, "lines_changed", f"{changed:,}")
    else:
        output = replace_placeholder(output, "lines_changed", "N/A")

    include_views = env_bool("INCLUDE_VIEWS", default=True)

    if include_views:
        output = replace_placeholder(output, "views", f"{await s.views:,}")
    else:
        output = replace_placeholder(output, "views", "N/A")

    output = replace_placeholder(output, "repos", f"{len(await s.repos):,}")

    generate_output_folder()

    with open("generated/overview.svg", "w", encoding="utf-8") as f:
        f.write(output)


async def generate_languages(s: Stats) -> None:
    """
    Generate an SVG badge with summary languages used.
    """
    with open("templates/languages.svg", "r", encoding="utf-8") as f:
        output = f.read()

    progress = ""
    lang_list = ""

    sorted_languages = sorted(
        (await s.languages).items(),
        reverse=True,
        key=lambda t: t[1].get("size", 0),
    )

    delay_between = 150

    for i, (lang, data) in enumerate(sorted_languages):
        color = data.get("color") or "#000000"
        prop = data.get("prop", 0)

        progress += (
            f'<span style="background-color: {color};'
            f'width: {prop:0.3f}%;" '
            f'class="progress-item"></span>'
        )

        lang_list += f"""
<li style="animation-delay: {i * delay_between}ms;">
<svg xmlns="http://www.w3.org/2000/svg" class="octicon" style="fill:{color};"
viewBox="0 0 16 16" version="1.1" width="16" height="16"><path
fill-rule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8z"></path></svg>
<span class="lang">{lang}</span>
<span class="percent">{prop:0.2f}%</span>
</li>

"""

    output = replace_placeholder(output, "progress", progress)
    output = replace_placeholder(output, "lang_list", lang_list)

    generate_output_folder()

    with open("generated/languages.svg", "w", encoding="utf-8") as f:
        f.write(output)


################################################################################
# Main Function
################################################################################


async def main() -> None:
    """
    Generate all badges.
    """
    access_token = os.getenv("ACCESS_TOKEN")

    if not access_token:
        raise RuntimeError("A personal access token is required to proceed!")

    user = os.getenv("GITHUB_ACTOR")

    if user is None:
        raise RuntimeError("Environment variable GITHUB_ACTOR must be set.")

    excluded_repos = env_set("EXCLUDED")
    excluded_langs = env_set("EXCLUDED_LANGS")

    ignore_forked_repos = env_bool("EXCLUDE_FORKED_REPOS", default=False)

    timeout = aiohttp.ClientTimeout(total=120)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        s = Stats(
            user,
            access_token,
            session,
            exclude_repos=excluded_repos,
            exclude_langs=excluded_langs,
            ignore_forked_repos=ignore_forked_repos,
        )

        tasks = [generate_overview(s)]

        if env_bool("GENERATE_LANGUAGES", default=True):
            tasks.append(generate_languages(s))

        await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
