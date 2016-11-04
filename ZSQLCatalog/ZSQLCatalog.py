##############################################################################
#
# Copyright (c) 2001 Zope Corporation and Contributors. All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.0 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE
#
##############################################################################
"""
ZSQLCatalog product.
$Id: ZSQLCatalog.py 2008-04-15 12:00:00 $

*** Checked 24/05/2009 ***

"""
from warnings import warn
import urllib, time, sys, string, logging
from zLOG import LOG, DEBUG, INFO

from Globals import DTMLFile, MessageDialog
#from _mysql_exceptions import OperationalError, NotSupportedError

import Globals
from OFS.Folder import Folder
from OFS.ObjectManager import ObjectManager
from DateTime import DateTime

from ZPublisher import Publish

from AccessControl.SecurityManagement import get_ident
from Acquisition import Implicit, aq_base, aq_get, aq_inner, aq_parent
from DocumentTemplate.DT_Util import InstanceDict, TemplateDict
from DocumentTemplate.DT_Util import Eval
from AccessControl.Permission import name_trans
from AccessControl.DTML import RestrictedDTML
from AccessControl.Permissions import manage_zcatalog_entries, manage_zcatalog_indexes, search_zcatalog
from Globals import Persistent

from ZODB.POSException import ConflictError
import transaction

from Catalog import Catalog, CatalogError
from IZSQLCatalog import IZSQLCatalog as z2IZSQLCatalog
from ProgressHandler import ZLogHandler
from ZSQLCatalogIndexes import ZSQLCatalogIndexes

import SQLParser

from utils import uniqueValues, uniqueItems

from logging import getLogger
logger = getLogger( 'Zope.ZSQLCatalog' )

manage_addZSQLCatalogForm=DTMLFile('dtml/addZSQLCatalog',globals())

default_extension_types = { 'SimpleType':0, 'ListType':1, 'KeywordType':2 }


def manage_addZSQLCatalog( self, id, title, REQUEST=None ):
    """
        Add a ZSQLCatalog object
    """
    id = str(id)
    title = str(title)
    sql_conn = REQUEST.get('sql_conn')
    sql_db_name = REQUEST.get('sql_db_name')
    sql_prefix = REQUEST.get('sql_prefix')
    sql_root = REQUEST.get('sql_root')
    sql_user = REQUEST.get('sql_user')

    try:
        c = ZSQLCatalog( id, title, sql_conn, sql_db_name, sql_prefix, sql_root, sql_user, self )
        self._setObject( id, c )

        self._getOb( id )._catalog.setup()
    except:
        transaction.get().abort()
        raise

    if REQUEST is not None:
        return self.manage_main(self, REQUEST, update_menu=1)


class ZSQLCatalog( Folder, Persistent, Implicit ):
    """
    ZSQLCatalog object.

    A ZSQLCatalog contains arbirary index like references to Zope objects.
    ZSQLCatalog's can index either 'Field' values of object, or 'Text' values.

    ZSQLCatalog does not store references to the objects themselves, but rather to a unique identifier 
    that defines how to get to the object.  In Zope, this unique idenfier is the object's relative path to 
    the ZSQLCatalog (since two Zope object's cannot have the same URL, this is an excellent unique qualifier 
    in Zope).

    Most of the dirty work is done in the _catalog object, which is an instance of the Catalog class.
    """
    __implements__ = z2IZSQLCatalog
    #implements(z3IZSQLCatalog)

    meta_type = "ZSQLCatalog"
    icon = 'misc_/ZSQLCatalog/ZSQLCatalog.gif'

    manage_options = (
        {'label': 'Contents',           # TAB: Contents
         'action': 'manage_main',
         'help': ('OFSP','ObjectManager_Contents.stx')},
        {'label': 'Catalog',            # TAB: Cataloged Objects
         'action': 'manage_catalogView',
         'help':('ZSQLCatalog','ZSQLCatalog_Cataloged-Objects.stx')},
        {'label': 'Properties',         # TAB: Properties
         'action': 'manage_propertiesForm',
         'help': ('OFSP','Properties.stx')},
        {'label': 'Indexes',            # TAB: Indexes
         'action': 'manage_catalogIndexes',
         'help': ('ZSQLCatalog','ZSQLCatalog_Indexes.stx')},
        {'label': 'Metadata',           # TAB: Metadata
         'action': 'manage_catalogSchema',
         'help':('ZSQLCatalog','ZSQLCatalog_MetaData-Table.stx')},
        {'label': 'Find Objects',       # TAB: Find Objects
         'action': 'manage_catalogFind',
         'help':('ZSQLCatalog','ZSQLCatalog_Find-Items-to-ZSQLCatalog.stx')},
        {'label': 'Advanced',           # TAB: Advanced
         'action': 'manage_catalogAdvanced',
         'help':('ZSQLCatalog','ZSQLCatalog_Advanced.stx')},
        {'label': 'Undo',               # TAB: Undo
         'action': 'manage_UndoForm',
         'help': ('OFSP','Undo.stx')},
        {'label': 'Security',           # TAB: Security
         'action': 'manage_access',
         'help': ('OFSP','Security.stx')},
        {'label': 'Ownership',          # TAB: Ownership
         'action': 'manage_owner',
         'help': ('OFSP','Ownership.stx'),}
        )

    __ac_permissions__=(
        ( manage_zcatalog_entries,
         ['manage_catalogObject', 'manage_uncatalogObject',
          'catalog_object', 'uncatalog_object', 'refreshCatalog',

          'manage_catalogView', 'manage_catalogFind',
          'manage_catalogSchema', 'manage_catalogIndexes',
          'manage_catalogAdvanced', 'manage_objectInformation',

          'manage_catalogReindex', 'manage_catalogFoundItems',
          'manage_catalogClear', 'manage_catalogCheck', 'manage_catalogSetup', #, 'manage_checkDefaultIndexes'
          'manage_addColumn', 'manage_delColumn', 'manage_addIndex', 'manage_delIndex', 'manage_clearIndex',
          'manage_reindexIndex', 'manage_main', 'manage_advanced', 'availableSplitters',

          # these two are deprecated:
          'manage_delColumns', #'manage_deleteIndex'
          ],
         ['Manager'] ),

        ( search_zcatalog,
         ['searchResults', '__call__', 'uniqueValuesFor',
          'manage_setProgress',
          'getpath', 'schema', 'indexes', 'index_objects',
          'all_meta_types', 'valid_roles', 'resolve_url',
          'getobject', 'search'],
         ['Anonymous', 'Manager'] ),

        ( manage_zcatalog_indexes,
         ['getIndexObjects'],
         ['Manager'] ),
        )

    _catalog_properties = (
        { 'id':'sql_conn',    'type':'string',  'mode':'w',  'default': None  },
        { 'id':'sql_db_name', 'type':'string',  'mode':'w',  'default': None  },
        { 'id':'sql_prefix',  'type':'string',  'mode':'w',  'default': ''    },
        { 'id':'sql_root',    'type':'string',  'mode':'w',  'default':'root' },
        { 'id':'sql_user',    'type':'string',  'mode':'w',  'default':'root' },
    )

    _properties = Folder._properties + _catalog_properties

    manage_catalogAddRowForm = DTMLFile('dtml/catalogAddRowForm', globals())
    manage_catalogView = DTMLFile('dtml/catalogView', globals())
    manage_catalogFind = DTMLFile('dtml/catalogFind', globals())
    manage_catalogSchema = DTMLFile('dtml/catalogSchema', globals())
    manage_catalogIndexes = DTMLFile('dtml/catalogIndexes', globals())
    manage_catalogAdvanced = DTMLFile('dtml/catalogAdvanced', globals())
    manage_objectInformation = DTMLFile('dtml/catalogObjectInformation', globals())

    Indexes = ZSQLCatalogIndexes()

    threshold = 10000
    _v_total = 0
    _v_transaction = None
    _v_sql_connection = None

    def _IsDebug( self ):
        try: return self.getPortalObject().aq_parent.getProperty('DEBUG_ZSQLCatalog') #getPhysicalRoot
        except: return None

    def __init__( self, id, title='',
                  sql_conn=None, sql_db_name=None, sql_prefix=None, sql_root=None, sql_user=None,
                  container=None
                  ):
        # Initialize attributes
        if container is not None:
            self = self.__of__(container)
        self.id = id
        self.title = title
        self.threshold = 1000
        self._v_total = 0

        self.sql_conn = sql_conn
        self.sql_db_name = sql_db_name
        self.sql_prefix = sql_prefix and sql_prefix[0:2] or ''
        self.sql_root = sql_root
        self.sql_user = sql_user

        self._catalog = Catalog()

    def __len__( self ):
        try: return self.run( 'size', max_rows=1, mode='item' ) or 0
        except: return 0

    def _connection_string( self ):
        return '%s %s' % ( self.sql_db_name, self.sql_user )
    #
    #   SQLCatalog properties ====================================================================================
    #
    def getSqlDBName( self ):
        return getattr(self, 'sql_db_name', None)

    def getSqlPrefix( self ):
        return getattr(self, 'sql_prefix', None) or ''

    def getSqlTableName( self, table ):
        #prefix = self.getSqlPrefix()
        #return '%s%s' % ( prefix, prefix and table.capitalize() or table )
        return '%s%s' % ( self.getSqlPrefix(), table )

    def getSqlRootName( self, with_db_name=None ):
        root = self.getSqlTableName( self.sql_root )
        if with_db_name:
            return '%s.%s' % ( self.sql_db_name, root )
        return root

    def getSqlRootColumns( self ):
        pass

    def getSchema( self, key=None, sort_item=None, for_indexes=None ):
        if for_indexes:
            schema = self._catalog.indexes
        else:
            schema = self._catalog.schema
        if key:
            return key in schema.keys() and schema[key] or None
        else:
            s = schema.items()
        if s:
            if sort_item:
                s.sort( lambda x, y: cmp(x[1][sort_item], y[1][sort_item]) )
            else:
                s.sort( lambda x, y: cmp(x[1][0], y[1][0]) )
        return s

    def getInsertPattern( self, table ):
        patterns = self._catalog.insert_patterns
        if patterns.has_key( table ):
            return patterns[ table ]
        return None

    def getUpdatePattern( self, name ):
        patterns = self._catalog.update_patterns
        if patterns.has_key( name ):
            return patterns[ name ]
        return None

    def metatypeIds( self ):
        res = [ x['name'] for x in self.all_meta_types() ]
        try: extra_types = [ getattr(x, 'id', None) for x in self.portal_types.listTypeInfo() ]
        except: extra_types = []
        for x in extra_types:
            if x not in res:
                res.append( x )
        remove_ids = ( 'simple item', 'Zope Tutorial', 'ZAK (Zope Army Knife)', )
        for x in remove_ids:
            while x in res:
                res.remove(x)
        res = uniqueValues(res)
        res.sort()
        return res

    def extensionTypes( self ):
        rs = []
        for k in default_extension_types.keys():
            rs.append( { 'name' : k, 'value' : default_extension_types[k] } )
        return tuple(rs)

    def getExtensionTypeValue( self, key ):
        return default_extension_types[key]

    def getRootIndexes( self ):
        return SQLParser.default_root_indexes
    #
    #   SQLDB functions ==========================================================================================
    #
    def connection( self ):
        # Checks, opens and returns SQL connection instance
        x = getattr(Publish, 'getSqlConnection', None)
        #s = self._connection_string()
        return x(object=self)

    def clearConnection( self ):
        if self._v_sql_connection is not None and self._v_sql_connection.connected:
            self._v_sql_connection.close()
        self._v_sql_connection = None

    def run( self, action, max_rows=1000, mode=None, no_raise=None, no_action=None, clear=None, **kw ):
        # Runs SQL query (action)
        if no_action is not None:
            query = action
        else:
            method = getattr( SQLParser, action, None )
            if method is None:
                if self._IsDebug():
                    logger.info("run checks no method: %s" % action)
                return None
            query = apply( method, ( self, ), kw )
        if not query:
            if self._IsDebug():
                logger.info("run checks no query for action: %s" % action)
            return None

        DB = self.connection()

        if DB is None:
            logger.error("connection is broken, TID: %s, query:\n%s" % ( get_ident(), query ))
            return None

        try:
            res = DB.query( query, max_rows )
        except:
            if no_raise: return None
            raise

        if clear:
            self.clearConnection()

        if not mode or type(res) != type(()):
            return res

        # Description and result set:
        # keys of description: 'name', 'type', 'width', 'null'
        # ----------------------------------------------------
        desc, rs = res

        # 1) Simple item
        # --------------
        if mode == 1 or mode == 'item':
            try:
                return rs and rs[0][0] or None
            except:
                return None

        # 2) Tuple of ( <description>, <result set> ):
        #    'description' of columns as a dictionary: {'<name>':(<type>, <null>, <width>)}
        #    'result set': tuple of columns values
        # ----------------------------------------
        elif mode == 2 or mode in ( 'default', ):
            mapping = {}
            for x in desc:
                mapping[x['name']] = ( x['type'], x['null'], x['width'] )
            return ( mapping, rs, )

        # 3) Mapping tuple ( <row 0>, <row 1>, ... ):
        #    'row' as a dictionary of columns: {'<name>':'<value>', ...}
        # --------------------------------------------------------------
        elif mode in ( 3,31 ) or mode in ( 'mapping', 'records', ):
            records = []
            for row in rs:
                mapping = {}
                for n in range(len(row)):
                    mapping[desc[n]['name']] = row[n]
                records.append( mapping )
            if mode == 31 or mode == 'mapping':
                return ( desc, records, )
            return records

        # 4) Description only
        # -------------------
        elif mode == 4 or mode.startswith( 'desc' ):
            return desc

        # 5) Simple list
        # --------------
        elif mode == 5 or mode in ( 'list','tuple' ):
            return [ x[0] for x in rs ]

        # Otherwise, result set ('recordset')
        # -----------------------------------
        return rs
    #
    #   ZMI functions ============================================================================================
    #
    def manage_edit( self, RESPONSE, URL1, threshold=1000, REQUEST=None ):
        """
            Edit the catalog
        """
        if type(threshold) is not type(1): threshold = int(threshold)
        self.threshold = threshold

        RESPONSE.redirect( URL1 + '/manage_main?manage_tabs_message=Catalog%20Changed' )

    def manage_advanced( self, RESPONSE, URL1, pgthreshold=1000, REQUEST=None ):
        """
            Open Advanced catalog tab
        """
        if type(pgthreshold) is not type(1): pgthreshold = int(pgthreshold)
        self.pgthreshold = pgthreshold

        RESPONSE.redirect( URL1 + '/manage_catalogAdvanced?manage_tabs_message=Catalog%20Changed' )

    def manage_subbingToggle( self, REQUEST, RESPONSE, URL1 ):
        """
            Toggle subtransactions
        """
        if self.threshold:
            self.threshold = None
        else:
            self.threshold = 1000

        RESPONSE.redirect( URL1 + '/manage_catalogAdvanced?manage_tabs_message=Catalog%20Changed' )

    def _get_manage_query( self, REQUEST=None ):
        """
            Returns managed by view query params
        """
        params = ''
        if REQUEST is not None:
            for x in ( 'meta_type', 'path', 'sort_by_path', ):
                k = 'r_' + x
                if REQUEST.has_key( k ):
                    v = REQUEST.get(k) or ''
                    if v: params += '&%s=%s' % ( x, v )
        return params

    def manage_catalogObject( self, REQUEST, RESPONSE, URL1, urls=None ):
        """
            Index Zope object(s) that 'urls' point to
        """
        logger.info("manage_catalogObject urls: %s" % urls)

        if urls:
            if isinstance(urls, str):
                urls = ( urls, )

            for url in urls:
                obj = self.resolve_path(url)
                if obj is None:
                    obj = self.resolve_url( url, REQUEST )
                if obj is not None:
                    self.catalog_object( obj, url, force=1 )

        if RESPONSE is not None and URL1:
            RESPONSE.redirect( URL1 + '/manage_catalogView?manage_tabs_message=Object%20Cataloged' )

    def manage_uncatalogObject( self, REQUEST=None, RESPONSE=None, URL1=None, urls=None ):
        """
            Removes Zope object(s) 'urls' from catalog
        """
        logger.info("manage_uncatalogObject urls: %s" % urls)

        if urls:
            if isinstance(urls, str):
                urls = ( urls, )

            for url in urls:
                self.uncatalog_object( url, force=1 )

        if RESPONSE is not None and URL1:
            RESPONSE.redirect( URL1 + '/manage_catalogView?manage_tabs_message=Object%20Uncataloged' + \
                               self._get_manage_query( REQUEST ) )

    def manage_catalogReindex( self, REQUEST=None, RESPONSE=None, URL1=None ):
        """
            Clear the catalog, then re-index everything
        """
        elapse = time.time()
        c_elapse = time.clock()

        pgthreshold = self._getProgressThreshold()
        handler = ( pgthreshold > 0 ) and ZLogHandler(pgthreshold) or None

        self.refreshCatalog( clear=1, pghandler=handler )

        elapse = time.time() - elapse
        c_elapse = time.clock() - c_elapse

        RESPONSE.redirect( URL1 + '/manage_catalogAdvanced?manage_tabs_message=' +
            urllib.quote( 'Catalog Updated \n'
                          'Total time: %s\n'
                          'Total CPU time: %s' % (`elapse`, `c_elapse`) ) )

    def manage_catalogClear( self, REQUEST=None, RESPONSE=None, URL1=None ):
        """
            Clears the whole enchilada
        """
        self._catalog.clear()

        if REQUEST and RESPONSE:
            RESPONSE.redirect( URL1 + '/manage_catalogAdvanced?manage_tabs_message=Catalog%20Cleared' )

    def manage_checkDefaultIndexes( self, REQUEST=None, RESPONSE=None, URL1=None ):
        pass

    def manage_catalogCheck( self, REQUEST=None, RESPONSE=None, URL1=None ):
        """
            Checks the catalog default indexes and update paterns
        """
        self._catalog.check()

        if hasattr(self, 'check') and callable(self.check):
            self.check()

        self._catalog._checkSchema()
        self._catalog._checkIndexes()

        if REQUEST and RESPONSE:
            RESPONSE.redirect( URL1 + '/manage_catalogAdvanced?manage_tabs_message=Catalog%20Checked' )

    def manage_catalogSetup( self, REQUEST=None, RESPONSE=None, URL1=None ):
        """
            Setup the catalog
        """
        if hasattr(self, 'setup') and callable(self.setup):
            self.setup( force=1 )

        if REQUEST and RESPONSE:
            RESPONSE.redirect( URL1 + '/manage_catalogAdvanced?manage_tabs_message=Catalog%20Setup%20Done' )

    def manage_catalogFoundItems( self, REQUEST, RESPONSE, URL2, URL1, **kw ):
        """
            Find object according to search criteria and Catalog them
        """
        elapse = time.time()
        c_elapse = time.clock()

        words = 0
        obj = REQUEST.PARENTS[1]
        path = '/'.join(obj.getPhysicalPath())
        obj_metatypes = get_param('obj_metatypes', REQUEST, kw)

        logger.info('ZSQLCatalog.manage_catalogFoundItems: obj %s, path %s, metatypes %s' % ( \
            `obj`, path, obj_metatypes ))

        results = self.ZopeFindAndApply( obj, search_sub=1, REQUEST=REQUEST,
                                         apply_func=self.catalog_object,
                                         apply_path=path,
                                         trace=None,
                                         )

        elapse = time.time() - elapse
        c_elapse = time.clock() - c_elapse

        RESPONSE.redirect( URL1 + '/manage_catalogView?manage_tabs_message=' +
            urllib.quote('Catalog Updated\n'
                         'Total time: %s\n'
                         'Total CPU time: %s'
                         % (`elapse`, `c_elapse`))
            )

    def manage_addColumn( self, name, REQUEST=None, RESPONSE=None, URL1=None ):
        """
            Add a column
        """
        if REQUEST is None:
            return

        ext_type = int(REQUEST.get('ext_type'))
        ext_spec = REQUEST.get('ext_spec')
        default_value = REQUEST.get('default_value')
        as_root = REQUEST.get('as_root')
        indexable = REQUEST.get('indexable')

        self.addColumn( name, ext_type, ext_spec, default_value, as_root, indexable )

        if RESPONSE is not None:
            RESPONSE.redirect( URL1 + '/manage_catalogSchema?manage_tabs_message=Column%20Added' )

    def manage_delColumns( self, names, REQUEST=None, RESPONSE=None, URL1=None ):
        """
            Deprecated method. Use manage_delColumn instead.
        """
        self.manage_delColumn( names, REQUEST=REQUEST, RESPONSE=RESPONSE, URL1=URL1 )

    def manage_delColumn( self, names, REQUEST=None, RESPONSE=None, URL1=None ):
        """
            Delete a column or some columns
        """
        if isinstance(names, str):
            names = (names,)

        logger.info('%s.manage_delColumn names: %s' % ( self.getId(), names ))

        for name in names:
            self.delColumn(name)

        if REQUEST and RESPONSE:
            RESPONSE.redirect( URL1 + '/manage_catalogSchema?manage_tabs_message=Column%20Deleted' )

    def manage_addIndex( self, name, REQUEST=None, RESPONSE=None, URL1=None ):
        """
            Add an index
        """
        if REQUEST is None:
            return

        ext_type = int(REQUEST.get('ext_type'))
        ext_spec = REQUEST.get('ext_spec')
        default_value = REQUEST.get('default_value')
        as_root = REQUEST.get('as_root')

        self.addIndex( name, ext_type, ext_spec, default_value, as_root )

        if REQUEST and RESPONSE:
            RESPONSE.redirect( URL1 + '/manage_catalogIndexes?manage_tabs_message=Index%20Added' )

    def manage_delIndex( self, ids=None, REQUEST=None, RESPONSE=None, URL1=None ):
        """
            Delete an index or some indexes
        """
        if not ids:
            return MessageDialog(title='No items specified', message='No items were specified!',
                action = "./manage_catalogIndexes",)

        if isinstance(ids, str):
            ids = (ids,)

        for name in ids:
            self.delIndex(name)

        if REQUEST and RESPONSE:
            RESPONSE.redirect( URL1 + '/manage_catalogIndexes?manage_tabs_message=Index%20Deleted' )

    def manage_clearIndex( self, ids=None, REQUEST=None, RESPONSE=None, URL1=None ):
        """
            Clear an index or some indexes
        """
        if not ids:
            return MessageDialog(title='No items specified', message='No items were specified!',
                action = "./manage_catalogIndexes",)

        if isinstance(ids, str):
            ids = (ids,)

        for name in ids:
            self.clearIndex(name)

        if REQUEST and RESPONSE:
            RESPONSE.redirect( URL1 + '/manage_catalogIndexes?manage_tabs_message=Index%20Cleared' )

    def manage_reindexIndex( self, ids=None, REQUEST=None, RESPONSE=None, URL1=None ):
        """
            Reindex indexe(s) from a ZSQLCatalog
        """
        if not ids:
            return MessageDialog(title='No items specified', message='No items were specified!',
                action = "./manage_catalogIndexes",)

        pgthreshold = self._getProgressThreshold()
        handler = (pgthreshold > 0) and ZLogHandler(pgthreshold) or None
        self.reindexIndex(ids, REQUEST, handler, force=1)

        if REQUEST and RESPONSE:
            RESPONSE.redirect( URL1 + '/manage_catalogIndexes?manage_tabs_message=Reindexing%20Performed' )
    #
    #   Matadata settings ========================================================================================
    #
    def addColumn( self, name, ext_type, ext_spec, default_value, as_root, engine, indexable, \
                   check=None, REQUEST=None ):
        self._catalog.addColumn( name, ext_type, ext_spec, default_value, as_root, \
                   engine, indexable, check=check )

    def delColumn( self, name, check=None ):
        self._catalog.delColumn( name, check=check )
    #
    #   Indexing methods =========================================================================================
    #
    def addIndex( self, name, ext_type, ext_spec, default_value, as_root, engine, indexable, \
                  check=None, REQUEST=None ):
        self._catalog.addIndex( name, ext_type, ext_spec, default_value, as_root, \
                  engine, indexable, check=check )

    def delIndex( self, name, check=None ):
        self._catalog.delIndex( name, check=check )

    def clearIndex( self, name ):
        pass

    def reindexIndex( self, name, REQUEST=None, pghandler=None, force=None ):
        if isinstance(name, str):
            name = (name,)

        paths = self._catalog.getPaths()
        num_paths = len(paths)

        i = 0
        if pghandler is not None:
            pghandler.init('reindexing %s' % name, num_paths)

        for p in paths:
            i+=1
            if pghandler is not None:
                pghandler.report(i)
            obj = self.resolve_path(p)
            if obj is None:
                obj = self.resolve_url(p, REQUEST)
            if obj is None:
                logger.error('reindexIndex could not resolve an object from the uid %r.' % p)
            else:
                # don't update metadata when only reindexing a single index via the UI
                self.catalog_object( obj, p, idxs=name, update_metadata=0, pghandler=pghandler, \
                                     force=force )

        if pghandler is not None:
            pghandler.finish()
    #
    #   Public cataloging API ====================================================================================
    #
    def catalog_object( self, obj, uid=None, idxs=None, update_metadata=1, pghandler=None, force=None ):
        """
            Wrapper around catalog
        """
        if uid is None:
            try: uid = obj.getPhysicalPath
            except AttributeError:
                raise CatalogError(
                    "A cataloged object must support the 'getPhysicalPath' "
                    "method if no unique id is provided when cataloging"
                    )
            else: uid='/'.join(uid())
        elif not isinstance(uid, str):
            raise CatalogError('The object unique id must be a string.')

        t = id(transaction.get())
        #logger.info('ZSQLCatalog.catalog_object: SCO [%s]' % t)
        self._catalog.catalogObject( obj, uid, None, idxs, update_metadata=update_metadata, force=force )
        #logger.info('ZSQLCatalog.catalog_object: FCO [%s]' % t)

        # None passed in to catalogObject as third argument indicates
        # that we shouldn't try to commit subtransactions within any
        # indexing code.  We throw away the result of the call to
        # catalogObject (which is a word count), because it's
        # worthless to us here.

        if self.threshold is not None:
            # figure out whether or not to commit a subtransaction.
            if t != self._v_transaction:
                self._v_total = 0
            self._v_transaction = t
            self._v_total = self._v_total + 1
            # increment the _v_total counter for this thread only and get
            # a reference to the current transaction.
            # the _v_total counter is zeroed if we notice that we're in
            # a different transaction than the last one that came by.
            # self.threshold represents the number of times that
            # catalog_object needs to be called in order for the catalog
            # to commit a subtransaction.  The semantics here mean that
            # we should commit a subtransaction if our threshhold is
            # exceeded within the boundaries of the current transaction.
            if self._v_total > self.threshold:
                transaction.savepoint(optimistic=True)
                self._p_jar.cacheGC()
                self._v_total = 0
                if pghandler is not None:
                    pghandler.info('commiting subtransaction')

    def uncatalog_object( self, uid, force=None ):
        """
            Wrapper around catalog
        """
        self._catalog.uncatalogObject(uid, force=force)

    def uniqueValuesFor( self, name ):
        """
            Return the unique values for a given FieldIndex
        """
        return self._catalog.uniqueValuesFor(name)

    def getpath( self, rid ):
        """
            Return the 'path' to a cataloged object given a 'data_record_id_'
        """
        return self._catalog.getPaths( rid=rid )

    def getuid( self, rid, default=None ):
        """
            Return the 'uid' to a cataloged object given a 'data_record_id_'
        """
        return self._catalog.getUids( rid=rid )

    def getrid( self, path, default=None ):
        """
            Return 'data_record_id_' the to a cataloged object given a 'path'
        """
        return self._catalog.getUids( path=path )

    def getobject( self, rid, REQUEST=None ):
        """
            Return a cataloged object given a 'data_record_id_'
        """
        return self.aq_parent.unrestrictedTraverse( self.getpath(rid) )

    def getMetadataForUID( self, uid ):
        """
            Return the correct metadata given the uid, usually the path
        """
        rid = self._catalog.uids[uid]
        return self._catalog.getMetadataForRID(rid)

    def getIndexDataForUID( self, uid ):
        """
            Return the current index contents given the uid, usually the path
        """
        rid = self._catalog.uids[uid]
        return self._catalog.getIndexDataForRID(rid)

    def getMetadataForRID( self, rid ):
        """
            Return the correct metadata for the cataloged record id
        """
        return self._catalog.getMetadataForRID(int(rid))

    def getIndexDataForRID( self, rid ):
        """
            Return the current index contents for the specific rid
        """
        return self._catalog.getIndexDataForRID(rid)

    def schema( self ):
        return self._catalog.schema.keys()

    def indexes( self ):
        return self._catalog.indexes.keys()

    def index_objects( self ):
        # This method returns unwrapped indexes!
        # You should probably use getIndexObjects instead
        return self._catalog.indexes.values()

    def getIndexObjects( self ):
        # Return a list of wrapped(!) indexes
        #getIndex = self._catalog.getIndex
        #return [ getIndex(name) for name in self.indexes() ]
        pass
    #
    #   Searching functions ======================================================================================
    #
    def _searchable_arguments( self ):
        r = {}
        n={'optional':1}
        for name in self._catalog.indexes.keys():
            r[name]=n
        return r

    def _searchable_result_columns( self ):
        r = []
        for name in self._catalog.schema.keys():
            i = {}
            i['name'] = name
            i['type'] = 's'
            i['parser'] = str
            i['width'] = 8
            r.append(i)
        r.append({'name': 'data_record_id_',
                  'type': 's',
                  'parser': str,
                  'width': 8})
        return r

    def searchSortedByPathResults( self, REQUEST=None, used=None, **kw ):
        """
            Search and sort by 'path'
        """
        sort_on = get_param('sort_by_path', REQUEST, kw) and 'path' or None
        try: return self._catalog.searchResults( REQUEST, used=used, sort_on=sort_on, rs_type=1, **kw )
        except: return ( 0, [] )

    def countResults( self, REQUEST=None, **kw ):
        """
            Count records in the catalog
        """
        return self._catalog.countResults( REQUEST, **kw )

    def searchResults( self, REQUEST=None, used=None, **kw ):
        """
            Search the catalog.
            Search terms can be passed in the REQUEST or as keyword arguments.
            The used argument is now deprecated and ignored
        """
        return self._catalog.searchResults( REQUEST, used, **kw )

    __call__ = searchResults

    def searchTrees( self, REQUEST=None, **kw ):
        """
            Search object trees inside the catalog.
            Search terms can be passed in the REQUEST or as keyword arguments.
        """
        return self._catalog.searchTrees( REQUEST, **kw )

    def search( self, query_request, sort_index=None, reverse=0, limit=None, merge=1 ):
        """
            Programmatic search interface, use for searching the catalog from scripts.

            query_request: Dictionary containing catalog query
            sort_index:    Name of sort index
            reverse:       Reverse sort order?
            limit:         Limit sorted result count (optimization hint)
            merge:         Return merged results (like searchResults) or raw results for later merging.
        """
        if sort_index is not None:
            sort_index = self._catalog.indexes[sort_index]
        return self._catalog.search( query_request, sort_index, reverse, limit, merge )

## this stuff is so the find machinery works

    meta_types=() # Sub-object types that are specific to this object

    def valid_roles( self ):
        #Return list of valid roles
        obj = self
        dict = {}
        dup = dict.has_key
        x = 0
        while x < 100:
            if hasattr(obj, '__ac_roles__'):
                roles = obj.__ac_roles__
                for role in roles:
                    if not dup(role):
                        dict[role]=1
            if not hasattr(obj, 'aq_parent'):
                break
            obj = obj.aq_parent
            x = x+1
        roles = dict.keys()
        roles.sort()
        return roles
    #
    #   Refreshing catalog functions =============================================================================
    #
    def refreshCatalog( self, clear=0, pghandler=None ):
        """
            Re-index everything we can find
        """
        catalog = self._catalog
        paths = catalog.getPaths()

        if not paths:
            return
        elif clear:
            paths = tuple(paths)
            catalog.clear()

        num_objects = len(paths)
        if pghandler is not None:
            pghandler.init('Refreshing catalog: %s' % self.absolute_url(1), num_objects)

        for i in xrange(num_objects):
            if pghandler is not None:
                pghandler.report(i)

            p = paths[i]
            obj = self.resolve_path(p)
            
            if obj is None and hasattr( self, 'REQUEST' ):
                obj = self.resolve_url( p, self.REQUEST )
            if obj is not None:
                try:
                    self.catalog_object( obj, p, pghandler=pghandler )
                #except ConflictError:
                #    raise
                except:
                    logger.error('Recataloging object at %s failed' % p, exc_info=sys.exc_info())

        if pghandler is not None:
            pghandler.finish()

    def ZopeFindAndApply( self, obj, obj_ids=None, search_sub=0, REQUEST=None, pre='',
                          apply_func=None, apply_path='', trace=None,
                          recursive=None, check=None, **kw ):
        """
            Zope Find interface and apply.

            This is a *great* hack.  Zope find just doesn't do what we
            need here; the ability to apply a method to all the objects
            *as they're found* and the need to pass the object's path into
            that method.
        """
        obj_metatypes = get_param('obj_metatypes', REQUEST, kw)
        obj_not_cataloged_only = get_param('obj_not_cataloged_only', REQUEST, kw)
        obj_searchterm = get_param('obj_searchterm', REQUEST, kw)
        obj_expr = get_param('obj_expr', REQUEST, kw)
        obj_mtime = get_param('obj_mtime', REQUEST, kw)
        obj_mspec = get_param('obj_mspec', REQUEST, kw)
        obj_permission = get_param('obj_permission', REQUEST, kw)
        obj_roles = get_param('obj_roles', REQUEST, kw)

        if recursive is None:
            if obj_metatypes and 'all' in obj_metatypes:
                obj_metatypes = None

            if obj_mtime and type(obj_mtime)==type('s'):
                obj_mtime = DateTime(obj_mtime).timeTime()

            if obj_permission:
                obj_permission = p_name(obj_permission)

            if obj_roles and type(obj_roles) is type('s'):
                obj_roles = [ obj_roles ]

            if obj_expr:
                # Setup expr machinations
                md = td()
                obj_expr = (Eval(obj_expr), md, md._push, md._pop )
        result = []

        base = obj
        if hasattr(obj, 'aq_base'):
            base = obj.aq_base

        if not hasattr(base, 'objectItems'):
            return result

        try: items = obj.objectItems()
        except: return result

        try: add_result = result.append
        except: raise AttributeError, `result`

        if apply_path and not apply_path.startswith('/'):
            apply_path = '/' + apply_path

        for id, ob in items:
            if pre: p = "%s/%s" % ( pre, id )
            else: p = id

            dflag = 0
            if hasattr(ob, '_p_changed') and ob._p_changed == None:
                dflag = 1

            if hasattr(ob, 'aq_base'): base = ob.aq_base
            else: base = ob

            meta_type = getattr(base, 'meta_type', None)

            if ( \
               ( not obj_ids or absattr(base.id) in obj_ids )
                 and
               ( not obj_metatypes or meta_type in obj_metatypes )
                 and
               ( not obj_searchterm or ( hasattr(ob, 'PrincipiaSearchSource') and ob.PrincipiaSearchSource().find(obj_searchterm) >= 0 ))
                 and
               ( not obj_expr or expr_match(ob, obj_expr) )
                 and
               ( not obj_mtime or mtime_match(ob, obj_mtime, obj_mspec) )
                 and
               ( not obj_permission or not obj_roles or role_match(ob, obj_permission, obj_roles) ) ):

                if apply_func is not None:
                    IsRun = 1
                    uid = '%s/%s' % ( apply_path, p )
                    try:
                        ob.parent_path()
                    except AttributeError:
                        ob = self.resolve_path(uid)
                    #uid = '/'.join(aq_base(ob).getPhysicalPath())
                    #LOG('xxx', DEBUG, 'uid:%s-%s' % ( uid, apply_path ))

                    if obj_not_cataloged_only:
                        if self._catalog.getRid( uid ) is not None:
                            IsRun = 0
                    try:
                        if IsRun:
                            if not check:
                                kw = { 'force': 1 }
                                apply( apply_func, ( ob, uid, ), kw )
                                #apply_func(ob, uid, force=1)
                            add_result( ( p, ob ) )
                    except Exception, message:
                        exc = sys.exc_info()
                        logger.error('ZSQLCatalog.ZopeFindAndApply: %s: meta_type %s, uid [%s]' % ( \
                            exc[1], meta_type, uid ))
                        raise #continue
                    if trace:
                        logger.info('ZSQLCatalog.ZopeFindAndApply: uid [%s]' % uid)
                else:
                    add_result( ( p, ob ) )
                    dflag = 0

            if search_sub and hasattr( base, 'objectItems' ):
                result += \
                    self.ZopeFindAndApply( ob, obj_ids, search_sub, REQUEST, p, apply_func, apply_path,
                                           obj_metatypes=obj_metatypes,
                                           obj_not_cataloged_only=obj_not_cataloged_only,
                                           obj_searchterm=obj_searchterm, obj_expr=obj_expr,
                                           obj_mtime=obj_mtime, obj_mspec=obj_mspec,
                                           obj_permission=obj_permission, obj_roles=obj_roles,
                                           trace=trace, recursive=1, check=check
                                       )
            if dflag: ob._p_deactivate()

        return result
    #
    #   Private functions ========================================================================================
    #
    def resolve_url( self, path, REQUEST ):
        """
            Attempt to resolve a url into an object in the Zope namespace. The url may be absolute or a catalog path
            style url. If no object is found, None is returned.
            No exceptions are raised.
        """
        if REQUEST:
            script = REQUEST.script
            if path.find(script) != 0:
                path = '%s/%s' % ( script, path )
            try: return REQUEST.resolve_url(path)
            except: pass

    def resolve_path( self, path ):
        """
            Attempt to resolve a url into an object in the Zope namespace. The url may be absolute or a catalog path
            style url. If no object is found, None is returned.
            No exceptions are raised.
        """
        try: return self.unrestrictedTraverse(path)
        except: pass

    def availableSplitters( self ):
        """
            Splitter we can add
        """
        return Splitter.availableSplitters

    def manage_normalize_paths( self, REQUEST ):
        """
            Ensure that all catalog paths are full physical paths.
            This should only be used with ZSQLCatalogs in which all paths can
            be resolved with unrestrictedTraverse.
        """
        paths = self._catalog.getPaths()
        uids = self._catalog.getUids()
        unchanged = 0
        fixed = []
        removed = []

        for path, rid in uids.items():
            ob = None
            if path[:1] == '/':
                ob = self.resolve_url(path[1:],REQUEST)
            if ob is None:
                ob = self.resolve_url(path, REQUEST)
                if ob is None:
                    removed.append(path)
                    continue
            ppath = '/'.join(ob.getPhysicalPath())
            if path != ppath:
                fixed.append((path, ppath))
            else:
                unchanged = unchanged + 1

        for path, ppath in fixed:
            rid = uids[path]
            del uids[path]
            paths[rid] = ppath
            uids[ppath] = rid
        for path in removed:
            self.uncatalog_object( path )

        return MessageDialog(title='Done Normalizing Paths',
          message='%s paths normalized, %s paths removed, and '
                  '%s unchanged.' % (len(fixed), len(removed), unchanged),
          action='./manage_main')

    def manage_setProgress( self, pgthreshold=0, RESPONSE=None, URL1=None ):
        """
            Set parameter to perform logging of reindexing operations very 'pgthreshold' objects
        """
        self.pgthreshold = pgthreshold
        if RESPONSE:
            RESPONSE.redirect( URL1 + '/manage_catalogAdvanced?manage_tabs_message=Catalog%20Changed' )

    def _getProgressThreshold( self ):
        if not hasattr(self, 'pgthreshold'):
            self.pgthreshold = 0
        return self.pgthreshold

    def manage_convertIndexes( self, REQUEST=None, RESPONSE=None, URL1=None ):
        """
            Recreate indexes derived from UnIndex because the implementation of
            __len__ changed in Zope 2.8. Pre-Zope 2.7 installation used to implement
            __len__ as persistent attribute of the index instance which is totally
            incompatible with the new extension class implementation based on new-style
            classes
        """
        logger.info('Start migration of indexes for %s' % self.absolute_url(1))
        
        reindex_ids = []

        for idx in self.Indexes.objectValues():
            bases = [ str(name) for name in idx.__class__.__bases__ ]
            found = False

            if idx.meta_type == 'PathIndex':
                found = True
            else:
                for base in bases:
                    if 'UnIndex' in base:
                        found = True
                        break

            if found:
                idx_type = idx.meta_type
                idx_id = idx.getId()
                logger.info('processing index %s' % idx_id)

                indexed_attrs = getattr(idx, 'indexed_attrs', None)

                if idx.meta_type == 'DateRangeIndex':
                    since_field = getattr(idx, '_since_field', None)
                    until_field = getattr(idx, '_until_field', None)

                self.delIndex(idx.getId())
                self.addIndex(idx_id, idx_type)
                new_idx = self.Indexes[idx_id]

                if indexed_attrs:
                    setattr(new_idx, 'indexed_attrs', indexed_attrs)

                if idx.meta_type == 'DateRangeIndex':
                    setattr(new_idx, '_since_field',  since_field)
                    setattr(new_idx, '_until_field', until_field)
                reindex_ids.append(idx_id)
        
        if reindex_ids:
            logger.info('Reindexing %s' % ', '.join(reindex_ids))
            self.manage_reindexIndex(reindex_ids, REQUEST)

        self._migrated_280 = True
        logger.info('Finished migration of indexes for %s' % self.absolute_url(1))

        if RESPONSE:
            RESPONSE.redirect( URL1 + '/manage_main?manage_tabs_message=Indexes%20converted%20and%20reindexed' )

Globals.default__class_init__(ZSQLCatalog)


def p_name( name ):
    return '_' + string.translate(name, name_trans) + '_Permission'

def absattr( attr ):
    if callable(attr): return attr()
    return attr

def get_param( name, REQUEST, kw=None, default=None ):
    value = None
    IsError = 0
    if kw:
        try: value = kw.get(name)
        except:
            IsError = 1
    if ( IsError or not value ) and REQUEST is not None:
        try: value = REQUEST.get(name)
        except:
            pass
    return value or default


class td( RestrictedDTML, TemplateDict ):
    pass

def expr_match( ob, ed, c=InstanceDict, r=0 ):
    e, md, push, pop=ed
    push(c(ob, md))
    try: r = e.eval(md)
    finally:
        pop()
        return r

def mtime_match( ob, t, q, fn=hasattr ):
    if not fn(ob, '_p_mtime'):
        return 0
    return q=='<' and (ob._p_mtime < t) or (ob._p_mtime > t)

def role_match( ob, permission, roles, lt=type([]), tt=type(()) ):
    pr=[]
    fn=pr.append

    while 1:
        if hasattr(ob, permission):
            p=getattr(ob, permission)
            if type(p) is lt:
                map(fn, p)
                if hasattr(ob, 'aq_parent'):
                    ob=ob.aq_parent
                    continue
                break
            if type(p) is tt:
                map(fn, p)
                break
            if p is None:
                map(fn, ('Manager', 'Anonymous'))
                break

        if hasattr(ob, 'aq_parent'):
            ob=ob.aq_parent
            continue
        break

    for role in roles:
        if not (role in pr):
            return 0
    return 1
