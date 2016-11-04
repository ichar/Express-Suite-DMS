"""
Catalog tool
$Id: CatalogTool.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 26/02/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import sys
from types import ListType, TupleType, DictType, StringType
from zLOG import LOG, DEBUG, INFO

import threading
from AccessControl import ClassSecurityInfo
from Acquisition import aq_base, aq_get
from DateTime import DateTime
from ZPublisher.HTTPRequest import record

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.CatalogTool import CatalogTool as _CatalogTool, \
     IndexableObjectWrapper as _IndexableObjectWrapper
from Products.CMFCore.utils import _checkPermission, _getAuthenticatedUser, getToolByName

from Products.ZCatalog.ZCatalog import ZCatalog
from ZODB.POSException import ConflictError, ReadConflictError

import Config
from SearchProfile import SearchQuery
from SimpleObjects import ToolBase
from DepartmentDictionary import departmentDictionary
from PortalLogger import portal_log
from TransactionManager import interrupt_thread

from Utils import InitializeClass, getLanguageInfo, getClientStorageType, getContainedObjects, \
     uniqueValues, uniqueItems

from CustomDefinitions import CustomSystemObjects, CustomCategoryIds
from CustomObjects import CustomAttributeValue

from logging import getLogger
logger = getLogger( 'CatalogTool' )

uncategorial_types = ( \
    'Registry', 'Task Item', 'Discussion Item', 'Heading', 'FS Folder', 'Search Profile', 'Image Attachment',
    'File Attachment', 'File', 'Shortcut',
    )

timeout = 1.0

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


class CatalogTool( ToolBase, _CatalogTool ):
    """
        Portal catalog
    """
    _class_version = 1.0

    meta_type = 'ExpressSuite Catalog Tool'

    security = ClassSecurityInfo()

    manage_options = _CatalogTool.manage_options # + ToolBase.manage_options

    _catalog_indexes = (
              ('Title', 'FieldIndex', None)
            , ('Subject', 'KeywordIndex', None)
            , ('Description', 'FieldIndex', None)
            , ('Creator', 'FieldIndex', None)
            , ('Date', 'FieldIndex', None)
            , ('created', 'FieldIndex', None)
            , ('effective', 'FieldIndex', None)
            , ('expires', 'FieldIndex', None)
            , ('modified', 'FieldIndex', None)
            , ('allowedRolesAndUsers', 'KeywordIndex', None)
            , ('state', 'FieldIndex', None)
            , ('in_reply_to', 'FieldIndex', None)
            , ('registry_ids', 'KeywordIndex', None)
            , ('nd_uid', 'FieldIndex', None)
            , ('category', 'FieldIndex', None)
            , ('meta_type', 'FieldIndex', None)
            , ('portal_type', 'FieldIndex', None)
            , ('id', 'FieldIndex', None)
            , ('path','PathIndex', None)
            , ('parent_path', 'FieldIndex', None)
            , ('implements', 'KeywordIndex', None)
            , ('hasBase', 'KeywordIndex', None)
            , ('CategoryAttributes', 'AttributesIndex')
            , ('archive', 'FieldIndex', None)
            , ('hasResolution', 'FieldIndex', None)
    )

    _explicit_indexes = ( 'CategoryAttributes', 'Subject', 'title', 'in_reply_to', \
                          'Date', 'allowedRolesAndUsers', )

    _catalog_metadata = (
              'id'
            , 'Subject'
            , 'Title'
            , 'Description'
            , 'Type'
            , 'state'
            , 'Creator'
            , 'Date'
            , 'getIcon'
            , 'created'
            , 'effective'
            , 'expires'
            , 'modified'
            , 'CreationDate'
            , 'EffectiveDate'
            , 'ExpirationDate'
            , 'ModificationDate'
            , 'registry_ids'
            , 'category'
            , 'meta_type'
            , 'portal_type'
            , 'nd_uid'
            , 'implements'
            , 'CategoryAttributes'
            , 'archive'
            , 'hasResolution'
    )

    def __init__( self ):
        """
            Initialize class instance
        """
        ZCatalog.__init__( self, self.getId() )
        ToolBase.__init__( self )

    def setupIndexes( self, idxs=[], check=None, reindex=None, REQUEST=None ):
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
        changed = 0

        # Setup new columns
        for column in self.enumerateColumns():
            if column not in self.schema():
                if check: return 1
                changed = 1
                self.addColumn(column)

        # Setup new indexes
        for item in self.enumerateIndexes():
            index, typ = item[0:2]
            extra = len(item) == 3 and item[2]
            if index not in self.indexes():
                if check: return 1
                changed = 1
                self.addIndex( index, typ, extra )
                reindexed.append( index )

        # Remove redundant indexes/columns
        for column in self.schema():
            if column not in self.enumerateColumns():
                if check: return 1
                changed = 1
                self.delColumn(column)

        for index in self.indexes():
            if index not in map(lambda x: x[0], self.enumerateIndexes()):
                if check: return 1
                changed = 1
                self.delIndex( index )

        if reindex and reindexed:
            for index in reindexed:
                try:
                    self.reindexIndex( index, REQUEST=REQUEST )
                except:
                    raise
                logger.info("setupIndexes = Index: %s reindexed" % index)

        return changed

    def enumerateIndexes( self ):
        #   Return a list of ( index_name, type, extra ) pairs for the initial
        #   index set.
        idxs = list( self._catalog_indexes )

        try:
            from Products.TextIndexNG2 import TextIndexNG
            text_index_name = 'TextIndexNG2'
            text_index_extra = record()

            properties = getToolByName( self, 'portal_properties', None )
            if properties is not None:
                stemmer = properties.getProperty('stemmer')
            else:
                stemmer = 'russian'

            #text_index_extra.use_stemmer = stemmer
            text_index_extra.default_encoding = getLanguageInfo( self )['python_charset']
            text_index_extra.splitter_separators = '.+-_@'
            text_index_extra.autoexpand = 1
            text_index_extra.truncate_left = 1

        except ImportError:
            text_index_name = 'TextIndex'
            text_index_extra = None

        idxs += (('SearchableText', text_index_name, text_index_extra), )
        idxs += (('title', text_index_name, text_index_extra), )

        return idxs

    def explicitIndexes( self ):
       # Return a sequence of explicit indexes
       return self._explicit_indexes

    def enumerateColumns( self ):
       # Return a sequence of schema names to be cached
       return self._catalog_metadata

    security.declareProtected( CMFCorePermissions.ManagePortal, 'lockCatalog' )
    def lockCatalog( self ):
        uname = _getAuthenticatedUser(self).getUserName()
        logger.info('lockCatalog locked by %s' % uname)
        self._v_locked = 1

    def check_catalog_locked( self ):
        return getattr( self, '_v_locked', None ) and 1 or 0

    security.declareProtected( CMFCorePermissions.ManagePortal, 'unlockCatalog' )
    def unlockCatalog( self ):
        uname = _getAuthenticatedUser(self).getUserName()
        logger.info('unlockCatalog unlocked by %s' % uname )
        self._v_locked = 0

    def addIndex( self, name, type, extra=None ):
        ZCatalog.addIndex( self, name, type, extra )
        idx = self._catalog.getIndex( name )
        if hasattr( aq_base( idx ), 'manage_afterAdd' ):
            idx.manage_afterAdd( idx, self._catalog )

    def delIndex( self, name ):
        idx = self._catalog.getIndex( name )
        if hasattr( aq_base( idx ), 'manage_beforeDelete' ):
            idx.manage_beforeDelete( idx, self._catalog )

        ZCatalog.delIndex( self, name )

    def wrapOb( self, object ):
        wf = getattr( self, 'portal_workflow', None )
        if wf is not None:
            vars = wf.getCatalogVariablesFor( object )
        else:
            vars = {}
        w = IndexableObjectWrapper( vars, object )
        return w

    def catalog_object( self, object, uid, idxs=[], update_metadata=1, pghandler=None, force=None ):
        # Wraps the object with workflow and accessibility information just before cataloging
        if self.check_catalog_locked():
            return
        w = self.wrapOb(object)
        #portal_log( self, 'CatalogTool', 'catalog_object', 'uid', uid )
        ZCatalog.catalog_object( self, w, uid, idxs, update_metadata=update_metadata, \
                                 pghandler=pghandler, force=force )

    def uncatalog_object( self, uid ):
        # Wrapper around catalog just before uncataloging
        if self.check_catalog_locked():
            return
        #portal_log( self, 'CatalogTool', 'uncatalog_object', 'uid', uid )
        ZCatalog.uncatalog_object( self, uid )

    def indexObject( self, object ):
        """
            Adds to catalog
        """
        #portal_log( self, 'CatalogTool', 'indexObject', 'path', object.physical_path() )
        _CatalogTool.indexObject(self, object)

    def unindexObject( self, object ):
        """
            Removes from catalog
        """
        #portal_log( self, 'CatalogTool', 'unindexObject', 'path', object.physical_path() )
        _CatalogTool.unindexObject(self, object)

    def reindexObject( self, object, idxs=[], recursive=None ):
        """
            Updates catalog after object data has changed
        """
        obs = [ object ]
        if recursive:
            obs.extend( getContainedObjects(object) )
        for ob in obs:
            #portal_log( self, 'CatalogTool', 'reindexObject', 'path', ( ob.physical_path(), idxs ) )
            _CatalogTool.reindexObject( self, self.wrapOb(ob), idxs )

    def _containment_onAdd( self, item, container ):
        self._catalog.clear()
    #
    # Catalog implementary functions ================================================================================
    #
    security.declarePublic( 'attachmentSearchEnabled' )
    def attachmentSearchEnabled( self ):
        """ """
        return Config.AttachmentSearchable

    def getQuery( self, id=None, profile=None, copy=None, REQUEST=None ):
        """
            Returns existing (by id/profile id) or new seach query, implemented by followed executeQuery method
        """
        if REQUEST is None: 
            REQUEST = aq_get( self, 'REQUEST' )

        if id:
            query = REQUEST.SESSION.get( ( 'search', id ) )
            #if query is None:
            #    raise KeyError, id
        elif profile:
            ob = self.getObjectByUid( profile, 'isSearchProfile' )
            if ob is None:
                raise KeyError, profile
            query = ob.getQuery()
        else:
            IsError = 0
            query = SearchQuery()
            try:
                REQUEST.SESSION.set( ( 'search', query.getId() ), query )
            except:
                IsError = 1
                del query

            if IsError:
                uname = _getAuthenticatedUser(self).getUserName()
                logger.error('getQuery cannot set session for member: %s' % uname)
                return None
            copy = 0

        if copy and query is not None:
            query = query.clone()
            REQUEST.SESSION.set( ( 'search', query.getId() ), query )

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

        IsGroup = 0
        if REQUEST is not None:
            indexes['sort_on'] = kw.get('sort_on')
            indexes['sort_order'] = kw.get('sort_order')
            if REQUEST.get('group', None):
                properties = getToolByName( self, 'portal_properties', None )
                try: sort_limit = int(properties.getProperty('sort_limit'))
                except: sort_limit = None
                indexes['sort_limit'] = sort_limit or 2000
                IsGroup = 1

        indexes = uniqueItems( indexes )

        portal_log( self, 'CatalogTool', 'executeQuery', 'indexes', indexes )
        total_objects, results = self.searchResults( type='query', with_limit=1, REQUEST=REQUEST, **indexes )
        results = query.filter( results, parent=self.parent() )

        if results and IsGroup:
            return ( total_objects, self.groupResults( results, REQUEST, **kw ) )
        else:
            return ( total_objects, self.sortResults( results, **kw ) )

    def searchRegistries( self, REQUEST=None, **kw ):
        """
            Returns current member registries list
        """
        interrupt_thread( self )

        indexes = {}
        indexes['meta_type'] = 'Registry'

        portal_log( self, 'CatalogTool', 'searchRegistries', 'indexes', indexes )
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

        portal_log( self, 'CatalogTool', 'searchResolutions', 'indexes', indexes )
        results = self.searchResults( REQUEST=REQUEST, **indexes )
        if not results: return None

        for x in results:
            if x is None:
                continue
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
            query['archive'] = 0
        else:
            # Archive
            if type == 'documents':
                query['implements'] = 'isHTMLDocument'
                query['archive'] = 1

        return self.unrestrictedSearch( REQUEST, with_limit=with_limit, **query )

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
        if membership is None or workflow is None:
            return ( results_by_creators, results_by_categories, results_by_resolutions, results_by_companies )

        user = membership.getAuthenticatedMember()
        uname = user.getUserName()
        IsManager = user.IsManager()
        IsAdmin = user.IsAdmin()

        found_objects = self.searchResults( meta_type='HTMLDocument', **query )

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
            creator = obj.Creator()
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

            category = obj.Category()
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

        found_objects = self.searchResults( meta_type='HTMLDocument', hasResolution=1, implements=['isVersionable'], **query )

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

            interrupt_thread( self )

        for state in task_info.keys():
            found_objects = task_info[ state ]

            results_by_resolutions.append( {
                'state' : state,
                'found_objects' : found_objects
                } )

        return ( results_by_creators, results_by_categories, results_by_resolutions, results_by_companies )

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
            days = period == 5 and 90 or period == 4 and 30 or period == 3 and 14 or period == 2 and 7 or 0
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
                info['executor'] = type(executor) not in ( ListType, TupleType ) and [ executor ] or executor
            else:
                info['executor'] = []

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

    def getAccessibleDocuments( self, REQUEST=None ):
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
                            sort_limit=50 )

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

    def getMyDocuments( self, REQUEST=None ):
        """ 
            Returns member's private documents list
        """
        membership = getToolByName( self, 'portal_membership', None )
        if membership is None:
            return

        user = membership.getAuthenticatedMember()
        uname = user.getUserName()

        total_objects, documents = self.searchResults( type='documents', with_limit=1, REQUEST=REQUEST, \
                            creator=uname, implements='isHTMLDocument', sort_on='created', sort_order='reverse', \
                            sort_limit=50 )

        return ( total_objects, documents, )

    def searchAttributeValues( self, REQUEST=None, category=None, field=None ):
        """
            Returns attribute's implemented values list, such as textarea types
        """
        results = []

        if not ( category and field ):
            return results

        membership = getToolByName( self, 'portal_membership', None )
        user = membership.getAuthenticatedMember()
        uname = user.getUserName()
        IsManager = user.IsManager()
        IsAdmin = user.IsAdmin()

        prptool = getToolByName( self, 'portal_properties', None )
        interval = prptool and prptool.getProperty( 'created_search_interval' ) or 60

        indexes = {}
        indexes['category'] = category
        indexes['created'] = { 'query' : ( DateTime()-interval, DateTime() ), 'range' : 'min:max' }

        if not IsAdmin:
            indexes['Creator'] = [ uname ]

        found_objects = self.searchResults( meta_type='HTMLDocument', **indexes )

        if not found_objects:
            return results

        for x in found_objects:
            value = ( str(x['CategoryAttributes'][field]) ).strip()
            if value and value not in ['None'] and value not in results:
                results.append( value )

        interrupt_thread( self )

        results.sort()
        return results

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

    security.declarePrivate( 'unrestrictedSearch' )
    def unrestrictedSearch( self, REQUEST=None, check_permission=0, with_limit=None, **kw ):
        """
            Run ZCatalog searching 
        """
        interrupt_thread( self )

        results = []
        total_objects = 0
        batch_start = batch_size = batch_length = 0

        try:
            if with_limit:
                if REQUEST is not None and not kw.has_key('sort_limit'):
                    batch_start = int(REQUEST.get('batch_start', 1))
                    batch_size = int(REQUEST.get('batch_size', 10))
                    batch_length = int(REQUEST.get('batch_length', 0)) or batch_size
                    sort_limit = batch_start + 2 * batch_length + 1
                    kw['sort_limit'] = sort_limit
                kw['rs_type'] = 1
            if kw is not None and kw.has_key('allowedRolesAndUsers'):
                kw['allowedRolesAndUsers'] = uniqueValues(kw['allowedRolesAndUsers'])
            #logger.info("unrestrictedSearch batch:%s-%s-%s\nkw:%s" % ( batch_start, batch_size, batch_length, kw ))
            #LOG('%s.unrestrictedSearch' % self.getId(), DEBUG, "batch:%s-%s-%s\nkw:%s" % ( batch_start, batch_size, batch_length, kw ))

            x = apply( ZCatalog.searchResults, (self, REQUEST), kw )

            #logger.info('unrestrictedSearch x: %s' % len(x))
            if kw.get('rs_type', 0):
                if type(x) is TupleType:
                    total_objects, results = x
                else:
                    total_objects = len(x)
                    results = x
                #logger.info('unrestrictedSearch total_objects: %s, results: %s' % ( total_objects, len(results) ))
                return ( total_objects, results )
            else:
                return x

        except ReadConflictError, message:
            raise
        except:
            #logger.error('unrestrictedSearch CATALOG SEARCH ERROR', exc_info=True)
            raise

    __call__ = searchResults

    def sortResults( self, results, unique=None, **kw ):
        """
            Sort results from the previous searches.

            If 'merge' argument is not None, duplicate records
            are removed from the results set
        """
        #logger.info('sortResults len results:%s, sort_on: %s, sort_order: %s' % ( len(results), kw.get('sort_on'), kw.get('sort_order') ))
        catalog = self._catalog

        if unique:
            results = self.uniqueResults(results)

        if not hasattr( catalog, '_getSortIndex' ):
            # Zope 2.5.x
            return results

        index = catalog._getSortIndex( kw )
        if index is None:
            return results
        index_name = index.getId()

        limit = catalog._get_sort_attr( 'limit', kw )
        order = catalog._get_sort_attr( 'order', kw )
        reverse = order and order.lower() in ('reverse', 'descending') and 1 or 0
        #logger.info('sortResults len results:%s, index:%s' % ( len(results), index_name ) )

        if index_name == 'Creator':
            membership = getToolByName( self, 'portal_membership', None )
            if membership is not None:
                results = list(results)
                results.sort( lambda x, y, f=membership.getMemberName: cmp( f(x['Creator']), f(y['Creator']) ) )
                if reverse:
                    results.reverse()

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
        #logger.info('groupResultsresults: %s' % len(results))
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
                #logger.info('groupResults ungroup: %s, meta_type: %s' % ( rid, r['meta_type'] ))

        results = group_map.values()
        results.sort()
        if reverse:
            results.reverse()

        #logger.info('groupResults except_items: %s, none_items: %s' % ( except_items, none_items ))
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
                    logger.error('getObjectByUid uid: %s' % uid, exc_info=True)
                    #pass
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
                    logger.error('unrestrictedGetObjectByUid uid: %s' % uid, exc_info=True)
                    #pass
            else:
                #logger.info('unrestrictedGetObjectByUid not found uid: %s' % uid)
                pass
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

InitializeClass( CatalogTool )
