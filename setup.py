'''
Created on Aug 30, 2013

@author: u0490822
'''



from ez_setup import use_setuptools
from setuptools import setup, find_packages
import sys

use_setuptools()

setup(name='nornir_shared',
      version='1.0',
      description="Shared routines for Nornir python packages and scripts",
      author="James Anderson",
      author_email="James.R.Anderson@utah.edu",
      url="https://github.com/jamesra/nornir-shared",
      packages=["nornir_shared"],
      test_suite='test')
