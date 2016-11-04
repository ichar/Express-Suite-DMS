##############################################################################
#
# Copyright (c) 2001 Zope Corporation and Contributors. All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################
""" Utility functions.

$Id: utils.py 40138 2005-11-15 17:47:37Z jens $

*** Checked 01/06/2008 ***

"""
import re
from copy import deepcopy

from types import ClassType, InstanceType, MethodType, DictType, TupleType, ListType, UnicodeType, \
     StringType, IntType, FloatType, LongType, ComplexType, BooleanType, StringTypes

from ZPublisher.HTTPRequest import record as _zpub_record

SequenceTypes = ( TupleType, ListType )
MappingTypes = ( DictType, _zpub_record )


def uniqueValues( sequence ):
    """
        Removes duplicates from the list, preserving order of the items.

        Arguments:

            'sequence' -- Python list.

        Result:

            Python list.
    """
    if type(sequence) not in SequenceTypes:
        sequence = [ sequence ]
    return [ sequence[i] for i in range(len(sequence)) if sequence[i] not in sequence[:i] ]

def uniqueItems( mapping ):
    """
        Removes empty dictionary items.

        Arguments:

            'mapping' -- Python dictionary.

        Result:

            Python dictionary.
    """
    if type(mapping) not in MappingTypes:
        return mapping
    for key in tuple(mapping.keys()):
        if mapping[key]: continue
        del mapping[key]
    return mapping
