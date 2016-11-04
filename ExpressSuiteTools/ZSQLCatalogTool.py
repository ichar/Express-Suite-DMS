"""
Portal catalog tool with MySQL supporting
$Id: ZSQLCatalogTool.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 18/06/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import sys
from types import ListType, TupleType, DictType, StringType
from DateTime import DateTime

from Globals import DTMLFile
from AccessControl import ClassSecurityInfo
from AccessControl.PermissionRole import rolesForPermissionOn
from Acquisition import aq_base, aq_get

import transaction

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.CatalogTool import IndexableObjectWrapper as _IndexableObjectWrapper
from Products.CMFCore.utils import _checkPermission, _getAuthenticatedUser, \
     getToolByName, _dtmldir, _mergedLocalRoles
from Products.CMFCore.interfaces.portal_catalog import portal_catalog as ICatalogTool

from Products.ZSQLCatalog.ZSQLCatalog import ZSQLCatalog as ZCatalog
from Products.ZSQLCatalog.Catalog import CatalogSearchArgumentsMap, view
from ZODB.POSException import ConflictError, ReadConflictError

import Config
from SearchProfile import SearchQuery
from SimpleObjects import ToolBase
from DepartmentDictionary import departmentDictionary
from PortalLogger import portal_log, portal_info, portal_debug, portal_error
from TransactionManager import interrupt_thread

from Utils import InitializeClass, getLanguageInfo, getClientStorageType, getContainedObjects, \
     uniqueValues, uniqueItems, check_request

from CustomDefinitions import CustomSystemObjects, CustomCategoryIds, CustomPortalColors
from CustomObjects import CustomAttributeValue

from logging import getLogger
logger = getLogger( 'ZSQLCatalogTool' )

uncategorial_types = ( \
    'Registry', 'Task Item', 'Discussion Item', 'Heading', 'FS Folder', 'Search Profile', 'Image Attachment',
    'File Attachment', 'File', 'Shortcut',
    )

search_like_exp          = "%%%s%%"
default_searchable_limit = 1000
default_visible_limit    = 100
default_unlimit          = 1000000
timeout                  = 1.0


class GroupItem:

    __allow_access_to_unprotected_subobjects__ = 1

    meta_type = 'GroupItem'

    reverse_key = '-X'

    def __init__( self, id, name, value, typ, reverse=None ):
        """
            Initialize Group Query Results class instance
        """
        self.id = ('000'+str(id))[-3:]
        self.group = 1
        self.is_grouped = 1
        self.typ = typ
        if reverse:
            value = value + self.reverse_key
        setattr( self, name, value )
        self.count = 0

    def __getitem__( self, name ):
        return getattr( self, name, None )

    def getId( self ):
        return self.id

    def unGroup( self ):
        self.is_grouped = 0

    def inc( self ):
        """ Increase object's group count """
        self.count += 1

    def get_count( self ):
        return self.count

    def dec( self ):
        """ Decrease object's group count """
        if self.count > 0: self.count -= 1

    def get( self, context=None ):
        if context is None:
            return self.__str__()

        elif hasattr(self, 'category'):
            msg = getToolByName( context, 'msg', None )
            if self.typ in uncategorial_types:
                value = self.getname('category')
                return '%s (%s)' % ( msg(value), self.count )
            else:
                metadata = getToolByName( context, 'portal_metadata', None )
                name = self.getname('category')
                another = msg('another')
                if not name or name == 'None':
                    return '%s (%s)' % ( another, self.count )
                try: value = metadata.getCategoryById(name).Title()
                except: value = another
                return '%s (%s)' % ( value, self.count )

        elif hasattr(self, 'Creator'):
            msg = getToolByName( context, 'msg', None )
            if self.typ in ('Heading', 'Task Item',):
                value = self.getname('Creator')
                return '%s (%s)' % ( name, self.count )
            else:
                membership = getToolByName( context, 'portal_membership', None )
                name = self.getname('Creator')
                another = msg('another')
                if not name or name == 'None':
                    return '%s (%s)' % ( another, self.count )
                try: value = membership.getMemberName( name )
                except: value = another
                return '%s (%s)' % (value, self.count)

        elif hasattr( self, 'created' ):
            value = self.getname('created')
            return '%s (%s)' % ( value, self.count )

        elif hasattr(self, 'modified'):
            value = self.getname('modified')
            return '%s (%s)' % ( value, self.count )

    def getname( self, name ):
        value = getattr( self, name, None )
        n = len(self.reverse_key)
        return value.endswith(self.reverse_key) and value[:-n] or value

    def __str__( self ):
        return 'GroupItem: '+str(self.__dict__)


class IndexableObjectWrapper( _IndexableObjectWrapper ):

    __ignored_indexes = {
            'nd_uid' : (['isVersion'], None),
        }

    __allowed_indexes = {
            'hasBase' : (['isCategorial'], ()),
        }

    def __init__( self, vars, ob ):
        names = {}
        if hasattr( aq_base(ob), 'implements' ):

            for attr, (impls, default) in self.__ignored_indexes.items():
                for impl in impls:
                    if ob.implements( impl ):
                        names[ attr ] = default
                        break

            for attr, (impls, default) in self.__allowed_indexes.items():
                for impl in impls:
                    if ob.implements( impl ):
                        break
                else:
                    names[ attr ] = default
        else:
            for attr, (impls, default) in self.__allowed_indexes.items():
                names[ attr ] = default

        self.__ignored_names = names
        _IndexableObjectWrapper.__init__( self, vars, ob )

    def __getattr__( self, name ):
        try: return self.__ignored_names[ name ]
        except: pass #except KeyError: pass
        return _IndexableObjectWrapper.__getattr__( self, name )


class CatalogTool( ToolBase, ZCatalog ):
    """
        Portal catalog
    """
    _class_version = 1.04

    id = 'portal_catalog'
    meta_type = 'ExpressSuite Catalog Tool'

    __implements__ = (ICatalogTool, ZCatalog.__implements__,)

    security = ClassSecurityInfo()

    manage_options = ZCatalog.manage_options # + ToolBase.manage_options

    # ---------------------------------------------------------------------------------------------------------- #
    #   <metadata key>             <ext_type>    <R><M><I>  <data type>      <attributes>          <engine>      #
    # ---------------------------------------------------------------------------------------------------------- #
    _catalog_metadata = { \
        'allowedRolesAndUsers' : ( 'ListType',    0, 0, 1,  'CHAR',      50, 'ASCII NOT NULL',     'MYISAM', ),
        'archive'              : ( 'SimpleType',  1, 1, 1,  'BOOLEAN',    0, 'NOT NULL DEFAULT 0', '',       ),
        'category'             : ( 'SimpleType',  1, 1, 1,  'VARCHAR',   20, \
                                   'CHARACTER SET latin1 COLLATE latin1_general_cs NULL',          '',       ),
        'CategoryAttributes'   : ( 'KeywordType', 0, 1, 1,  'VARCHAR',  250, 'NULL',               'MYISAM', ),
        'created'              : ( 'SimpleType',  1, 1, 1,  'DATETIME',   0, 'NOT NULL',           '',       ),
        'CreationDate'         : ( 'SimpleType',  0, 1, 0,  'DATETIME',   0, 'NOT NULL',           '',       ),
        'Creator'              : ( 'SimpleType',  1, 1, 1,  'CHAR',      30, 'ASCII NULL',         '',       ),
        'Date'                 : ( 'SimpleType',  0, 1, 1,  'DATETIME',   0, 'NULL',               '',       ),
        'Description'          : ( 'SimpleType',  0, 1, 1,  'VARCHAR',  500, 'NOT NULL',           '',       ),
        'effective'            : ( 'SimpleType',  1, 1, 1,  'DATETIME',   0, 'NULL',               '',       ),
        'EffectiveDate'        : ( 'SimpleType',  0, 1, 0,  'DATETIME',   0, 'NULL',               '',       ),
        'expires'              : ( 'SimpleType',  1, 1, 1,  'DATETIME',   0, 'NULL',               '',       ),
        'ExpirationDate'       : ( 'SimpleType',  0, 1, 0,  'DATETIME',   0, 'NULL',               '',       ),
        'getIcon'              : ( 'SimpleType',  1, 1, 0,  'VARCHAR',  255, \
                                   'CHARACTER SET latin1 COLLATE latin1_general_cs NULL',          '',       ),
        'hasBase'              : ( 'ListType',    0, 0, 1,  'CHAR',      20, 'ASCII NULL',         'MYISAM', ),
        'hasResolution'        : ( 'SimpleType',  1, 1, 1,  'BOOLEAN',    0, 'NOT NULL DEFAULT 0', '',       ),
        'id'                   : ( 'SimpleType',  1, 1, 1,  'VARCHAR',  255, \
                                   'CHARACTER SET latin1 COLLATE latin1_general_cs NOT NULL',      '',       ),
        'implements'           : ( 'ListType',    0, 1, 1,  'CHAR',      30, 'ASCII NOT NULL',     'MYISAM', ),
        'in_reply_to'          : ( 'ListType',    0, 0, 1,  'VARCHAR',   50, 'NULL',               '',       ),
        'meta_type'            : ( 'SimpleType',  1, 1, 1,  'CHAR',      20, 'ASCII NOT NULL',     '',       ),
        'modified'             : ( 'SimpleType',  1, 1, 1,  'DATETIME',   0, 'NULL',               '',       ),
        'ModificationDate'     : ( 'SimpleType',  0, 1, 0,  'DATETIME',   0, 'NULL',               '',       ),
        'nd_uid'               : ( 'SimpleType',  1, 1, 1,  'CHAR',      23, 'ASCII NULL',         '',       ),
        'parent_path'          : ( 'SimpleType',  0, 1, 1,  'VARCHAR',  500, \
                                   'CHARACTER SET latin1 COLLATE latin1_general_cs NOT NULL',      'MYISAM', ),
        'portal_type'          : ( 'SimpleType',  0, 1, 1,  'CHAR',      20, 'ASCII NOT NULL',     '',       ),
        'registry_ids'         : ( 'SimpleType',  1, 1, 1,  'VARCHAR',   30, 'NULL',               '',       ),
        'state'                : ( 'SimpleType',  1, 1, 1,  'CHAR',      20, 'ASCII NULL',         '',       ),
        'SearchableText'       : ( 'SimpleType',  0, 0, 2,  'TEXT',    4000, 'NULL',               'MYISAM', ),
        'Subject'              : ( 'SimpleType',  0, 1, 1,  'VARCHAR',  250, 'NULL',               '',       ),
        'Title'                : ( 'SimpleType',  1, 1, 1,  'VARCHAR',  500, 'NULL',               '',       ),
        'Type'                 : ( 'SimpleType',  0, 1, 0,  'CHAR',      50, 'ASCII NOT NULL',     '',       ),
        'title'                : ( 'SimpleType',  0, 0, 0,  'VARCHAR',  250, 'NOT NULL',           '',       ),
    }

    _explicit_indexes = ( \
        'CategoryAttributes', 'Subject', 'title', 'in_reply_to', 'Date', 'allowedRolesAndUsers', \
        )

    _properties = ZCatalog._catalog_properties

    _v_queries = {}

    def _IsDebug( self ):
        try: return self.getPortalObject().aq_parent.getProperty('DEBUG_ZSQLCatalogTool')
        except: return None

    def __init__( self, title='' ):
        """
            Initialize class instance
        """
        ZCatalog.__init__( self, self.getId(), title )
        ToolBase.__init__( self )

    def _initstate( self, mode ):
        """
            Initialize attributes
        """
        if not ToolBase._initstate( self, mode ):
            return 0
        """
        try:
            key = 'SearchableText'
            table = self.getSqlTableName( key )

            if not 'FULLTEXT' in view( self._catalog, 'indexType', table=table, key=key ):
                query = \
                    'ALTER TABLE %s DROP INDEX %s, ADD FULLTEXT INDEX %s(%s)' % ( \
                        table, table, table, 'attrValue' )
                self.run( query, no_action=1 )
                self.manage_catalogCheck()
        except:
            pass
        """
        return 1

    def _containment_onDelete( self, item, container ):
        if getattr(self, '_catalog', None) is not None:
            self._catalog.drop()

    def _check_unindexable_content( self, object ):
        meta_type = getattr(object, 'meta_type', None)
        if not meta_type or meta_type in Config.UnindexableContents:
            return 1
        return None
    #
    #   ZMI methods ==============================================================================================
    #
    security.declareProtected( CMFCorePermissions.ManagePortal, 'manage_overview' )
    manage_overview = DTMLFile( 'explainCatalogTool', _dtmldir )
    #
    #   Setup methods ============================================================================================
    #
    def setup( self, force=None, check=None, root_object=None ):
        """ 
            Setup Catalog instance 
        """
        id = getattr(self, 'id', None)
        sql_prefix = getattr(self, 'sql_prefix', None)
        
        logger.info('setup new instance: %s, prefix: %s, force: %s' % ( id, sql_prefix, force ))
        #
        #   Initialize the catalog
        #
        if not force:
            self._catalog._initschema()
            self._catalog.setup()
            return
        #
        #   Check indexes
        #
        self.setupIndexes( force=force )

        transaction.get().commit()
        #
        #   Find and catalog all indexable objects
        #
        obj_metatypes = ( \
            ['Heading', 'Fax Incoming Folder', 'Registry', 
             'HTMLDocument', 'HTMLCard', 'Content Version', 'Task Item', 'File Attachment', 'Image Attachment',
             'FS Folder', 'FS File', 'File', 'Shortcut', 'Search Profile'], \
            )

        if root_object is None:
            obj = self.getPortalObject()
        else:
            obj = root_object

        apply_path = '/'.join(obj.getPhysicalPath())
        apply_func = self._catalog.catalog_object

        for i in range(len(obj_metatypes)):
            res = self._catalog.ZopeFindAndApply( obj, obj_metatypes=obj_metatypes[i], obj_not_cataloged_only=1,
                apply_func=apply_func, apply_path=apply_path, search_sub=1,
                check=check
            )

        if check: return res
        del res

    def setupIndexes( self, idxs=[], check=None, reindex=None, force=None, REQUEST=None ):
        """
            Configure the catalog indexes/columns settings.

            Arguments:

                'idxs' -- Not implemented.

                'check' -- If true, indicates that only catalog configuration
                          analysis to be perfomed.

                'reindex' -- try to reindex new or updated Index.

            Result:

                Boolean. Returns the value indicating whether the catalog
                configuration is up to date.
        """
        reindexed = []
        changed = { 'new_columns':[], 'old_columns':[], 'new_indexes':[], 'old_indexes':[] }

        columns = self.enumerateColumns()
        indexes = self.enumerateIndexes()

        # Setup new columns
        for column in columns:
            key = column[0]
            if key not in self.schema():
                if check:
                    changed['new_columns'].append( key )
                else:
                    apply( self.addColumn, column, { 'check':check } )

        # Setup new indexes
        for index in indexes:
            key = index[0]
            if key not in self.indexes():
                if check:
                    changed['new_indexes'].append( key )
                else:
                    apply( self.addIndex, index, { 'check':check } )
                    reindexed.append( key )

        root_indexes = self.getRootIndexes()

        # Remove redundant columns
        x = map(lambda x: x[0], columns)
        for key in self.schema():
            if not ( key in x or key in root_indexes ):
                if check:
                    changed['old_columns'].append( key )
                else:
                    self.delColumn( key, check=check )

        # Remove redundant indexes
        x = map(lambda x: x[0], indexes)
        for key in self.indexes():
            if not ( key in x or key in root_indexes ):
                if check:
                    changed['old_indexes'].append( key )
                else:
                    self.delIndex( key, check=check )

        if reindex:
            for index in reindexed:
                self.reindexIndex( index, REQUEST=REQUEST )
                logger.info("setupIndexes = Index: %s reindexed" % index)

        return check and changed

    _initIndexes = setupIndexes

    def default_extensions( self, metadata=None, indexes=None ):
        # Return a sequence of schema names to be cached
        rs = []
        for key in self._catalog_metadata.keys():
            ext_type, as_root, IsMetatype, indexable, s1, s2, s3, engine  = self._catalog_metadata[key]
            if metadata and not IsMetatype: 
                continue
            if indexes and not indexable: 
                continue
            args = [ key,
                     self.getExtensionTypeValue( ext_type ),
                     '%s%s%s' % ( s1, s2 and '('+str(s2)+')' or '', s3 and ' '+s3 or '' ),
                     None,
                     as_root and 1 or 0,
                     engine,
                     ]
            if metadata or indexable:
                args.append( indexable )
            rs.append( tuple(args) )
        return rs

    def enumerateColumns( self ):
        return self.default_extensions( metadata=1 )

    def enumerateIndexes( self ):
        return self.default_extensions( indexes=1 )

    def explicitIndexes( self ):
       # Return a sequence of explicit indexes
       return self._explicit_indexes
    #
    #   'portal_catalog' interface methods =======================================================================
    #
    def __url( self, ob ):
        return '/'.join( ob.getPhysicalPath() )

    def _listAllowedRolesAndUsers( self, user ):
        result = list( user.getRoles() )
        result.append( 'Anonymous' )
        result.append( 'user:%s' % user.getId() )
        # deal with groups
        getGroups = getattr(user, 'getGroups', None)
        if getGroups is not None:
            for group in getGroups():
                result.append('group:%s' % group)
        # end groups
        return result

    security.declareProtected( CMFCorePermissions.ManagePortal, 'lockCatalog' )
    def lockCatalog( self ):
        uname = _getAuthenticatedUser(self).getUserName()
        setattr( self, '_locked', 1 )
        self._p_changed = 1

        transaction.get().commit()

        portal_info( '%s.lockCatalog' % self.getId(), 'locked by %s' % uname )

    def check_catalog_locked( self ):
        return getattr( self, '_locked', None ) and 1 or 0

    security.declareProtected( CMFCorePermissions.ManagePortal, 'unlockCatalog' )
    def unlockCatalog( self ):
        uname = _getAuthenticatedUser(self).getUserName()
        setattr( self, '_locked', 0 )
        self._p_changed = 1

        transaction.get().commit()

        portal_info( '%s.unlockCatalog' % self.getId(), 'unlocked by %s' % uname )

    def wrapOb( self, object ):
        # Wraps the object with workflow and accessibility information just before cataloging
        wf = getattr( self, 'portal_workflow', None )
        if wf is not None:
            vars = wf.getCatalogVariablesFor( object )
        else:
            vars = {}
        return IndexableObjectWrapper( vars, object )

    def catalog_object( self, object, uid, idxs=[], update_metadata=1, pghandler=None, force=None ):
        if self.check_catalog_locked():
            return
        w = self.wrapOb(object)
        ZCatalog.catalog_object( self, w, uid, idxs, update_metadata=update_metadata, \
                                 pghandler=pghandler, force=force )
        if self._IsDebug():
            portal_debug( '%s.catalog_object' % self.getId(), 'uid: %s' % uid )

    def uncatalog_object( self, uid, force=None ):
        # Wrapper around catalog just before uncataloging
        if self.check_catalog_locked():
            return
        ZCatalog.uncatalog_object( self, uid, force=force )
        if self._IsDebug():
            portal_debug( '%s.uncatalog_object' % self.getId(), 'uid: %s' % uid )

    def indexObject( self, object ):
        """
            Adds to catalog
        """
        uid = self.__url(object)
        #if self._IsDebug():
        #    portal_debug( '%s.indexObject' % self.getId(), 'uid: %s' % uid )
        self.catalog_object( object, uid )

    def unindexObject( self, object ):
        """
            Removes from catalog
        """
        uid = self.__url(object)
        #if self._IsDebug():
        #    portal_debug( '%s.unindexObject' % self.getId(), 'uid: %s' % uid )
        self.uncatalog_object( uid )

    def reindexObject( self, object, idxs=[], recursive=None, update_metadata=None ):
        """
            Updates catalog after object data has changed
        """
        if self.check_catalog_locked():
            return
        IsDebug = self._IsDebug()
        catalog_id = self.getId()
        obs = [ object ]

        if recursive:
            obs.extend( getContainedObjects(object) )
        for ob in obs:
            uid = self.__url(ob)
            ZCatalog.catalog_object( self, self.wrapOb(ob), uid, idxs, update_metadata=update_metadata )
            if not IsDebug:
                continue
            portal_debug( '%s.reindexObject' % catalog_id, 'uid: %s, idxs: %s, update_metadata: %s' % ( \
                uid, idxs, update_metadata ) )

    def _containment_onAdd( self, item, container ):
        #self._catalog.clear()
        pass
    #
    #   Catalog implementary functions ===========================================================================
    #
    security.declarePublic( 'attachmentSearchEnabled' )
    def attachmentSearchEnabled( self ):
        
        return Config.AttachmentSearchable

    def _obsolete_error( self, REQUEST, context=None ):
        
        message = 'Query is already obsolete. Please repeat $ $ error'
        if context is None:
           context = self 
        REQUEST.RESPONSE.redirect( context.absolute_url( action='search_results', message=message ) )
        return None

    def getQuery( self, id=None, profile=None, copy=None, REQUEST=None, context=None ):
        """
            Returns existing (by id/profile id) or new seach query, implemented by followed executeQuery method
        """
        REQUEST = check_request( self, REQUEST )
        IsError = 0

        def check_query_id( query ):
            for n in range(10):
                id = query.getId()
                if not self._v_queries.has_key(id): return id
            return None

        if id:
            #query = REQUEST.SESSION.get( ( 'search', id ) )
            query = self._v_queries.get(id)
            if query is None:
                if REQUEST is not None:
                    return self._obsolete_error( REQUEST, context )
                raise KeyError, id
        elif profile:
            ob = self.getObjectByUid( profile, 'isSearchProfile' )
            if ob is None:
                if REQUEST is not None:
                    return self._obsolete_error( REQUEST, context )
                raise KeyError, profile
            query = ob.getQuery()
        else:
            query = SearchQuery()
            #try:
            #    REQUEST.SESSION.set( ( 'search', query.getId() ), query )
            #except:
            #    IsError = 1
            #    del query
            try:
                self._v_queries[ check_query_id(query) ] = query
            except:
                IsError = 1
            copy = 0

        if copy and query is not None:
            query = query.clone()
            #REQUEST.SESSION.set( ( 'search', query.getId() ), query )
            try:
                self._v_queries[ check_query_id(query) ] = query
            except:
                IsError = 1
 
        if IsError:
            uname = _getAuthenticatedUser(self).getUserName()
            portal_error( '%s.getQuery' % self.getId(), 'cannot get SearchQuery instance for member: %s' % uname )
            return None

        return query

    def executeQuery( self, query, REQUEST=None, **kw ):
        """
            Executes search query
        """
        if not query: return []
        indexes = {}

        member_id = _getAuthenticatedUser(self).getUserName()

        if query.oid: indexes['id'] = query.oid

        if query.category:
            if query.derivatives:
                indexes['hasBase'] = query.category
            else:
                indexes['category'] = query.category

        if query.state:
            state = query.state
            if type(state) in ( ListType, TupleType ):
                indexes['state'] = query.state
            elif type(state) is StringType:
                indexes['state'] = [ query.state ]
            else:
                try: indexes['state'] = [ state[x] for x in query.category if state.has_key(x) and state[x] != 'any' ]
                except: pass

        if query.creation:
            if query.creation[0] and query.creation[1]:
                indexes['created'] = { 'query' : query.creation, 'range' : 'min:max' }
            elif query.creation[0]:
                indexes['created'] = { 'query' : query.creation[0], 'range' : 'min' }
            elif query.creation[1]:
                indexes['created'] = { 'query' : query.creation[1], 'range' : 'max' }

        if query.owners:
            if type(query.owners) is ListType:
                indexes['Creator'] = { 'query': query.owners, 'operator': 'or' }
            else:
                indexes['Creator'] = [ query.owners ]

        if hasattr( query, 'implements' ) and query.implements:
            implements = indexes['implements'] = query.implements
        else:
            implements = indexes['implements'] = []

        if getattr( query, 'hasResolution', None ):
            indexes['hasResolution'] = 1
            indexes['implements'] = ['isVersionable']
            indexes['types'] = 'HTMLDocument'
        elif query.types:
            if 'any' in query.types:
                pass
            else:
                indexes['meta_type'] = query.types
        else:
            if 'bodies' in query.objects and 'isHTMLDocument' not in implements:
                implements.append('isHTMLDocument')
            if 'attachments' in query.objects and 'isAttachment' not in implements:
                implements.append('isAttachment')
            if 'folders' in query.objects and 'isContentStorage' not in implements:
                implements.append('isContentStorage')

        if not query.location:
            pass
        elif query.scope == 'recursive':
            indexes['path'] = query.location
        elif query.scope == 'local':
            indexes['parent_path'] = query.location

        if hasattr( query, 'attributes' ):
            indexes['CategoryAttributes'] = query.attributes

        if hasattr( query, 'registry_id' ) and query.registry_id:
            indexes['registry_ids'] = query.registry_id

        if query.title:
            indexes['Title'] = query.title
        if query.description:
            indexes['Description'] = query.description
        if query.text:
            indexes['SearchableText'] = query.text

        #for x in ( 'Title', 'Description', 'SearchableText' ):
        #    if indexes.has_key(x): 
        #        indexes[x] = search_like_exp % indexes[x]

        IsGroup = 0
        if REQUEST is not None:
            indexes['sort_on'] = kw.get('sort_on')
            indexes['sort_order'] = kw.get('sort_order')
            if REQUEST.get('group', None):
                ps = getToolByName( self, 'portal_properties', None )
                try:
                    sort_limit = int(ps.getProperty('sort_limit'))
                except:
                    sort_limit = None
                indexes['sort_limit'] = sort_limit or 2000
                IsGroup = 1

        indexes = uniqueItems( indexes )

        if self._IsDebug():
            portal_debug( '%s.executeQuery' % self.getId(), 'indexes: %s' % indexes )

        total_objects, results = self.searchResults( type='query', with_limit=1, REQUEST=REQUEST, **indexes )
        results = query.filter( results, parent=self.parent() )

        if results and IsGroup:
            return ( total_objects, self.groupResults( results, REQUEST, **kw ) )
        else:
            return ( total_objects, self.sortResults( results, **kw ) )

    def searchTrees( self, REQUEST=None, **query ):
        """
            Calls ZCatalog.searchTrees with extra arguments
        """
        user = _getAuthenticatedUser(self)

        query['allowedRolesAndUsers'] = uniqueValues(self._listAllowedRolesAndUsers( user ))
        #query['archive'] = getClientStorageType( self ) and 1 or 0

        try:
            rs = apply( ZCatalog.searchTrees, (self, REQUEST), query )
        except ReadConflictError, message:
            raise

        return rs

    def searchResults( self, type='unrestricted', archive=None, with_limit=None, REQUEST=None, **query ):
        """
            Calls ZCatalog.searchResults with extra arguments that
            limit the results to what the user is allowed to see depending on current user's storage type.
    
            Arguments:

                'type' -- type of objects: 'all' - are documents, folders and registries (default), see below

                'archive' -- archive mode: 1-archive objects only, 0-storage
        """
        user = _getAuthenticatedUser(self)
        query['allowedRolesAndUsers'] = self._listAllowedRolesAndUsers( user )

        if archive is None:
            archive = getClientStorageType( self )

        if type in ['unrestricted'] or archive is None:
            # Get objects without restrictions
            pass
        elif not archive:
            # Storage
            #query['archive'] = 0
            pass
        else:
            # Archive
            if type == 'documents':
                query['implements'] = 'isHTMLDocument'
                #query['archive'] = 1

        return self.unrestrictedSearch( REQUEST, with_limit=with_limit, **query )

    security.declarePrivate('unrestrictedSearchResults')
    def unrestrictedSearchResults( self, REQUEST=None, **kw ):
        return self.unrestrictedSearch( REQUEST=REQUEST, **kw )

    security.declarePrivate( 'unrestrictedSearch' )
    def unrestrictedSearch( self, REQUEST=None, check_permission=0, with_limit=None, **kw ):
        """
            Run ZSQLCatalog searching 
        """
        IsDebug = self._IsDebug()
        catalog_id = self.getId()

        interrupt_thread( self )

        offset = limit = rs_type = batch_start = batch_size = 0

        try:
            if with_limit:
                if REQUEST is not None and not kw.has_key('sort_limit'):
                    batch_start = int(REQUEST.get('batch_start', 1))
                    batch_size = int(REQUEST.get('batch_size', 10))
                    batch_length = int(REQUEST.get('batch_length', 0))
                    if batch_length:
                        limit = batch_start + 2 * batch_length + 1
                    else:
                        offset = batch_start - 1
                        limit = batch_size
                    kw['sort_offset'] = offset
                    kw['sort_limit'] = limit
                kw['rs_type'] = rs_type = 1
            if kw.has_key('allowedRolesAndUsers'):
                if 'Manager' not in kw['allowedRolesAndUsers']:
                    kw['allowedRolesAndUsers'] = uniqueValues(kw['allowedRolesAndUsers'])
                else:
                    del kw['allowedRolesAndUsers']
            if IsDebug:
                portal_debug( '%s.unrestrictedSearch' % catalog_id, "batch:%s-%s-%s-%s\nkw:%s" % ( \
                    batch_start, batch_size, offset, limit, kw ) \
                    )

            x = apply( ZCatalog.searchResults, (self, REQUEST), kw )

            if IsDebug:
                portal_debug( '%s.unrestrictedSearch' % catalog_id, 'x: %s' % len(x) )
            if rs_type:
                if type(x) is TupleType:
                    total_objects, results = x
                else:
                    total_objects = len(x)
                    results = x
                return ( total_objects, results )
            else:
                return x

        except ReadConflictError, message:
            raise
        except:
            raise

    def countResults( self, REQUEST=None, **kw ):
        """
            Counts records matched the query
        """
        interrupt_thread( self )

        try:
            if kw.has_key('allowedRolesAndUsers'):
                kw['allowedRolesAndUsers'] = uniqueValues(kw['allowedRolesAndUsers'])
            #kw['archive'] = getClientStorageType( self )

            x = apply( ZCatalog.countResults, (self, REQUEST), kw )

            #portal_debug( '%s.countResults' % self.getId(), 'x: %s' % x )
            return x

        except ReadConflictError, message:
            raise
        except:
            #portal_error( '%s.unrestrictedSearch' % self.getId(), 'CATALOG SEARCH ERROR', exc_info=True )
            raise

    def sortResults( self, results, unique=None, **kw ):
        """
            Sort results from the previous searches
        """
        #portal_info( '%s.sortResults' % self.getId(), 'len results:%s, sort_on: %s, sort_order: %s' % ( \
        #    len(results), kw.get('sort_on'), kw.get('sort_order') ) 
        #    )
        catalog = self._catalog

        #if unique:
        #    results = self.uniqueResults(results)

        if not hasattr( catalog, '_getSortIndex' ):
            return results
        index = catalog._getSortIndex( kw )
        if index is None:
            return results

        #limit = catalog._get_sort_attr( 'limit', kw )
        order = catalog._get_sort_attr( 'order', kw )
        reverse = order and order.lower() in ( 'reverse', 'descending' ) and 1 or 0
        #portal_info( '%s.sortResults' % self.getId(), 'len results:%s, index:%s' % ( len(results), index_name ) )

        if index == 'Creator':
            membership = getToolByName( self, 'portal_membership', None )
            if membership is not None:
                res = list(results)
                res.sort( lambda x, y, f=membership.getMemberName: cmp( f(x['Creator']), f(y['Creator']) ) )
                if reverse:
                    res.reverse()
                return res

        return results

    def uniqueResults( self, results ):
        """
            Removes duplicate records from the results set.
        """
        rid_map = {}
        for r in results:
            rid_map[r.getRID()] = r
        return rid_map.values()

    def groupResults( self, results, REQUEST=None, **kw ):
        """
            Groups catalog search results items
        """
        #portal_info( '%s.groupResultsresults' % self.getId(), '%s' % len(results) )
        if not results or REQUEST is None:
            return results

        if kw is None: kw = {}

        name = kw.get('sort_on')
        reverse = kw.get('sort_order') == 'reverse' and 1 or 0
        if not name:
            return results

        ungroup = REQUEST.get('ungroup', None) or []

        except_items = 0
        none_items = 0
        group_map = {}
        group = None
        id = 0

        for r in results:
            #ob = r.getObject()
            #if ob is None or not _checkPermission('View', ob):
            #    continue
            typ = None
            try:
                if name in ( 'created', 'modified', ):
                    x = r[name]
                    value = '%d-%s-%s' % ( x.year(), x.mm(), x.dd() )
                    typ = 'DateType'
                elif name == 'category':
                    if r['meta_type'] in uncategorial_types:
                        value = typ = r['meta_type']
                    else:
                        value = str(r[name])
                else:
                    value = str(r[name])
            except:
                except_items += 1
                continue
            if not value or value == 'None':
                none_items += 1
                continue

            if not group_map.has_key(value):
                id += 1
                group = GroupItem( id, name, value, typ, reverse )
                group_id = group.getId()
                group_map[value] = ( group[name], group_id, group )
            else:
                x, group_id, group = group_map[value]

            if group is not None: group.inc()

            if group_id in ungroup:
                group.unGroup()
                rid = value+'-'+group_id+'-'+('000'+str(group.get_count()))[-3:]
                group_map[rid] = ( rid, group_id, r )
                #portal_info( '%s.groupResults' % self.getId(), 'ungroup: %s, meta_type: %s' % ( rid, r['meta_type'] ) )

        results = group_map.values()
        results.sort()
        if reverse:
            results.reverse()

        #portal_info( '%s.groupResults' % self.getId(), 'except_items: %s, none_items: %s' % ( except_items, none_items ) )
        return [ x for rid, group_id, x in results ] # if rid.startswith('File Attachment')

    def getRemoteObjectByUid( self, remote ):
        """
            Returns an object by given UID, with remote check
        """
        obj = None
        if not remote: return None
        if type(remote) is DictType:
            try: remote_uid = remote['uid']
            except: remote_uid = None
            if remote_uid:
                obj = self.getObjectByUid( remote_uid )
        else:
            obj = self.getObjectByUid( remote )
        return obj

    def getObjectByUid( self, uid, implements=() ):
        """
            Returns an object by given UID
        """
        if uid and type(uid) is StringType:
            kw = {}
            kw['nd_uid'] = uid
            if implements:
                if not type(implements) is StringType:
                    kw['implements'] = tuple(implements)
                else:
                    kw['implements'] = implements
            results = self.searchResults( **kw )
            if results:
                try: return results[0].getObject()
                except:
                    portal_error( '%s.getObjectByUid' % self.getId(), 'uid: %s' % uid, exc_info=True )
        return None

    def unrestrictedGetObjectByUid( self, uid, implements=() ):
        """
            Returns an object by given UID, without restrictions
        """
        if uid and type(uid) is StringType:
            kw = {}
            kw['nd_uid'] = uid
            if implements:
                if not type(implements) is StringType:
                    kw['implements'] = tuple(implements)
                else:
                    kw['implements'] = implements
            results = self.unrestrictedSearch( **kw )
            if results:
                try: return results[0].getObject()
                except:
                    portal_error( '%s.unrestrictedGetObjectByUid' % self.getId(), 'uid: %s' % uid, exc_info=True )
            else:
                portal_info( '%s.unrestrictedGetObjectByUid' % self.getId(), 'not found uid: %s' % uid )
        return None

    def unrestrictedGetSubObjectByUid( self, uid, id=None, implements=() ):
        """
            Returns a subobject by given UID and id, without restrictions
        """
        ob = self.unrestrictedGetObjectByUid( uid, implements=implements )
        if ob is not None and id:
            if type(id) in ( TupleType, ListType ):
                id = id[0]
            try: ob = ob._getOb(id, None)
            except: ob = None
        return ob
    #
    #   In-Progress Settings and Utilities =======================================================================
    #
    def _parseInProgressOptions( self, REQUEST=None ):
        """
            Returns in-progress request options
        """
        enabled_only = None

        if REQUEST is not None:
            period = int(REQUEST.get('period', '0'))
            if REQUEST.has_key('enabled_only'):
                try: enabled_only = int(REQUEST.get('enabled_only'))
                except: pass
            category = filter( None, uniqueValues( REQUEST.get('category') ) )
            implements = REQUEST.get('implements') or 'isVersion'
            scale = int(REQUEST.get('scale') or 1)
            cols = int(REQUEST.get('cols') or 300)
            state = not REQUEST.has_key('archive_search') and 2 or None
        else:
            period = 0
            category = []
            implements = ''
            scale = 1
            cols = 300
            state = None

        portal_info( '%s._parseInProgressOptions' % self.getId(), \
            'period: %s, category: %s, implements: %s, scale: %s, enabled_only: %s, cols: %s, state: %s' % ( \
                period, category, implements, scale, enabled_only, cols, state ) \
            )
        return ( period, category, implements, scale, enabled_only, cols, state )

    def _parseInProgressPeriod( self, period, REQUEST=None ):
        """
            Returns in-progress request period: ( created_from, created_till )
        """
        if REQUEST is not None and REQUEST.has_key('now'):
            now = REQUEST.get('now').split('/')
            created_from = len(now) == 3 and DateTime( int(now[0]), int(now[1]), int(now[2])) or None
        else:
            created_from = None

        now = DateTime()
        current_date = DateTime(int(now.strftime('%Y')), int(now.strftime('%m')), int(now.strftime('%d')))
        days = period_to_days( period )

        if period == 0:
            created_from = DateTime(2005,1,1)
            created_till = current_date
            p = 0
        elif created_from is not None:
            p = int(REQUEST.get('p', 0)) or days
            if REQUEST.get('print_preview'):
                created_till = created_from + abs(p) - 1
            else:
                if p < 0:
                    created_till = created_from - 1
                created_from += p
                if p > 0:
                    created_till = created_from + p - 1
        else:
            created_from = current_date - float((days - 1) * 3600 * 24) / 86400
            created_till = current_date
            p = 0

        portal_info( '%s._parseInProgressPeriod' % self.getId(), \
            'period: %s, created_from: %s, created_till: %s, p: %s' % ( period, created_from, created_till, p ) \
            )
        return ( created_from, created_till )
    #
    #   Docflow Statistics =======================================================================================
    #
    def getDocflowStatistics( self, REQUEST=None ):
        """
            Returns docflow statistics
        """
        if REQUEST is None:
            REQUEST = check_request( self, REQUEST )

        period, category, implements, scale, enabled_only, cols, state = self._parseInProgressOptions( REQUEST )
        created_from, created_till = self._parseInProgressPeriod( period, REQUEST )

        date_mask = '%Y/%m/%d'
        created_from = created_from
        keys = []

        while True:
            if created_from > created_till:
                break
            key = created_from.strftime(date_mask)
            if key not in keys:
                keys.append( key )
            created_from += scale

        created_till = str(created_till)
        if created_till not in keys and ( scale == 1 or DateTime().strftime(date_mask) != created_till ):
            keys.append( created_till )

        services = getToolByName( self, 'portal_services', None )
        if services is not None:
            IsError, res = services.sync_property( 'get_docflow_stat', state, 'portal_catalog', 1, \
                1, keys, created_till, category, implements, scale, date_mask \
            )
        else:
            IsError = None
            res = []

        res.append( self.get_docflow_stat( 0, keys, created_till, category, implements, scale, date_mask )[1] )

        total = 0
        docflow_info = [ ('Calendar period', 'Docflow Instance', 'Period total', 'Threshold diagram', ), \
                          [], \
                         ('Total',), \
                          [], \
                          [], \
                        ]
        values = {}

        for i, x, t in res:
            docflow_info[1].append(i) # Docflow Instance
            docflow_info[3].append(t) # Total
            for d, v in x:
                if not values.has_key(d):
                    values[d] = []
                values[d].append(v)   # Calendar period values

        total = 0                     # Period total
        value_min = 1000
        value_max = 0

        for x in values.keys():
            s = sum(values[x])
            values[x].append(s)
            if not s:
                continue
            if s < value_min: value_min = s
            if s > value_max: value_max = s
            total += s
        docflow_info[3].append( total )

        values = values.items()       # Sorting
        values.sort()

        res = []                      # Threshold diagram
        threshold = 0
        step = int(value_max/cols) + 1

        docflow_info[4].append( ( value_min, value_max, step, threshold ) )

        colors = CustomPortalColors()
        default_color = '#4F4FFF'

        for key, value in values:
            diagram = []
            if value[-1:][0] > 0:
                for i in range(len(value)):
                    x = int(value[i]/step)
                    if i < len(docflow_info[1]):
                        t = docflow_info[1][i]
                        c = colors[t][5]
                        h = 1
                        p = None
                    else:
                        t = 'total'
                        c = default_color
                        h = 10
                        p = range(int(x/10))
                    diagram.append( {'value':x, 'title':t, 'color':c, 'height':h, 'preview':p} )
                diagram = tuple(diagram)
            res.append( { 'key':key, 'value':value, 'diagram':diagram, 'scale':scale } )

        del values

        return ( total, docflow_info, res, IsError, )

    def get_docflow_stat( self, mode, keys, created_till, category, implements, scale, date_mask ):
        """
            Returns counters of documents created in the current instance
        """
        res = []
        IsError = 0

        portal = self.getPortalObject()
        instance = portal.getId()

        query = {}
        if category:
            query['category'] = category
        if implements:
            query['implements'] = implements
        total = 0

        scale = float(scale - 1)

        for created in keys:
            if created > created_till:
                break
            created_from = DateTime(created)
            query['created'] = { \
                'query' : ( '%s 00:00:00' % created, \
                            '%s 23:59:59' % ( scale and (created_from + scale).strftime(date_mask) or created ) ), \
                'range' : 'min:max' \
            }

            x = self.countResults( REQUEST=None, **query ) or 0
            res.append( ( created, x ) )
            total += x

            #portal_info( '%s.getDocflowStatistics' % self.getId(), '%s : %s' % ( created, x ) )

        return ( IsError, ( instance, res, total, ), )

    def searchDocumentStatistics( self, REQUEST=None, **query ):
        """
            Document statistics collector
        """
        results_by_creators = []
        results_by_categories = []
        results_by_resolutions = []
        results_by_companies = []

        membership = getToolByName( self, 'portal_membership', None )
        workflow = getToolByName( self, 'portal_workflow', None )
        if None in ( membership, workflow, ):
            return ( results_by_creators, results_by_categories, results_by_resolutions, results_by_companies )

        user = membership.getAuthenticatedMember()
        uname = user.getUserName()
        IsManager = user.IsManager()
        IsAdmin = user.IsAdmin()

        unlimit_search = REQUEST is not None and int(REQUEST.get('unlimit_search', None) or 0)
        sort_limit = unlimit_search and default_unlimit or default_searchable_limit

        found_objects = self.searchResults( implements='isHTMLDocument', sort_limit=sort_limit, **query )
        logger.info('searchDocumentStatistics, query: %s, sort_limit: %s' % ( str(query), sort_limit ))

        if not found_objects:
            results_by_creators.append( { 'creator' : uname, 'found_objects' : 0 } )
            return ( results_by_creators, results_by_categories, results_by_resolutions, results_by_companies )

        creator_info = {}
        category_info = {}
        company_info = {}
        task_info = {}

        for x in found_objects:
            if x is None:
                continue
            obj = x.getObject()
            if obj is None or not obj.implements('isDocument'):
                continue

            creator = x['Creator']
            member = membership.getMemberById( creator )

            if not creator or member is None:
                continue
            if not creator_info.has_key( creator ):
                creator_info[ creator ] = 1
            else:
                creator_info[ creator ] += 1

            company = member.getMemberCompany( mode='id' )
            if not company_info.has_key(company):
                company_info[ company ] = [1, []]
            else:
                company_info[ company ][0] += 1
            if not creator in company_info[ company ][1]:
                company_info[ company ][1].append( creator )

            category = x['category']
            if not category:
                continue

            if not category_info.has_key(category):
                category_info[ category ] = [1, {}]
            else:
                category_info[ category ][0] += 1

            state = workflow.getInfoFor( obj, 'state', None )
            if not state:
                continue

            state_info = category_info[ category ][1]
            if not state_info.has_key(state):
                state_info[ state ] = 1
            else:
                state_info[ state ] += 1

        interrupt_thread( self )

        creators = membership.listSortedUserNames( creator_info.keys() )

        for creator in creators:
            user_id = creator['user_id']
            found_objects = creator_info[ user_id ]

            results_by_creators.append( {
                'creator' : user_id,
                'found_objects' : found_objects
                } )

        for category in category_info.keys():
            found_objects = category_info[ category ][0]
            states_info = category_info[ category ][1]

            states = []
            for state in states_info.keys():
                states.append( {
                    'state' : state,
                    'found_objects' : states_info[ state ]
                    } )

            results_by_categories.append( {
                'category' : category,
                'found_objects' : found_objects,
                'states' : states
                } )

        for company in company_info.keys():
            found_objects = company_info[ company ][0]
            company_name = departmentDictionary.getCompanyTitle( company, name=1 )

            results_by_companies.append( {
                'company' : company_name,
                'found_objects' : found_objects,
                'owners' : uniqueValues( company_info[ company ][1] )
                } )

        found_objects = self.searchResults( meta_type='HTMLDocument', hasResolution=1, implements='isVersionable', **query )

        if not found_objects:
            return ( results_by_creators, results_by_categories, results_by_resolutions, results_by_companies )

        for x in found_objects:
            if x is None:
                continue
            obj = x.getObject()
            if obj is None or not obj.implements('isDocument'):
                continue

            state = workflow.getInfoFor( obj, 'state', None )
            if not state:
                continue

            if not task_info.has_key(state):
                task_info[ state ] = 1
            else:
                task_info[ state ] += 1

        for state in task_info.keys():
            found_objects = task_info[ state ]

            results_by_resolutions.append( {
                'state' : state,
                'found_objects' : found_objects
                } )

        return ( results_by_creators, results_by_categories, results_by_resolutions, results_by_companies )
    #
    #   Accessible documents =====================================================================================
    #
    def getMyDocumentsInProgress( self, REQUEST=None, member=None, check_only=None ):
        """
            Returns progress list of the documents for current user (created by member only, my documents)
        """
        results = {}
        now = DateTime()

        membership = getToolByName( self, 'portal_membership' )
        metadata = getToolByName( self, 'portal_metadata' )
        username = member or membership.getAuthenticatedMember().getUserName()

        if REQUEST is not None:
            period = int(REQUEST.get('period', '0'))
        else:
            period = None

        indexes = {}
        indexes['Creator'] = [ username ]
        indexes['implements'] = [ 'isVersionable' ]
        if period:
            days = period_to_days( period )
            if days > 0:
                created_till = DateTime()
                created_from = created_till - float(days * 3600 * 24) / 86400
                indexes['created'] = { 'query' : ( created_from, created_till and created_till + 0.99999 ), 'range' : 'min:max' }
            else:
                now = DateTime()
                created_from = DateTime(int(now.strftime('%Y')), int(now.strftime('%m')), int(now.strftime('%d')))
                indexes['created'] = { 'query' : created_from, 'range' : 'min' }

        documents = self.searchResults( type='query', REQUEST=REQUEST, **indexes )

        if check_only:
            if not documents: return 0
        elif not documents:
            return ( 0, [] )

        for r in documents:
            obj = r.getObject()
            if obj is None:
                continue
            if not username in membership.getObjectOwners( obj ):
                continue
            if not ( obj.implements('isDocument') or obj.implements('isVersionable') ):
                continue

            category = obj.Category()

            if not results.has_key(category):
                results[category] = []

            info = {}

            info['document_title'] = obj.Title().strip()
            obj_description = obj.Description().strip()
            info['document_description'] = info['document_title'] != obj_description and obj_description
            info['creator'] = obj.Creator()
            info['creation_date'] = r['created']
            info['recipient_agency'] = CustomAttributeValue( obj, 'recipient_agency' )

            executor = CustomAttributeValue( obj, 'executor' )
            if executor:
                if type(executor) is StringType:
                    executor = [ executor ]
            else:
                executor = []
            info['executor'] = list( filter( None, uniqueValues( executor ) ) )

            signatory = CustomAttributeValue( obj, 'signatory' )
            if signatory:
                if type(signatory) not in ( ListType, TupleType ):
                    signatory = [ signatory ]
                info['signatory'] = [ x for x in signatory if x not in info['executor'] ]
            else:
                info['signatory'] = []

            info['registry_id'] = obj.registry_ids() and obj.getInfoForLink( mode=2 ) or ''
            info['resolution'] = obj.getDocumentResolution( no_absolute=1 )
            info['view_url'] = obj.absolute_url( canonical=1, no_version=1 ) + '/view?expand=1'
            info['new'] = 0

            try: effective_date = int((now - info['creation_date']) * 10**8)
            except: effective_date = 0

            info['sortkey'] = ( '0000000000' + str(effective_date) )[ -10: ]
            results[ category ].append( info )

            interrupt_thread( self )

        if check_only: return len(results.keys()) > 0 and 1 or 0

        res = []
        custom_categories = CustomCategoryIds()
        max_categories = len(custom_categories)

        for category in results.keys():
            x = max_categories
            for n in range(0, max_categories):
                if category == custom_categories[n]:
                    x = n
                    break

            category_title = ( x < max_categories and category[4:]+'s' ) or 'Another Documents'
            res.append( ( x, category_title, results[ category ] ) )

        res.sort()

        results = []
        total = 0

        for x, category, documents in res:
            results.append( { 'category' : category, 'documents' : documents } )
            total += len( documents )

        if check_only: return total > 0 and 1 or 0
        return ( total, results )

    def getAccessibleDocuments( self, REQUEST=None, **kw ):
        """ 
            Returns custom accessible documents list
        """
        membership = getToolByName( self, 'portal_membership', None )
        if membership is None:
            return

        user = membership.getAuthenticatedMember()
        uname = user.getUserName()
        IsManager = user.IsManager()
        IsAdmin = user.IsAdmin()

        membership.updateLoginTime( uname )

        total_objects, documents = self.searchResults( type='documents', with_limit=1, REQUEST=REQUEST, \
                       implements='isHTMLDocument', sort_on='created', sort_order='reverse', \
                       **kw )

        if not IsManager and documents:
            res = []
            system_objects = CustomSystemObjects()
            for x in documents:
                try: path = x.getPath()
                except: continue
                IsSystem = 0
                for key in system_objects:
                    if path.find( key ) > -1:
                        IsSystem = 1
                        break
                if not IsSystem:
                    res.append( x )
            return ( total_objects, res, )

        return ( total_objects, documents, )

    def getMyDocuments( self, REQUEST=None, **kw ):
        """ 
            Returns member's private documents list
        """
        membership = getToolByName( self, 'portal_membership', None )
        if membership is None:
            return

        user = membership.getAuthenticatedMember()
        uname = user.getUserName()

        total_objects, documents = self.searchResults( type='documents', with_limit=1, REQUEST=REQUEST, \
                       Creator=uname, implements='isHTMLDocument', sort_on='created', sort_order='reverse', \
                       **kw )

        return ( total_objects, documents, )

    def getMyShortcuts( self, REQUEST=None, **kw ):
        """ 
            Returns member's shortcut list
        """
        membership = getToolByName( self, 'portal_membership', None )
        if membership is None:
            return
        personal_folder_path = membership.getPersonalFolderPath(0)
        if not personal_folder_path:
            return (0, [])

        user = membership.getAuthenticatedMember()
        uname = user.getUserName()

        favorites_path = personal_folder_path + '/favorites/%'

        total_objects, documents = self.searchResults( type='documents', with_limit=1, REQUEST=REQUEST, \
                       path=favorites_path, meta_type='Shortcut', sort_on='created', sort_order='reverse', \
                       **kw )

        return ( total_objects, documents, )

    def searchRegistries( self, REQUEST=None, **kw ):
        """
            Returns current member registries list
        """
        interrupt_thread( self )

        indexes = {}
        indexes['meta_type'] = 'Registry'

        if self._IsDebug():
            portal_debug( '%s.searchRegistries' % self.getId(), 'indexes: %s' % indexes )

        results = self.searchResults( REQUEST=REQUEST, sort_on='Title', **indexes )
        if not results: return None

        membership = getToolByName( self, 'portal_membership', None )
        current_registry = kw and kw.get('current_registry') or 1
        registries = []

        for x in results:
            if x is None:
                continue
            obj = x.getObject()
            if obj is None or (current_registry and not obj.isCurrentRegistry()) or \
               not membership.checkPermission('Add portal content', obj):
                continue
            registries.append( x )

        return registries

    def searchResolutions( self, REQUEST=None ):
        """
            Returns current member resolutions list
        """
        interrupt_thread( self )

        uname = REQUEST is not None and REQUEST.get('member', None) or _getAuthenticatedUser(self).getUserName()
        resolutions = []

        indexes = {}
        indexes['hasResolution'] = 1
        indexes['implements'] = ['isVersionable']
        indexes['types'] = 'HTMLDocument'
        indexes['query_items'] = []

        if self._IsDebug():
            portal_debug( '%s.searchResolutions' % self.getId(), 'indexes: %s' % indexes )

        res = self.searchResults( REQUEST=REQUEST, **indexes )
        if not res: return None

        for x in res:
            if x is None: continue
            ob = x.getObject()
            if ob is None or not ob.implements('isDocument'):
                continue

            for task in ob.followup.getBoundTasks():
                if task.isFinalized() or task.getTaskResolution() is None:
                    continue
                if uname in task.listInvolvedUsers( recursive=1 ): # or uname in task.Supervisors():
                    resolutions.append( task )
                    break

        return resolutions

    security.declarePublic( 'unrestrictedSearchDepartment' )
    def unrestrictedSearchDepartment( self, nd_uid ):
        """
            Search department folder
        """
        interrupt_thread( self )

        results = ZCatalog.searchResults( self, nd_uid=nd_uid )
        if results:
            ob = results[0].getObject()
            if ob:
                res = {}
                res['Title'] = ob.title_or_id()
                res['url'] = ob.absolute_url()
                return res
        return None
    #
    #   Utilities ================================================================================================
    #
    def searchAttributeValues( self, REQUEST=None, category=None, field=None ):
        """
            Returns attribute's implemented values list, such as textarea types
        """
        if not ( category and field ):
            return []

        membership = getToolByName( self, 'portal_membership', None )
        user = membership.getAuthenticatedMember()
        uname = user.getUserName()
        IsManager = user.IsManager()
        IsVip = user.IsVip()

        ps = getToolByName( self, 'portal_properties', None )
        interval = ps is not None and ps.getProperty( 'created_search_interval' ) or 360

        created = ( DateTime()-interval, DateTime()+1, )

        query = {}
        query['meta_type'] = 'HTMLDocument'
        query['category'] = category
        query['allowedRolesAndUsers'] = uniqueValues(self._listAllowedRolesAndUsers( user ))

        if not ( IsManager or IsVip ):
            query['Creator'] = uname

        catalog = self._catalog
        query = catalog._parse_query( CatalogSearchArgumentsMap(REQUEST, query) )

        res = view( catalog, 'search_attributes', table='CategoryAttributes', attr=field, created=created, query=query )

        interrupt_thread( self )

        if res: res.sort()
        return res

    def searchCategoryObjects( self, category=None, search=None, REQUEST=None ):
        """
            Returns category object's implemented values list
        """
        if not category:
            return []

        query = {}
        query['implements'] = 'isDocument'
        query['category'] = category
        if search:
            query['SearchableText'] = search

        res = [ ( x['Title'], x['id'], x['nd_uid'], x['Description'], x.getPath() ) \
                for x in self.unrestrictedSearch( **query ) \
                    if x['nd_uid'] ]

        res.sort()
        res = [ { 'id' : id, 'uid' : uid, 'title' : title, 'description' : description, 'path' : path } \
                for title, id, uid, description, path in res ]

        interrupt_thread( self )

        return res

    def isAttrValueExist( self, category_id, attr_id, value, except_obj_uid=None):
        """
            Check for attribute 'attr_id' value is exist for all document category 'category_id'
            except document with 'except_obj_uid' uid.
            Include document the user is not allowed to see.
            Document versions ignored.

            Parameters:
                category_id - document category id
                attr_id     - attribute id
                value       - attribute value for check
                except_obj_uid - document uid to except from check (e.g. created or edited document)

            Result:
                boolean 
        """
        query={'implements' : ['isDocument'],
               'meta_type'  : ['HTMLDocument'],
               'category'   : [category_id],
               'CategoryAttributes':[{ 'attributes':["%s/%s" %(category_id,attr_id)], 'query':value }]
              }
        results = self.unrestrictedSearch( **query )
        results = [ item for item in results if item['nd_uid'] != except_obj_uid ]
        if results:
            return 1
        return 0

    __call__ = searchResults

InitializeClass( CatalogTool )


def period_to_days( period ):
    return period == 7 and 360 or period == 6 and 180 or period == 5 and 90 or \
           period == 4 and 30  or period == 3 and 14  or period == 2 and 7  or \
           1
