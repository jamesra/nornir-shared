"""Regression tests for ImageMagick identify helpers in ``nornir_shared.images``."""

from __future__ import annotations

import subprocess
import unittest
from unittest import mock

from nornir_shared import images


class _FakeProc:
    def __init__(self, stdout: bytes) -> None:
        self._stdout = stdout

    def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, b""


class TestMagickIdentifyHelpers(unittest.TestCase):
    def test_get_image_bpp_parses_stdout(self) -> None:
        with mock.patch("os.path.exists", return_value=True), mock.patch(
            "nornir_shared.images._magick_identify_stdout",
            return_value=b"16\n",
        ) as mocked:
            self.assertEqual(images.GetImageBpp("/tmp/a.png"), 16)
        mocked.assert_called_once_with("/tmp/a.png", '-format "%z" -verbose')

    def test_get_image_colorspace_parses_line(self) -> None:
        stdout = b"colorspace:sRGB\n"
        with mock.patch(
            "nornir_shared.images._magick_identify_stdout",
            return_value=stdout,
        ):
            self.assertEqual(images.GetImageColorspace("/tmp/a.png"), "sRGB")

    def test_get_image_stats_parses_fields(self) -> None:
        stdout = (
            b"min:(0)\nmean:(128)\nmax:(255)\nstandard deviation:(12.5)\n"
        )
        with mock.patch(
            "nornir_shared.images._magick_identify_stdout",
            return_value=stdout,
        ):
            min_v, mean_v, max_v, std_v = images.GetImageStats("/tmp/a.png")
        self.assertEqual((min_v, mean_v, max_v, std_v), (0.0, 128.0, 255.0, 12.5))

    def test_magick_identify_stdout_uses_shell_command(self) -> None:
        with mock.patch("nornir_shared.images.subprocess.Popen") as popen:
            popen.return_value = _FakeProc(b"ok")
            out = images._magick_identify_stdout("/tmp/sp ace.png", "-verbose")
        self.assertEqual(out, b"ok")
        popen.assert_called_once_with(
            'magick identify -verbose "/tmp/sp ace.png" && exit',
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def test_identify_image_builds_same_verbose_command(self) -> None:
        sentinel = mock.Mock()
        with (
            mock.patch("nornir_shared.images.subprocess.Popen", return_value=sentinel) as popen,
            mock.patch(
                "nornir_shared.images.processoutputinterceptor.IdentifyOutputInterceptor"
            ) as interceptor_cls,
        ):
            interceptor_cls.Intercept = mock.Mock()
            interceptor_cls.return_value = mock.sentinel.interceptor
            result = images.IdentifyImage("/tmp/sp ace.png")
        self.assertIs(result, mock.sentinel.interceptor)
        popen.assert_called_once_with(
            'magick identify -verbose "/tmp/sp ace.png" && exit',
            shell=True,
            stdout=subprocess.PIPE,
        )


if __name__ == "__main__":
    unittest.main()
