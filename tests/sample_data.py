"""The sample picture some tests run on: a guides PSD (the art, five regions and their 走向 lines) and the same art as
a PNG. It is not distributed with the code (the art is not ours to share). Put sample-guides.psd and sample.png in
tests/data, or point STOCKING_SAMPLES at a folder holding them; tests that need them are skipped without.

Any guides PSD the tool exported works as sample-guides.psd for the tests that only need a solved document; the
tests comparing against measured numbers (region names, course angles, render statistics) expect the original.
"""
import os

import pytest

DIR = os.environ.get('STOCKING_SAMPLES') or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
PSD = os.path.join(DIR, 'sample-guides.psd')
PNG = os.path.join(DIR, 'sample.png')
HERE = os.path.isfile(PSD) and os.path.isfile(PNG)
WHY = f'needs the sample picture (sample-guides.psd and sample.png in {DIR}), which is not distributed'

needed = pytest.mark.skipif(not HERE, reason=WHY)


def require():
    """In a fixture: skip the tests using it when the sample is not here."""
    if not HERE:
        pytest.skip(WHY)
