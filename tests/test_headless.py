"""Pin ``nornir_shared.headless.is_headless`` (env flag plus the non-Windows ``DISPLAY`` rule)."""

from __future__ import annotations

import subprocess
import sys

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from nornir_shared.headless import is_headless

_TRUTHY_FLAGS = ("1", "true", "yes", "on")
_FLAG_WORDS = _TRUTHY_FLAGS + ("0", "false", "no", "off", "", "2", "y", "t", "enabled")

# os.environ rejects NUL and lone surrogates.
_ENV_TEXT = st.text(alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"))


@st.composite
def _flag_values(draw) -> str | None:
    """``NORNIR_HEADLESS`` values: known words with case/whitespace noise, arbitrary text, or unset."""
    kind = draw(st.sampled_from(("word", "text", "unset")))
    if kind == "unset":
        return None
    if kind == "text":
        return draw(_ENV_TEXT)
    word = draw(st.sampled_from(_FLAG_WORDS))
    if draw(st.booleans()):
        word = word.upper()
    return draw(st.sampled_from(("", " ", "\t"))) + word + draw(st.sampled_from(("", " ", "\n")))


_DISPLAY_VALUES = st.one_of(st.none(), st.just(""), st.just(":0"), _ENV_TEXT.filter(bool))
_PLATFORMS = st.sampled_from(("win32", "linux", "darwin", "cygwin"))


def _expected(flag: str | None, display: str | None, platform: str) -> bool:
    if flag is not None and flag.strip().lower() in _TRUTHY_FLAGS:
        return True
    return platform != "win32" and not display


@given(flag=_flag_values(), display=_DISPLAY_VALUES, platform=_PLATFORMS)
@example(flag=" TRUE ", display=":0", platform="win32")
@example(flag="0", display=None, platform="linux")
@example(flag="off", display="", platform="linux")
@example(flag="0", display=":0", platform="linux")
@example(flag=None, display=None, platform="win32")
def test_is_headless_matches_env_and_display_rules(flag: str | None, display: str | None, platform: str) -> None:
    """Truthy ``NORNIR_HEADLESS`` wins; otherwise headless means non-Windows without a ``DISPLAY``."""
    with pytest.MonkeyPatch.context() as mp:
        for name, value in (("NORNIR_HEADLESS", flag), ("DISPLAY", display)):
            if value is None:
                mp.delenv(name, raising=False)
            else:
                mp.setenv(name, value)
        mp.setattr(sys, "platform", platform)
        assert is_headless() is _expected(flag, display, platform)


def test_import_does_not_load_plotting_or_gpu_stack() -> None:
    """Pytest hooks import this module at startup; it must not pull in matplotlib or CuPy."""
    code = (
        "import sys, nornir_shared.headless\n"
        "print(','.join(m for m in ('matplotlib', 'cupy', 'nornir_imageregistration') if m in sys.modules))\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == ""
