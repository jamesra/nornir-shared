'''
Created on Aug 30, 2013

@author: u0490822
'''

from ez_setup import use_setuptools


if __name__ == '__main__':
    use_setuptools()

    from setuptools import setup, find_packages

    packages = find_packages()

    install_requires = ["six"]

    classifiers = ['Programming Language :: Python :: 3.4',
                   'Programming Language :: Python :: 2.7']

    #Starting with 1.3.4 Image Magick 7 is required

    setup(name='nornir_shared',
          zip_safe=True,
          classifiers=classifiers,
          version='1.3.4',
          description="Shared routines for Nornir python packages and scripts",
          author="James Anderson",
          author_email="James.R.Anderson@utah.edu",
          url="https://github.com/jamesra/nornir-shared",
          packages=packages,
          install_requires=install_requires,
          test_suite='test')
