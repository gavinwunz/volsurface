"""Build the VolFoundry C++ extension via pybind11.

Usage:
    python cpp/setup.py build_ext --inplace
"""

import os
import sysconfig
from pathlib import Path

from pybind11.setup_helpers import Pybind11Extension, build_ext

cpp_dir = Path(__file__).resolve().parent
ext_modules = [
    Pybind11Extension(
        "volfoundry.pricers._core",
        [str(cpp_dir / "black_scholes.cpp")],
        cxx_std=17,
        extra_compile_args=["-O3", "-ffast-math"],
    ),
]


def build(setup_kwargs=None):
    """Build hook for pybind11."""
    setup_kwargs = setup_kwargs or {}
    setup_kwargs.setdefault("ext_modules", []).extend(ext_modules)
    setup_kwargs.setdefault("cmdclass", {})["build_ext"] = build_ext
    return setup_kwargs