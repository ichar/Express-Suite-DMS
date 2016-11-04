##############################################################################
#
# Copyright (c) 2001 Zope Corporation and Contributors. All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.0 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################
"""
Virtual container for ZSQLCatalog indexes.
$Id: ZSQLCatalogIndexes.py 2008-04-15 12:00:00 $

*** Checked 17/10/2008 ***

"""
#import ExtensionClass

from Acquisition import Implicit, aq_parent, aq_self
from Globals import DTMLFile, InitializeClass
from AccessControl.SecurityInfo import ClassSecurityInfo
from AccessControl.Permissions import manage_zcatalog_indexes
#from OFS.PropertyManager import PropertyManager
from OFS.Folder import Folder
from OFS.ObjectManager import IFAwareObjectManager
from OFS.SimpleItem import SimpleItem

from Catalog import CatalogSearchArgumentsMap
import SQLParser

_marker = []

# Index Properties mapping: <key> : ( <title>, <visible>, <sorting> )
# -------------------------------------------------------------------
default_properties = { \
    'getId'          : ( 'Name'             , 1,  1, ),
    'Column_name'    : ( 'Column Name'      , 0,  2, ),
    'Table'          : ( 'Table'            , 1,  3, ),
    'Key_name'       : ( 'Key'              , 0,  4, ),
    'getSize'        : ( '# distinct values', 0,  5, ),
    'typ'            : ( 'Type'             , 1,  6, ),
    'spec'           : ( 'SQL field type'   , 0,  7, ),
    'insertPattern'  : ( 'Insert pattern'   , 0,  8, ),
    'updatePattern'  : ( 'Update pattern'   , 0,  9, ),
    'Null'           : ( 'Null'             , 0, 10, ),
    'Non_unique'     : ( 'Non unique'       , 0, 11, ),
    'Index_type'     : ( 'Index type'       , 1, 12, ),
    'Collation'      : ( 'Collation'        , 0, 14, ),
    'Cardinality'    : ( 'Cardinality'      , 1, 15, ),
}

TITLE   = 0
VISIBLE = 1
SORTING = 2

def propertyIds( visible=None ):
    keys = default_properties.items()
    keys.sort( lambda x, y, SORTING=SORTING: cmp(x[1][SORTING], y[1][SORTING]) )
    keys = [ x[0] for x in keys if not visible or x[1][VISIBLE] ]
    return [ {'name':x, 'title':default_properties[x][TITLE]} for x in keys ]

### SQL Querier ###

def run( context, action, max_rows=1000, mode=None, no_raise=None, no_action=None, clear=None, **kw ):
    if None in ( context, action, ):
        return None
    return aq_parent(context).run( action, max_rows, mode, \
        no_raise, no_action, clear, \
        **kw
        )

def view( context, action, **kw ):
    method = getattr( SQLParser, action, None )
    if method is None:
        return None
    return apply( method, ( aq_parent(context), ), kw )


class ZSQLIndex( SimpleItem ): #, PropertyManager
    """ Abstract 'index' class (not persistent) """
    #__allow_access_to_unprotected_subobjects__=1

    meta_type='SQLIndex'

    __ac_permissions__=( \
        ( manage_zcatalog_indexes,
          ['manage_main', 'manage_browse', 'manage_workspace'],
          ['Anonymous', 'Manager'] ),
        )

    #_properties=()

    manage = manage_main = DTMLFile( 'dtml/manageIndex', globals() )
    manage_browse = DTMLFile('dtml/browseIndex', globals())

    manage_main._setName( 'manage_main' )
    manage_workspace = manage_main

    manage_options = ( \
                       { 'label' : 'Settings', 'action' : 'manage_main'   },
                       { 'label' : 'Browse',   'action' : 'manage_browse' },
                     ) #+ PropertyManager.manage_options

    def __init__( self, id, typ, spec, extension, props, caller ):
        """ Initialize attributes
        """
        for x in props.keys():
            setattr(self, x, props[x])
        self.id = id
        self.table = props['Table']
        self.typ = typ
        self.spec = spec
        self.extension = extension
        self.caller = caller

    def getProperty( self, name, default=None ):
        """ Returns property value """
        x = getattr(self, name, default)
        if callable(x): x = x()
        return x

    def getId( self ):
        """ Returns the 'index' id """
        return self.id

    def getSize( self, distinct='distinct' ):
        """ Returns object's size (count of records) """
        rs = run( aq_self(self.caller), 'indexSize', table=self.table, key=self.id, distinct=distinct, \
                  mode='recordset' )
        return rs[0][0]

    def numObjects( self ):
        """ Returns number of indexed objects (collation of the index) """
        return self.getProperty( 'Collation' )

    def insertPattern( self ):
        return aq_parent(aq_self(self.caller)).getInsertPattern( self.table )

    def updatePattern( self ):
        return aq_parent(aq_self(self.caller)).getUpdatePattern( self.id )

    def propertyValues( self ):
        """ Index property values list """
        res = []
        for x in propertyIds():
            value = { 'value' : self.getProperty(x['name']) }
            value.update( x )
            res.append( value )
        return res

    def itemValues( self, REQUEST, sort_by_path=None, distinct=None, sort_limit=None, sort_offset=None, **kw ):
        """ Index values list """
        catalog = aq_parent(aq_self(self.caller))._catalog
        request = CatalogSearchArgumentsMap(REQUEST, kw)

        query = []
        for k in ( 'path', 'meta_type', ):
            idx = catalog._apply_index( k, request )
            if not idx: continue
            query.append( idx )
        
        return view( aq_self(self.caller), 'index', key=self.id, \
                     query=query, sort_by_path=sort_by_path, distinct=distinct, \
                     limit=sort_limit, offset=sort_offset, \
                     )

    indexSize = getSize


class ZSQLCatalogIndexes( IFAwareObjectManager, Folder, Implicit ):
    """
    ZSQLCatalog Indexes.

    A mapping object, responding to getattr requests by looking up
    the requested indexes in an object manager.
    """

    # The interfaces we want to show up in our object manager
    _product_interfaces = () #( PluggableIndexInterface, IPluggableIndex )

    meta_type = "ZSQLCatalogIndex"
    manage_options = ()

    security = ClassSecurityInfo()

    security.declareObjectProtected(manage_zcatalog_indexes)
    security.setPermissionDefault(manage_zcatalog_indexes, ('Manager',))
    #security.declareProtected(manage_zcatalog_indexes, 'addIndexForm')
    #addIndexForm= DTMLFile('dtml/addIndexForm',globals())

    # You no longer manage the Indexes here, they are managed from ZSQLCatalog
    def manage_main( self, REQUEST, RESPONSE ):
        """Redirect to the parent where the management screen now lives"""
        RESPONSE.redirect('../manage_catalogIndexes')

    def _getItems( self, key=None ):
        indexes = run( self, 'indexTables', key=key, mode='recordset' )
        if not indexes:
            return None

        obs = []
        for id, table, typ, spec, extension in indexes:
            indexes = run( self, 'indexItems', table=table, key=id, mode='records' )
            if indexes:
                obs.append( ZSQLIndex( id, typ, spec, extension, indexes[0], self ) )

        if key: return obs[0]
        return obs

    def _getOb( self, id, default=_marker ):
        #indexes = self.aq_parent._catalog.indexes
        #if not indexes.get(id, None):
        #    raise AttributeError
        return self._getItems( id )

    manage_workspace = manage_main
    #
    #   Object managed methods =====================================================================================
    #
    security.declareProtected(manage_zcatalog_indexes, 'objectItems')
    def objectItems( self, desc=None ):
        try:
            items = self._getItems()
            if desc:
                return ( propertyIds( visible=1 ), items )
            return items
        except:
            return ( 0, [] )

    security.declareProtected(manage_zcatalog_indexes, 'objectIds')
    def objectIds( self, spec=None ):
        items = self._getItems()
        return [ x.getId() for x in items ]

    def filtered_meta_types( self ):
        return None
    """
    # base accessors loop back through our dictionary interface
    def _setOb( self, id, object ):
        #indexes = self.aq_parent._catalog.indexes
        #indexes[id] = object
        #self.aq_parent._indexes = indexes
        #self.aq_parent._p_changed = 1
        pass

    def _delOb( self, id ):
        #indexes = self.aq_parent._catalog.indexes
        #del indexes[id]
        #self.aq_parent._indexes = indexes
        #self.aq_parent._p_changed = 1
        pass

    def _setObject( self, id, object, roles=None, user=None, set_owner=1 ):
        pass
    """
    #
    #   Traversal ==================================================================================================
    #
    def __bobo_traverse__( self, REQUEST, name ):
        if name in ( 'manage_workspace', ):
            return getattr(self, name)
        o = self._getOb( name )
        return o.__of__(self)

InitializeClass(ZSQLCatalogIndexes)
