##############################################################################
#
# Copyright (c) 2005 Zope Corporation and Contributors. All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################
"""
ZSQLCatalog z3 interfaces.
$Id: ZSQLCatalog.py 2008-04-15 12:00:00 $

*** Checked 01/06/2008 ***

"""
from zope.interface import Interface


class IZSQLCatalog( Interface ):
    """
        ZSQLCatalog object.

        A ZSQLCatalog contains arbitrary index like references to Zope objects.  
        ZSQLCatalog's can index object attribute using a set of predefined index types.
    """

    def catalog_object( obj, uid, idxs=None, update_metadata=1 ):
        """
            Catalogs the object 'obj' with the unique identifier 'uid'.
            The uid must be a physical path, either absolute or relative to the catalog. If provided, idxs specifies the names of indexes to update.

            If update_metadata is specified (the default), the object's metadata is updated. If it is not, the metadata is left untouched.
            This flag has no effect if the object is not yet cataloged (metadata is always added for new objects).
        """

    def uncatalog_object( uid ):
        """
            Uncatalogs the object with the unique identifier 'uid'.
            The uid must be a physical path, either absolute or relative to the catalog.
        """

    def uniqueValuesFor( name ):
        """
            Returns the unique values for a given FieldIndex named 'name'
        """

    def getpath( rid ):
        """
            Returns the path to a cataloged object given a 'data_record_id_'
        """

    def getrid( path ):
        """
            Returns the 'data_record_id_' to a cataloged object given a path
        """

    def getobject( rid, REQUEST=None ):
        """
            Returns a cataloged object given a 'data_record_id_'
        """

    def schema():
        """
            Get the meta-data schema.
            Returns a sequence of names that correspond to columns in the meta-data table.
        """

    def indexes():
        """
            Returns a sequence of names that correspond to indexes.
        """

    def index_objects():
        """
            Returns a sequence of actual index objects.
            NOTE: This returns unwrapped indexes! You should probably use getIndexObjects instead. Some indexes expect to be wrapped.
        """

    def getIndexObjects():
        """
            Returns a list of acquisition wrapped index objects
        """

    def searchResults( REQUEST=None, **kw ):
        """
            Search the catalog.
        """

    def __call__( REQUEST=None, **kw ):
        """
            Search the catalog, the same way as 'searchResults'.
        """

    def search( query_request, sort_index=None, reverse=0, limit=None, merge=1 ):
        """
            Programmatic search interface, use for searching the catalog from scripts.
        """

    def refreshCatalog(clear=0, pghandler=None):
        """
            Reindex every object we can find, removing the unreachable ones from the index.
        """

    def reindexIndex(name, REQUEST, pghandler=None):
        """
            Reindex a single index.
        """
