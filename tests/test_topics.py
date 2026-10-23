"""Guards for the topic list and the topic icons.

Every topic needs the card fields (`name`, `subtitle`, `category`, `icon`), a
category from `CATEGORIES` and an icon template that exists. Icons are vendored
Tabler SVGs in `accounts/templates/ui/icons/` (see the README there); each one must
keep the unified `<svg>` root, and no icon may be left without a user.
"""

import re
from pathlib import Path

import pytest
from django.apps import apps
from django.template import TemplateDoesNotExist
from django.template.loader import get_template

from conversations.topics import (
    CATEGORIES,
    TOPICS,
    Category,
    Topic,
    topics_by_category,
)
from tests.test_ui import COLOUR_LITERAL

ICONS_DIR = Path(apps.get_app_config("accounts").path) / "templates" / "ui" / "icons"

# Icons used outside the topic cards (the "Surprise me" button).
NON_TOPIC_ICONS = {"arrows-shuffle"}

SVG_ROOT = re.compile(r"<svg\b[^>]*>")
REQUIRED_ROOT_ATTRIBUTES = [
    'aria-hidden="true"',
    'stroke="currentColor"',
    'stroke-width="2"',
]


def icon_files() -> list[Path]:
    return sorted(ICONS_DIR.glob("*.svg"))


@pytest.mark.parametrize("topic", TOPICS, ids=lambda topic: topic.key)
def test_topic_has_card_fields(topic: Topic) -> None:
    missing = [
        field
        for field in ("name", "subtitle", "category", "icon")
        if not getattr(topic, field)
    ]

    assert missing == [], f"topic {topic.key!r} has empty {missing}"


def test_topic_categories_are_known() -> None:
    known = {category.key for category in CATEGORIES}

    unknown = {
        topic.key: topic.category for topic in TOPICS if topic.category not in known
    }

    assert unknown == {}


def test_category_keys_are_unique() -> None:
    keys = [category.key for category in CATEGORIES]

    assert len(keys) == len(set(keys)), keys


def test_every_category_has_a_topic() -> None:
    used = {topic.category for topic in TOPICS}

    empty = [category.key for category in CATEGORIES if category.key not in used]

    assert empty == []


@pytest.mark.parametrize("topic", TOPICS, ids=lambda topic: topic.key)
def test_topic_icon_template_exists(topic: Topic) -> None:
    try:
        get_template(topic.icon_template)
    except TemplateDoesNotExist:
        pytest.fail(
            f"topic {topic.key!r}: icon template {topic.icon_template!r} not found "
            f"in {ICONS_DIR}"
        )


@pytest.mark.parametrize("icon", sorted(NON_TOPIC_ICONS))
def test_non_topic_icon_template_exists(icon: str) -> None:
    template_name = f"ui/icons/{icon}.svg"
    try:
        get_template(template_name)
    except TemplateDoesNotExist:
        pytest.fail(f"icon template {template_name!r} not found in {ICONS_DIR}")


def test_icon_files_keep_the_unified_svg_root() -> None:
    files = icon_files()
    assert files, ICONS_DIR

    offenders: dict[str, list[str]] = {}
    for path in files:
        text = path.read_text()
        roots = SVG_ROOT.findall(text)
        if len(roots) != 1 or not text.lstrip().startswith("<svg"):
            offenders[path.name] = ["not a single <svg> root element"]
            continue
        missing = [attr for attr in REQUIRED_ROOT_ATTRIBUTES if attr not in roots[0]]
        if missing:
            offenders[path.name] = missing

    assert offenders == {}


def test_no_orphan_icon_files() -> None:
    used = {topic.icon for topic in TOPICS} | NON_TOPIC_ICONS

    orphans = [path.name for path in icon_files() if path.stem not in used]

    assert orphans == [], (
        "icon files used by no topic; delete them or add them to NON_TOPIC_ICONS"
    )


def test_topics_by_category_keeps_both_orders() -> None:
    groups = topics_by_category()

    assert [category for category, _ in groups] == list(CATEGORIES)
    for category, topics in groups:
        assert topics == [topic for topic in TOPICS if topic.category == category.key]
    grouped = [topic for _, topics in groups for topic in topics]
    assert sorted(grouped, key=TOPICS.index) == list(TOPICS)


@pytest.mark.parametrize("category", CATEGORIES, ids=lambda category: category.key)
def test_category_key_is_not_a_colour_literal(category: Category) -> None:
    # Category keys may end up in ids and `#fragment` links; `#add` or `#cafe`
    # would trip the colour scan of `tests/test_ui.py`.
    assert not COLOUR_LITERAL.search(f"#{category.key}")
