"""Prompt template management for Morning Drive.

This module provides Jinja2-based prompt templates for all Claude API calls,
along with utilities for rendering and tracking prompts.
"""

from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml
from jinja2 import Environment, FileSystemLoader


# Paths
PROMPTS_DIR = Path(__file__).parent
TEMPLATES_DIR = PROMPTS_DIR / "templates"
DATA_DIR = PROMPTS_DIR / "data"


# Jinja2 Environment (lazy-loaded)
_env: Optional[Environment] = None


def get_prompt_env() -> Environment:
    """Get or create the Jinja2 environment for prompt templates."""
    global _env
    if _env is None:
        _env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=False,  # No HTML escaping for prompts
            trim_blocks=True,
            lstrip_blocks=True,
        )
    return _env


def render_prompt(template_name: str, **context: Any) -> str:
    """Render a prompt template with the given context.

    Args:
        template_name: Name of the template file (e.g., 'script_writer_system.jinja2')
        **context: Template variables

    Returns:
        Rendered prompt string
    """
    env = get_prompt_env()
    template = env.get_template(template_name)
    return template.render(**context)


@lru_cache(maxsize=10)
def load_yaml_data(filename: str) -> dict:
    """Load and cache YAML data file.

    Args:
        filename: Name of the YAML file in data/ directory

    Returns:
        Parsed YAML data as dict
    """
    filepath = DATA_DIR / filename
    with open(filepath, "r") as f:
        return yaml.safe_load(f)


def get_writing_styles() -> dict:
    """Get all writing style configurations."""
    return load_yaml_data("writing_styles.yaml")


def get_writing_style(style_key: str) -> dict:
    """Get a specific writing style configuration.

    Args:
        style_key: Style identifier (e.g., 'good_morning_america')

    Returns:
        Style config with 'name' and 'prompt' keys
    """
    styles = get_writing_styles()
    default_key = styles.get("default", "good_morning_america")
    return styles.get(style_key) or styles.get(default_key)


def get_segment_display_names() -> dict:
    """Get segment type to display name mapping."""
    return load_yaml_data("segment_display_names.yaml")


class PromptRenderer:
    """Helper class to render prompts and track rendered content for storage.

    Usage:
        renderer = PromptRenderer()
        system_prompt = renderer.render("script_writer_system.jinja2", "system_prompt", **context)
        user_prompt = renderer.render("script_writer_user.jinja2", "user_prompt", **context)

        # Later, save to database
        briefing.rendered_prompts = renderer.get_all_rendered()
    """

    def __init__(self):
        self.rendered_prompts: dict[str, str] = {}

    def render(self, template_name: str, prompt_key: str, **context: Any) -> str:
        """Render a template and store the result.

        Args:
            template_name: Template file name
            prompt_key: Key to store the rendered prompt under
            **context: Template variables

        Returns:
            Rendered prompt string
        """
        rendered = render_prompt(template_name, **context)
        self.rendered_prompts[prompt_key] = rendered
        return rendered

    def add_prompt(self, prompt_key: str, prompt_text: str) -> None:
        """Add a pre-rendered prompt to the collection.

        Args:
            prompt_key: Key to store the prompt under
            prompt_text: The prompt text
        """
        self.rendered_prompts[prompt_key] = prompt_text

    def get_all_rendered(self) -> dict:
        """Get all rendered prompts with metadata.

        Returns:
            Dict suitable for storing in database
        """
        return {
            **self.rendered_prompts,
            "rendered_at": datetime.now().isoformat(),
        }
