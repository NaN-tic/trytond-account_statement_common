#!/usr/bin/env python
from configparser import ConfigParser
from pathlib import Path

from setuptools import setup

MODULE = 'account_statement_common'
ROOT = Path(__file__).parent
config = ConfigParser()
config.read(ROOT / 'tryton.cfg')
info = config['tryton']
version = info['version']
major, minor, _ = version.split('.')
require_version = f'>={major}.{minor},<{major}.{int(minor) + 1}'
prefixes = {'account_code_digits': 'nantic', 'widgets': 'nantic'}
requires = ['trytond' + require_version, 'Unidecode']
for dependency in info['depends'].split():
    if dependency not in {'ir', 'res'}:
        prefix = prefixes.get(dependency, 'trytond')
        requires.append(f'{prefix}_{dependency}{require_version}')

setup(
    name='nantic_' + MODULE,
    version=version,
    description='Shared bank statement management and reconciliation',
    long_description=(ROOT / 'README').read_text(),
    author='NaN·tic',
    author_email='info@nan-tic.com',
    url='https://www.nan-tic.com/',
    license='GPL-3',
    package_dir={'trytond.modules.' + MODULE: '.'},
    packages=['trytond.modules.' + MODULE,
        'trytond.modules.' + MODULE + '.tests'],
    package_data={'trytond.modules.' + MODULE: [
        'tryton.cfg', '*.xml', 'view/*.xml', 'locale/*.po']},
    install_requires=requires,
    entry_points={'trytond.modules': [
        f'{MODULE} = trytond.modules.{MODULE}']},
    zip_safe=False,
    )
