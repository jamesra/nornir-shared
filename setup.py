'''
Created on Aug 30, 2013

@author: u0490822
'''


from distutils.core import setup

setup(name='nornir-shared',
      version='1.0',
      description="Shared routines for Nornir python packages and scripts",
      author="James Anderson",
      author_email="James.R.Anderson@utah.edu",
      url="http://connectomes.utah.edu/",
      packages=["nornir_shared"],
      package_dir={'nornir_shared' : 'src' })
