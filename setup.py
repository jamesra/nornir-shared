"""
Created on Aug 30, 2013

@author: u0490822
"""

from ez_setup import use_setuptools

if __name__ == '__main__':
    use_setuptools()

    from setuptools import setup, find_packages

    packages = find_packages()

    install_requires = ["six"]

    extras_require = {"Curses": ["curses>=2.2"],
                      "pydevd": ["pydevd>=2.9"]}

    classifiers = ['Programming Language :: Python :: 3.7']

    # Starting with 1.3.4 Image Magick 7 is required

    setup(name='nornir_shared',
          zip_safe=True,
          classifiers=classifiers,
          version='1.5.0',
          description="Shared routines for Nornir python packages and scripts",
          author="James Anderson",
          author_email="James.R.Anderson@utah.edu",
          url="https://github.com/jamesra/nornir-shared",
          packages=packages,
          install_requires=install_requires,
          extras_require=extras_require,
          test_suite='test')
