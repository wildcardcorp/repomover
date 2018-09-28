import os

from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, 'README.md')) as f:
    README = f.read()
with open(os.path.join(here, 'CHANGES.txt')) as f:
    CHANGES = f.read()

# see requirements.txt for requirements
requires = [
    'stashy',
    'gitpython',
]

tests_require = [
]

setup(name='repomover',
      version='1.0.0.dev0',
      description='move repositories from one management system to another',
      long_description=README + '\n\n' + CHANGES,
      classifiers=[
          "Programming Language :: Python",
          "Programming Language :: Python :: 3.6",
      ],
      author='Wildcard Corp.',
      author_email='support@wildcardcorp.com',
      keywords='git repository',
      packages=find_packages(),
      include_package_data=True,
      zip_safe=False,
      extras_require={
          'testing': tests_require,
      },
      install_requires=requires,
      entry_points={
          'console_scripts': [
              'repomover=repomover:main',
          ],
      })
