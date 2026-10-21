"""Guards for the UI contract: the shared stylesheets and the rules around them.

`base.html` loads `ui/css/tokens.css` and `ui/css/components.css` through
`{% static %}`. The test storage does not check that a path exists, so a typo there
passes pytest, while the production manifest storage raises on it and every page
returns 500.

Colour values live only in `tokens.css`. The project's templates must not contain a
colour literal, a `<style>` block or a `style=` attribute, and `components.css` must
not contain a colour literal (it reads tokens through `var(--...)`).

The contrast test reads `tokens.css` (light `:root` and the dark
`@media (prefers-color-scheme: dark)` block, where a token that is not redefined keeps
its light value), resolves `var(--...)` aliases, converts OKLCH to sRGB (clipped to
the sRGB gamut) and checks each pair in `CONTRAST_PAIRS` against its WCAG 2.x
threshold in both themes.

Django messages render as the alert component with `message.level_tag` as its
`data-variant`, so `components.css` must keep the `error` alias of `destructive`.
"""

import math
import re
from functools import cache
from pathlib import Path

import pytest
from django.apps import apps
from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import Client

from accounts.models import User

STYLESHEETS = ["ui/css/tokens.css", "ui/css/components.css"]

# The colour part of the /10x-ui literal scan.
COLOUR_LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(|oklch\(")
INLINE_STYLE = re.compile(r"<style| style=")

# Directories inside BASE_DIR that hold copies or third-party code, not project apps.
NOT_PROJECT_DIRS = {".venv", "mutants", "staticfiles"}

# (text or ring token, background token, minimum contrast ratio).
# 4.5:1 for text (WCAG 1.4.3), 3:1 for focus rings and field borders (WCAG 1.4.11).
CONTRAST_PAIRS: list[tuple[str, str, float]] = [
    ("foreground", "background", 4.5),
    ("foreground", "card", 4.5),
    ("foreground", "muted", 4.5),
    ("foreground", "destructive-muted", 4.5),
    ("foreground", "success-muted", 4.5),
    ("foreground", "bubble-assistant", 4.5),
    ("foreground", "bubble-user", 4.5),
    ("primary-foreground", "primary", 4.5),
    ("secondary-foreground", "secondary", 4.5),
    ("muted-foreground", "background", 4.5),
    ("muted-foreground", "card", 4.5),
    ("accent-foreground", "accent", 4.5),
    ("destructive-foreground", "destructive", 4.5),
    ("destructive", "background", 4.5),
    ("destructive", "card", 4.5),
    ("warning-foreground", "warning", 4.5),
    ("success", "background", 4.5),
    ("ring", "background", 3.0),
    ("ring", "card", 3.0),
    ("input", "background", 3.0),
    ("input", "card", 3.0),
]
THEMES = ["light", "dark"]

DARK_BLOCK = re.compile(
    r"@media\s*\(\s*prefers-color-scheme\s*:\s*dark\s*\)\s*\{\s*:root\s*\{(?P<body>[^}]*)\}\s*\}"
)
ROOT_BLOCK = re.compile(r":root\s*\{(?P<body>[^}]*)\}")
DECLARATION = re.compile(r"--(?P<name>[\w-]+)\s*:\s*(?P<value>[^;]+);")
OKLCH_VALUE = re.compile(
    r"oklch\(\s*(?P<l>[\d.]+)\s+(?P<c>[\d.]+)\s+(?P<h>[\d.]+)\s*\)"
)
ALIAS_VALUE = re.compile(r"var\(\s*--(?P<name>[\w-]+)\s*\)")


@pytest.mark.parametrize("path", STYLESHEETS)
def test_stylesheet_is_found_by_static_finders(path: str) -> None:
    assert finders.find(path) is not None


def project_template_files() -> list[Path]:
    """Every file under the `templates/` directory of a project app."""
    base_dir = Path(settings.BASE_DIR).resolve()
    files: list[Path] = []
    for app_config in apps.get_app_configs():
        app_dir = Path(app_config.path).resolve()
        if not app_dir.is_relative_to(base_dir):
            continue
        if app_dir.relative_to(base_dir).parts[0] in NOT_PROJECT_DIRS:
            continue
        templates_dir = app_dir / "templates"
        if templates_dir.is_dir():
            files.extend(
                path for path in sorted(templates_dir.rglob("*")) if path.is_file()
            )
    return files


def test_project_templates_have_no_colours_or_inline_styles() -> None:
    templates = project_template_files()
    assert any(path.name == "base.html" for path in templates), templates

    offenders = [
        f"{path}:{number}: {line.strip()}"
        for path in templates
        for number, line in enumerate(path.read_text().splitlines(), start=1)
        if COLOUR_LITERAL.search(line) or INLINE_STYLE.search(line)
    ]

    assert offenders == []


def test_components_stylesheet_has_no_colour_literals() -> None:
    path = finders.find("ui/css/components.css")
    assert path is not None

    offenders = [
        f"{number}: {line.strip()}"
        for number, line in enumerate(Path(path).read_text().splitlines(), start=1)
        if COLOUR_LITERAL.search(line)
    ]

    assert offenders == []


def declarations(block: str) -> dict[str, str]:
    return {
        match["name"]: match["value"].strip() for match in DECLARATION.finditer(block)
    }


@cache
def theme_tokens() -> dict[str, dict[str, str]]:
    """Raw token values per theme; the dark theme starts from the light one."""
    path = finders.find("ui/css/tokens.css")
    assert path is not None
    css = re.sub(r"/\*.*?\*/", "", Path(path).read_text(), flags=re.DOTALL)

    dark_blocks = DARK_BLOCK.findall(css)
    assert len(dark_blocks) == 1, "expected one dark :root block"
    light_blocks = ROOT_BLOCK.findall(DARK_BLOCK.sub("", css))
    assert len(light_blocks) == 1, "expected one light :root block"

    light = declarations(light_blocks[0])
    return {"light": light, "dark": light | declarations(dark_blocks[0])}


def resolve_oklch(tokens: dict[str, str], name: str) -> tuple[float, float, float]:
    """Follow `var(--...)` aliases to a literal `oklch(L C H)`."""
    seen: list[str] = []
    while name not in seen:
        seen.append(name)
        assert name in tokens, f"--{name} is not defined (via {seen})"
        value = tokens[name]
        if alias := ALIAS_VALUE.fullmatch(value):
            name = alias["name"]
            continue
        literal = OKLCH_VALUE.fullmatch(value)
        assert literal, f"--{name}: {value!r} is neither oklch(L C H) nor var(--...)"
        return float(literal["l"]), float(literal["c"]), float(literal["h"])
    raise AssertionError(f"alias loop: {seen}")


def oklch_to_srgb(
    lightness: float, chroma: float, hue: float
) -> tuple[float, float, float]:
    """OKLCH to gamma-encoded sRGB channels, clipped to [0, 1] (Björn Ottosson's OKLab)."""
    a = chroma * math.cos(math.radians(hue))
    b = chroma * math.sin(math.radians(hue))
    long_ = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
    medium = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
    short = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3
    linear = (
        4.0767416621 * long_ - 3.3077115913 * medium + 0.2309699292 * short,
        -1.2684380046 * long_ + 2.6097574011 * medium - 0.3413193965 * short,
        -0.0041960863 * long_ - 0.7034186147 * medium + 1.7076147010 * short,
    )

    def encode(channel: float) -> float:
        channel = min(1.0, max(0.0, channel))
        if channel <= 0.0031308:
            return 12.92 * channel
        return 1.055 * channel ** (1 / 2.4) - 0.055

    red, green, blue = (encode(channel) for channel in linear)
    return red, green, blue


def relative_luminance(srgb: tuple[float, float, float]) -> float:
    """WCAG 2.x relative luminance of a gamma-encoded sRGB colour."""

    def decode(channel: float) -> float:
        if channel <= 0.04045:
            return channel / 12.92
        return ((channel + 0.055) / 1.055) ** 2.4

    red, green, blue = (decode(channel) for channel in srgb)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(
    first: tuple[float, float, float], second: tuple[float, float, float]
) -> float:
    lighter, darker = sorted(
        (
            relative_luminance(oklch_to_srgb(*first)),
            relative_luminance(oklch_to_srgb(*second)),
        ),
        reverse=True,
    )
    return (lighter + 0.05) / (darker + 0.05)


def test_contrast_ratio_matches_known_wcag_values() -> None:
    white = (1.0, 0.0, 0.0)
    black = (0.0, 0.0, 0.0)

    assert contrast_ratio(white, black) == pytest.approx(21.0)
    assert contrast_ratio(white, white) == pytest.approx(1.0)


@pytest.mark.django_db
def test_error_message_renders_as_the_error_alert_variant(client: Client) -> None:
    """Django's `error` level tag reaches the alert through its `error` alias."""
    user = User.objects.create_user("anna@example.de", "pass-12345-xyz")
    client.force_login(user)

    response = client.post(
        "/conversations/start/", {"topic": "no-such-topic"}, follow=True
    )

    assert '<p class="flash alert" data-variant="error">' in response.content.decode()
    path = finders.find("ui/css/components.css")
    assert path is not None
    assert '.alert[data-variant="error"]' in Path(path).read_text()


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize(
    ("text", "background", "minimum"),
    CONTRAST_PAIRS,
    ids=[f"{text}/{background}" for text, background, _ in CONTRAST_PAIRS],
)
def test_token_pair_meets_wcag_contrast(
    theme: str, text: str, background: str, minimum: float
) -> None:
    tokens = theme_tokens()[theme]

    ratio = contrast_ratio(
        resolve_oklch(tokens, text), resolve_oklch(tokens, background)
    )

    assert ratio >= minimum, f"{theme}: --{text} on --{background} is {ratio:.2f}:1"
