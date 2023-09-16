'''
 
Nornir Shared Package
---------------------

Functions shared across the various Nornir and connectomics packages live in this module.

checksum
========

.. automodule:: nornir_shared.checksum
   :members:

emaillib
========

.. automodule:: nornir_shared.emaillib
   :members:
   

 
'''

__all__ = ['argparse_helpers', 'checksum', 'files', 'histogram', 'images', 'mathhelper', 'misc', 'parallel', 'plot',
           'processoutputinterceptor', 'reflection', 'prettyoutput', 'tasktimer']

#
#
# .. automodule:: nornir_shared.checksum
# .. automodule:: nornir_shared.files
# .. automodule:: nornir_shared.histogram
# .. automodule:: nornir_shared.images
# .. automodule:: nornir_shared.mathhelper
# .. automodule:: nornir_shared.misc
# .. automodule:: nornir_shared.parallel
# .. automodule:: nornir_shared.plot
# .. automodule:: nornir_shared.prettyoutput
# .. automodule:: nornir_shared.processoutputinterceptor
# .. automodule:: nornir_shared.reflection
# .. automodule:: nornir_shared.tasktimer
# .. automodule:: nornir_shared.argparse_helpers


import nornir_shared.checksum as checksum
import nornir_shared.files as files
import nornir_shared.histogram as histogram
import nornir_shared.mathhelper as mathhelper
import nornir_shared.plot as plot
import nornir_shared.prettyoutput as prettyoutput
import nornir_shared.tasktimer as tasktimer
from nornir_shared.mathhelper import NearestPowerOfTwo, ListMedian, RoundingPrecision

def find_first_match(collection, attributes: dict[str, any]) -> object | None:
    '''
    Returns the first object in the collection whose attributes match the values in the attribute dictionary
    '''
    #return next((item for item in collection if all(attr in item and item[attr] == attributes[attr] for attr in attributes)), None)
    assert(collection is not None)
    try:
        return next(filter(lambda item: (all(attr in item and item[attr] == attributes[attr]) for attr in attributes), collection))
    except StopIteration:
        return None
