"""Guards for the UI contract: the shared stylesheets and the rules around them.

`base.html` loads `ui/css/tokens.css` and `ui/css/components.css` through
`{% static %}`. The test storage does not check that a path exists, so a typo there
passes pytest, while the production manifest storage raises on it and every page
returns 500.
"""

import pytest
from django.contrib.staticfiles import finders

STYLESHEETS = ["ui/css/tokens.css", "ui/css/components.css"]


@pytest.mark.parametrize("path", STYLESHEETS)
def test_stylesheet_is_found_by_static_finders(path: str) -> None:
    assert finders.find(path) is not None
