"""
Followup actions tool with MySQL supporting
$Id: ZSQLFollowupActionsTool.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 09/06/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import re, sys, traceback
from string import join
from types import StringType, ListType, TupleType, DictType
from DateTime import DateTime

import xmlrpclib

from Globals import DTMLFile
from Acquisition import Implicit, aq_get, aq_base, aq_parent, aq_inner
from AccessControl.PermissionRole import rolesForPermissionOn
from AccessControl import ClassSecurityInfo
from ExtensionClass import Base

import transaction

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.Expression import Expression
from Products.CMFCore.utils import getToolByName, mergedLocalRoles, _getAuthenticatedUser, \
     _checkPermission, _dtmldir

from ZODB.POSException import ConflictError, ReadConflictError

from Products.ZSQLCatalog.ZSQLCatalog import ZSQLCatalog as ZCatalog
from Products.ZSQLCatalog.Catalog import Catalog, CatalogError
from Products.PageTemplates.Expressions import getEngine

from ZSQLCatalogTool import CatalogTool

import Config
from ISAMSupporter import ISAMList
from HTMLDocument import HTMLDocument
from HTMLCleanup import HTMLCleaner
from SimpleObjects import Persistent, ToolBase
from TaskBrains import listTaskBrains, getTaskBrains
from TaskItem import TaskItem, TaskItemContainer
from PortalLogger import portal_log, portal_info, portal_debug, portal_error
from TransactionManager import CommitThread, interrupt_thread

from DepartmentDictionary import departmentDictionary

from Utils import InitializeClass, refreshClientFrame, SequenceTypes, \
     getObjectByUid, getContainedObjects, getClientStorageType, getPlainText, get_param, \
     formatComments, formatFloat, uniqueValues, makeTuple

from CustomDefinitions import portalConfiguration, CustomCategoryIds, CustomTaskStates
from CustomObjects import CustomAttributeValue

from logging import getLogger
logger = getLogger( 'ZSQLFollowupActionsTool' )


task_states              = CustomTaskStates()
commission_category      = 'BaseCommission'
default_searchable_limit = 1000
default_visible_limit    = 100
default_unlimit          = 1000000


default_followup_params = { \
    # Incoming tasks ---------------------------------------------------------------------------------------------
    'incoming_total'     : {
        'supervised':0, 'isEnabled':1, 'InvolvedUsers':'%(member_id)s', 'path':'%(path)s', \
    },
    'incoming_new'       : {
        'supervised':0, 'isEnabled':1, 'isFinalized':0, 'InvolvedUsers':'%(member_id)s', 'StateKeys':'pending:%(member_id)s', 'path':'%(path)s', \
    },
    'incoming_seen'      : {
        'supervised':0, 'isEnabled':1, 'isFinalized':0, 'InvolvedUsers':'%(member_id)s', 'StateKeys':'pending:%(member_id)s', 'SeenBy':'%(member_id)s', 'path':'%(path)s', \
    },
    'incoming_current'   : {
        'supervised':0, 'isEnabled':1, 'isFinalized':0, 'InvolvedUsers':'%(member_id)s', 'StateKeys':{ 'query':['user_responded:%(member_id)s', 'closed_report:%(member_id)s'], 'operator':'AND NOT' }, 'path':'%(path)s', \
    },
    'incoming_closed'    : {
        'supervised':0, 'isEnabled':1, 'isFinalized':0, 'InvolvedUsers':'%(member_id)s', 'StateKeys':'closed_report:%(member_id)s', 'path':'%(path)s', \
    },
    'incoming_finalized' : {
        'supervised':0, 'isEnabled':1, 'isFinalized':1, 'InvolvedUsers':'%(member_id)s', 'path':'%(path)s', \
    },
    # Outgoing tasks ---------------------------------------------------------------------------------------------
    'outgoing_total'     : {
        'supervised':0, 'isEnabled':1, 'Creator':'%(member_id)s', 'path':'%(path)s', \
    },
    'outgoing_new'       : {
        'supervised':0, 'isEnabled':1, 'isFinalized':0, 'Creator':'%(member_id)s', 'StateKeys':'task_not_started', 'path':'%(path)s', \
    },
    'outgoing_seen'      : {
        'supervised':0, 'isEnabled':1, 'isFinalized':0, 'Creator':'%(member_id)s', 'StateKeys':'task_not_started', 'SeenBy':'%(member_id)s', 'path':'%(path)s', \
    },
    'outgoing_started'   : {
        'supervised':0, 'isEnabled':1, 'isFinalized':0, 'Creator':'%(member_id)s', 'StateKeys':'task_started', 'path':'%(path)s', \
    },
    'outgoing_current'   : {
        'supervised':0, 'isEnabled':1, 'isFinalized':0, 'Creator':'%(member_id)s', 'StateKeys':{ 'query':['task_started', 'task_closed'], 'operator':'AND NOT' }, 'path':'%(path)s', \
    },
    'outgoing_closed'    : {
        'supervised':0, 'isEnabled':1, 'isFinalized':0, 'Creator':'%(member_id)s', 'StateKeys':'task_closed', 'path':'%(path)s', \
    },
    'outgoing_finalized' : {
        'supervised':0, 'isEnabled':1, 'isFinalized':1, 'Creator':'%(member_id)s', 'path':'%(path)s', \
    },
    # Supervised tasks -------------------------------------------------------------------------------------------
    'supervised_total'   : {
        'supervised':1, 'isEnabled':1, 'Supervisors':'%(member_id)s', 'path':'%(path)s', \
    },
    'supervised_new'     : {
        'supervised':1, 'isEnabled':1, 'isFinalized':0, 'Supervisors':'%(member_id)s', 'StateKeys':{ 'query':'review:%(member_id)s', 'operator':'NOT' }, 'path':'%(path)s', \
    },
    'supervised_seen'    : {
        'supervised':1, 'isEnabled':1, 'isFinalized':0, 'Supervisors':'%(member_id)s', 'SeenBy':'%(member_id)s', 'path':'%(path)s', \
    },
    'supervised_not_seen': {
        'supervised':1, 'isEnabled':1, 'Supervisors':'%(member_id)s', 'SeenBy':{ 'query':'%(member_id)s', 'operator':'NOT' }, 'path':'%(path)s', \
    },
    'supervised_reviewed': {
        'supervised':1, 'isEnabled':1, 'Supervisors':'%(member_id)s', 'StateKeys':'review:%(member_id)s', 'path':'%(path)s', \
    },
    # Kicked tasks -----------------------------------------------------------------------------------------------
    'kicked_total'       : {
        'supervised':0, 'isEnabled':1, 'isFinalized':0, 'KickedUsers':'%(member_id)s', \
    },
    'kicked_new'         : {
        'supervised':0, 'isEnabled':1, 'isFinalized':0, 'KickedUsers':'%(member_id)s', 'SeenBy':{ 'query':'%(member_id)s', 'operator':'NOT' },
    },
}

class IndexableObjectWrapper:

    def __init__( self, vars, ob ):
        self.__vars = vars
        self.__ob = ob

    def __getattr__( self, name ):
        vars = self.__vars
        if vars.has_key(name):
            return vars[name]
        return getattr(self.__ob, name)

    def allowedRolesAndUsers( self ):
        """
            Return a list of roles and users with View permission.
            Used by PortalCatalog to filter out items you're not allowed to see.
        """
        ob = self.__ob
        allowed = {}
        for r in rolesForPermissionOn('View', ob):
            allowed[r] = 1
        localroles = mergedLocalRoles(ob)
        for user, roles in localroles.items():
            for role in roles:
                if allowed.has_key(role):
                    allowed['user:' + user] = 1
        if allowed.has_key('Owner'):
            del allowed['Owner']
        return list(allowed.keys())


class SeenByLog( Persistent, Implicit, Base ):
    """
    Lightweight user task seens storage. It is not aware of the
    task type brains and treats seens as a list data.
    """

    id = 'SeenByLog'

    def __init__( self ):
        """ Initialize class instance
        """
        Persistent.__init__( self )
        self._values = ISAMList( self.getId(), Config.default_seen_by_log_columns )

    def getId( self ):
        return getattr(self, 'id', None)

    def setup( self, force=None ):
        """ Initialize ISAM class instance
        """
        if not force and Config.CheckZODBBeforeInstall:
            if getattr(self, '_values', None) is not None:
                return

        values = ISAMList( self.getId(), Config.default_seen_by_log_columns )

        value = getattr(self, '_pages_seen_by', {}).items()
        value.sort()

        for x, v in value:
            try: 
                ob = self.unrestrictedTraverse( x )
                uid = ob.getUid()
            except: 
                continue
            seen_time = v[0]
            if type(v[1]) is not type([]):
                v = [ v[1] ]
            else:
                v = v[1]
            for member in v:
                values.add( ID=uid, seen_time=seen_time, member=member )

        if Config.DropZODBContent:
            if hasattr(self, '_pages_seen_by'):
                del self._pages_seen_by

        self._values = values
        self._p_changed = 1

    def __uid( self, ob ):
        return ob.getUid()

    def addSeenByFor( self, ob, uname=None ):
        """
            Remembers that user has visited the given task item.

            Arguments:

                'ob' -- Task item.
        """
        uid = self.__uid(ob)
        if not uname:
            uname = _getAuthenticatedUser(self).getUserName()

        values = self._values.get( ID=uid, member=uname )
        if values: return

        self._values.add( ID=uid, seen_time=DateTime(), member=uname )

        self.catalog_object( ob, idxs=['SeenBy',] )
        portal_info( 'ZSQLFollowupActionsTool.addSeenByFor', 'logger', ( uname, ob.getId() ) )

        # Request nav menu refresh
        refreshClientFrame( Config.FollowupMenu )

    def delSeenByFor( self, ob, uname=None ):
        """
            Removes seen by entry for the given user.

            Arguments:

                'ob' -- Task item.

                'uname' -- User id string/list.
        """
        uid = self.__uid(ob)

        values = self._values.get( ID=uid )
        if not values: return

        if uname:
            members = [ member for ID, seen_time, member in values ]
            IsChanged = 0
            if uname not in ( ListType, TupleType ):
                users = [uname]
            else:
                users = uname
            for x in users:
                if x in members:
                    self._values.remove( ID=uid, mamber=x )
                    IsChanged = 1
            if not IsChanged:
                return
        else:
            self._values.remove( ID=uid )

        self.catalog_object( ob, idxs=['SeenBy',] )
        portal_info( 'ZSQLFollowupActionsTool.delSeenByFor', 'logger', ( uname, ob.getId() ) )

    def listSeenByFor( self, ob, default=None ):
        if not hasattr(self, '_values'):
            self.setup()
        uid = self.__uid(ob)
        values = self._values.get( ID=uid )
        if values: 
            members = [ member for ID, seen_time, member in values ]
            return members
        return default or []

InitializeClass( SeenByLog )


class TaskBrains:
    def test_me(self):
        return 'it\'s me!'


class FollowupActionsTool( CatalogTool ):
    """
        Tasks indexing/search tool
    """
    _class_version = 1.0

    id = 'portal_followup'
    meta_type = 'ExpressSuite Followup Actions Tool'

    security = ClassSecurityInfo()

    manage_options = ZCatalog.manage_options # + ToolBase.manage_options

    # ---------------------------------------------------------------------------------------------------------- #
    #   <metadata key>             <ext_type>    <R><M><I>  <data type>      <attributes>          <engine>      #
    # ---------------------------------------------------------------------------------------------------------- #
    _catalog_metadata = { \
        'archive'              : ( 'SimpleType',  1, 1, 1,  'BOOLEAN',    0, 'NOT NULL DEFAULT 0', '',       ),
        'BrainsType'           : ( 'SimpleType',  1, 1, 1,  'CHAR',      30, 'ASCII NOT NULL',     '',       ),
        'Commissions'          : ( 'ListType',    0, 1, 1,  'VARCHAR',   50, 'NOT NULL',           '',       ),
        'created'              : ( 'SimpleType',  1, 1, 1,  'DATETIME',   0, 'NULL',               '',       ),
        'Creator'              : ( 'SimpleType',  1, 1, 1,  'CHAR',      30, 'ASCII NULL',         '',       ),
        'Description'          : ( 'SimpleType',  0, 1, 1,  'VARCHAR',  500, 'NOT NULL',           '',       ),
        'DocumentCategory'     : ( 'SimpleType',  1, 1, 1,  'VARCHAR',   50, \
                                   'CHARACTER SET latin1 COLLATE latin1_general_cs NULL',          '',       ),
       #'DocumentFolder'       : ( 'SimpleType',  0, 0, 1,  'VARCHAR',  250, 'NULL',               'MYISAM', ),
        'effective'            : ( 'SimpleType',  1, 1, 1,  'DATETIME',   0, 'NULL',               '',       ),
        'expires'              : ( 'SimpleType',  1, 1, 1,  'DATETIME',   0, 'NULL',               '',       ),
        'finished'             : ( 'SimpleType',  1, 1, 1,  'DATETIME',   0, 'NULL',               '',       ),
        'id'                   : ( 'SimpleType',  1, 1, 1,  'CHAR',      20, 'ASCII NOT NULL',     '',       ),
        'InvolvedUsers'        : ( 'ListType',    0, 1, 1,  'VARCHAR',   50, \
                                   'CHARACTER SET latin1 COLLATE latin1_general_cs NOT NULL',      'MYISAM', ),
        'isEnabled'            : ( 'SimpleType',  1, 1, 1,  'BOOLEAN',    0, 'NOT NULL DEFAULT 0', '',       ),
        'isFinalized'          : ( 'SimpleType',  1, 1, 1,  'BOOLEAN',    0, 'NOT NULL DEFAULT 0', '',       ),
        'KickedUsers'          : ( 'ListType',    0, 1, 1,  'VARCHAR',   50, \
                                   'CHARACTER SET latin1 COLLATE latin1_general_cs NOT NULL',      'MYISAM', ),
        'meta_type'            : ( 'SimpleType',  1, 1, 1,  'CHAR',      30, 'ASCII NOT NULL',     '',       ),
        'modified'             : ( 'SimpleType',  1, 1, 1,  'DATETIME',   0, 'NULL',               '',       ),
        'SeenBy'               : ( 'ListType',    0, 1, 1,  'VARCHAR',   50, \
                                   'CHARACTER SET latin1 COLLATE latin1_general_cs NOT NULL',      'MYISAM', ),
        'StateKeys'            : ( 'ListType',    0, 1, 1,  'VARCHAR',   50, \
                                   'CHARACTER SET latin1 COLLATE latin1_general_cs NOT NULL',      'MYISAM', ),
        'Supervisors'          : ( 'ListType',    0, 1, 1,  'VARCHAR',   50, \
                                   'CHARACTER SET latin1 COLLATE latin1_general_cs NOT NULL',      'MYISAM', ),
        'Title'                : ( 'SimpleType',  1, 1, 1,  'VARCHAR',  250, 'NULL',               '',       ),
    }

    _explicit_indexes = ()

    _properties = ZCatalog._catalog_properties

    def _IsDebug( self ):
        try: return self.getPortalObject().aq_parent.getProperty('DEBUG_ZSQLFollowupActionsTool')
        except: return None

    def __init__( self, title='', vocab_id=None, container=None ):
        vocab_id = None
        container = None

        if container is not None:
            self = self.__of__(container)

        self.vocabulary = None
        self.threshold = 1000
        self._v_total = 0

        self._catalog = Catalog( brains=TaskBrains )
        self.logger = SeenByLog()

    def _initstate( self, mode ):
        """
            Initialize attributes
        """
        if not Persistent._initstate( self, mode ):
            return 0

        if not getattr(self, 'logger', None):
            self.logger = SeenByLog()

        return 1

    def _check_unindexable_content( self, object ):
        meta_type = getattr(object, 'meta_type', None)
        if not meta_type or meta_type != TaskItem.meta_type:
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
        obj_metatypes = [ 'Task Item', ]
        
        if root_object is None:
            obj = self.getPortalObject()
        else:
            obj = root_object

        apply_path = '/'.join(obj.getPhysicalPath())
        apply_func = self._catalog.catalog_object

        res = self._catalog.ZopeFindAndApply( obj, obj_metatypes=obj_metatypes, obj_not_cataloged_only=1,
                apply_func=apply_func, apply_path=apply_path, search_sub=1,
                check=check
            )

        if check: return res
        del res
    #
    #   'portal_catalog' interface methods =======================================================================
    #
    security.declarePrivate( 'searchResults' )

    def __url( self, ob ):
        return join( ob.getPhysicalPath(), '/' )

    def wrapOb( self, object ):
        # Wraps the object with accessibility information just before cataloging
        return IndexableObjectWrapper( {}, object )

    def catalog_object( self, object, uid=None, idxs=[], update_metadata=1, pghandler=None, force=None ):
        if self.check_catalog_locked():
            return
        w = self.wrapOb(object)
        ZCatalog.catalog_object( self, w, uid, idxs, update_metadata=update_metadata, \
                                 pghandler=pghandler, force=force )
        if self._IsDebug():
            portal_info( '%s.catalog_object' % self.getId(), 'uid: %s' % uid )

    def reindexObject( self, object, idxs=[], recursive=None ):
        """
            Updates catalog after object data has changed
        """
        if self.check_catalog_locked():
            return
        IsDebug = self._IsDebug()
        catalog_id = self.getId()

        if recursive:
            obs = getContainedObjects( object, followup=1 )
        else:
            obs = [ object ]
        for ob in obs:
            uid = self.__url(ob)
            ZCatalog.catalog_object( self, self.wrapOb(ob), uid, idxs )
            if not IsDebug:
                continue

            portal_info( '%s.reindexObject' % catalog_id, 'uid: %s, idxs: %s' % ( uid, idxs ) )
    #
    #   Catalog implementary functions ===========================================================================
    #
    security.declareProtected( CMFCorePermissions.View, 'searchTasks' )
    def searchTasks( self, archive=None, REQUEST=None, IsCatalog=None, no_subordinate=None, **kw ):
        """
            Perfoms the portal-wide tasks search.

            Arguments:

                'REQUEST', '**kw' -- Extra arguments that limit the results to what the user is allowed to see.

                'IsCatalog' -- implements by ZCatalog.searchResults
        """
        if IsCatalog:
            return self.unrestrictedSearch( REQUEST=REQUEST, with_limit=1, **kw )

        membership = getToolByName( self, 'portal_membership', None )
        if membership is None:
            return []

        username = membership.getAuthenticatedMember().getUserName()
        IsManager = _checkPermission( CMFCorePermissions.ManagePortal, self )

        supervisors = get_param( 'Supervisors', REQUEST, kw, [] )
        creator = get_param( 'Creator', REQUEST, kw, None )
        involved = get_param( 'involved_users', REQUEST, kw, [] )

        if not no_subordinate and not ( creator or supervisors or involved or IsManager ):
            kw['InvolvedUsers'] = membership.listSubordinateUsers( include_chief=1 )

        if not kw.has_key('Creator') and creator == username:
            kw['Creator'] = creator
        if not kw.has_key('Supervisors') and username in supervisors:
            kw['Supervisors'] = supervisors

        total_objects, results = self.searchResults( type='query', with_limit=1, REQUEST=REQUEST, **kw )

        if username in supervisors or creator == username or IsManager or not involved:
            pass
        else:
            results = [ r for r in results if username in r['InvolvedUsers'] + [ r['Creator'] ] + r['Supervisors'] ]
            total_objects = len(results)

        return  ( total_objects, results )

    __call__ = searchTasks

    security.declarePrivate('registerTask')
    def registerTask( self, object ):
        """
            Indexes task item in the catalog.

            Arguments:

                'object' -- Task item.
        """
        #portal_log( self, 'ZSQLFollowupActionTool', 'registerTask', 'path', object.physical_path() )
        self.indexObject( object )

    security.declarePrivate('unregisterTask')
    def unregisterTask( self, object ):
        """
            Removes task item reference from the catalog.

            Arguments:

                'object' -- Task item.
        """
        self.unindexObject( object )
    #
    #   Helper functions =========================================================================================
    #
    def _getListWithResponse( self, tasks, member_id, responded=None ):
        """
            Returns responded or not incoming tasks for given user
        """
        res = []
        for x in tasks:
            state_keys = x['StateKeys']
            IsResponded = 0
            for key in state_keys: 
                if not key.startswith('user_responded:'):
                    continue
                if key.find( member_id ) > -1:
                    IsResponded = 1
                    break
            if responded and IsResponded:
                res.append( x )
            if not responded and IsResponded == 0:
                res.append( x )
        return res

    def _IsExpired( self, member, r ):
        IsClosedReport = 'closed_report:%s' % member in r['StateKeys']
        return not IsClosedReport and not r['isFinalized'] and r['expires'] and r['expires'].isPast() and 1 or 0

    def _IsNotAnswered( self, member, r ):
        IsPending = 'pending:%s' % member in r['StateKeys']
        IsResponded = 'user_responded:%s' % member in r['StateKeys']
        if IsPending or not IsResponded:
            if not r['isFinalized']:
                return 1
            ob = r.getObject()
            if ob is None:
                return 0
            finalized_users = ob.listUsersWithClosedReports()
            #if member in finalized_users:
            #    return 0
            if ob.isFinalizedByDAGroup( member=member, finalized_users=finalized_users ):
                return 0
            return 1
        return 0

    def _extp( self, key=None, value=None, **kw ):
        """
            Followup params extractor
        """
        if key and not value:
            params = default_followup_params[key].copy() or {}
        else:
            params = value.copy()
        keys = params.keys()
        for x in keys:
            t = type(params[x])
            # 'param' can be list or tuple
            if t in SequenceTypes:
                s = []
                for p in params[x]:
                    try: v = p % kw
                    except: v = p
                    s.append(v)
                params[x] = s
            # 'param' can be dictionary like (subquery)
            elif t == type({}):
                params[x] = self._extp(value=params[x], **kw)
            # 'param' is a string
            elif t != type('') or not '%' in params[x]:
                pass
            # 'param' have a substitution like: %(key)s
            else:
                try:
                    params[x] = params[x] % kw
                except:
                    pass
                # 'kw' has not valid key
                if '%' in params[x]:
                    del params[x]
        return params
    #
    #   Followup list functions ==================================================================================
    #
    security.declareProtected( CMFCorePermissions.View, 'countTotalTasks' )
    def countTotalTasks( self, REQUEST, path='', only_new=None ):
        """
            Returns total incoming, supervised and outgoing tasks count.

            Arguments:

                'path' -- Search starting path.

            Result:

               Dictionary, {'total': <total_tasks_count>, 'new': <new_tasks_count>, ...}.
        """
        x = {}

        in_    = self.countIncomingTasks( REQUEST=REQUEST, path=path, only_new=only_new )
        super_ = self.countSupervisedTasks( REQUEST=REQUEST, path=path )
        out_   = self.countOutgoingTasks( REQUEST=REQUEST, path=path )

        x['total'] = in_['total'] + super_['total'] + out_['total']
        x['new'  ] = in_['new'  ] + super_['new'  ] + out_['new'  ]

        return x

    security.declareProtected( CMFCorePermissions.View, 'countIncomingTasks' )
    def countIncomingTasks( self, REQUEST, path='', only_new=None, by_statuses=None ):
        """
            Returns the incoming and supervised tasks count
        """
        x = {}
        member_id = _getAuthenticatedUser(self).getUserName()
        kw = { 'member_id' : member_id, 'path' : path }

        x['total'    ] = self.countResults( REQUEST, **self._extp('incoming_total', **kw) )
        x['new'      ] = self.countResults( REQUEST, **self._extp('incoming_new', **kw) )
        x['seen'     ] = self.countResults( REQUEST, **self._extp('incoming_seen', **kw) )
        x['not_seen' ] = x['new'] - x['seen']

        if not by_statuses: return x

        x['current'  ] = self.countResults( REQUEST, **self._extp('incoming_current', **kw) )
        x['closed'   ] = self.countResults( REQUEST, **self._extp('incoming_closed', **kw) )
        x['finalized'] = self.countResults( REQUEST, **self._extp('incoming_finalized', **kw) )

        return x

    security.declareProtected( CMFCorePermissions.View, 'countOutgoingTasks' )
    def countOutgoingTasks( self, REQUEST, path='', by_statuses=None ):
        """
            Returns the number of outgoing tasks
        """
        x = {}
        member_id = _getAuthenticatedUser(self).getUserName()
        kw = { 'member_id' : member_id, 'path' : path }

        x['total'    ] = self.countResults( REQUEST, **self._extp('outgoing_total', **kw) )
        x['new'      ] = self.countResults( REQUEST, **self._extp('outgoing_new', **kw) )
        x['seen'     ] = self.countResults( REQUEST, **self._extp('outgoing_seen', **kw) )
        x['not_seen' ] = x['new'] - x['seen']

        if not by_statuses: return x

        x['started'  ] = self.countResults( REQUEST, **self._extp('outgoing_started', **kw) )
        x['current'  ] = self.countResults( REQUEST, **self._extp('outgoing_current', **kw) )
        x['closed'   ] = self.countResults( REQUEST, **self._extp('outgoing_closed', **kw) )
        x['finalized'] = self.countResults( REQUEST, **self._extp('outgoing_finalized', **kw) )

        return x

    security.declareProtected( CMFCorePermissions.View, 'countSupervisedTasks' )
    def countSupervisedTasks( self, REQUEST, path='' ):
        """
            Returns the number of supervised tasks
        """
        x = {}
        member_id = _getAuthenticatedUser(self).getUserName()
        kw = { 'member_id' : member_id, 'path' : path }

        x['total'    ] = self.countResults( REQUEST, **self._extp('supervised_total', **kw) )
        if not x['total']:
            x['new'] = x['seen'] = x['not_seen'] = 0
            return x

        x['new'      ] = self.countResults( REQUEST, **self._extp('supervised_new', **kw) )
        x['seen'     ] = 0 # self.countResults( REQUEST, **self._extp('supervised_seen', **kw) )
        x['not_seen' ] = self.countResults( REQUEST, **self._extp('supervised_not_seen', **kw) )

        return x

    security.declareProtected( CMFCorePermissions.View, 'countKickedTasks' )
    def countKickedTasks( self, REQUEST, path='' ):
        """
            Returns the number of user kicked tasks
        """
        x = {}
        member_id = _getAuthenticatedUser(self).getUserName()
        kw = { 'member_id' : member_id }

        x['total'    ] = self.countResults( REQUEST, **self._extp('kicked_total', **kw) )
        x['new'      ] = self.countResults( REQUEST, **self._extp('kicked_new', **kw) )

        return x

    def countPendingTasksForUser( self, uname=None, brains_type=None ):
        """
            Calculates count of tasks which should be pending for given user.
            Returns percent of not answered tasks
        """
        if not uname:
            uname = _getAuthenticatedUser(self).getUserName()

        kw = {}
        if brains_type:
            kw['BrainsType'] = brains_type
        kw['InvolvedUsers'] = uname
        kw['created'] = { 'query' : ( DateTime() - float(30 * 3600 * 24) / 86400,  ), 'range' : 'min' }
        kw['sort_limit'] = default_unlimit

        l1, x = self.searchTasks( IsCatalog=1, **kw )

        if l1 > 0:
            kw['StateKeys'] = 'pending:%s' % uname
            l2, x = self.searchTasks( IsCatalog=1, **kw )
            return 100.0 * l2 / l1
        return 0

    security.declareProtected( CMFCorePermissions.View, 'listIncomingTasks' )
    def listIncomingTasks( self, REQUEST, sort_limit=None, **query ):
        """
            Lists user's incoming tasks
        """
        kw = {}
        member_id = REQUEST.get('member_id') or _getAuthenticatedUser(self).getUserName()
        kw['member_id'] = member_id

        kw = self._extp('incoming_total', **kw)
        if query: kw = updateQuery( kw, query, restricted=['InvolvedUsers'] )

        if REQUEST.has_key('brains_type'):
            kw['BrainsType'] = REQUEST.get('brains_type')

        return self.searchTasks( REQUEST=REQUEST, IsCatalog=1, **kw )

    security.declareProtected( CMFCorePermissions.View, 'listIncomingTasksNew' )
    def listIncomingTasksNew( self, REQUEST, **query ):
        """
            Returns the list of tasks which remain open for the current user
        """
        kw = {}
        member_id = REQUEST.get('member_id') or _getAuthenticatedUser(self).getUserName()
        kw['member_id'] = member_id

        kw = self._extp('incoming_new', **kw)
        if query: kw = updateQuery( kw, query, restricted=['InvolvedUsers'] )

        return self.searchTasks( REQUEST=REQUEST, IsCatalog=1, **kw )

    security.declareProtected( CMFCorePermissions.View, 'listIncomingTasksCurrent' )
    def listIncomingTasksCurrent( self, REQUEST, supervised=0, **query ):
        """
            Returns the list of current tasks which remain open for the current user
        """
        kw = {}
        member_id = REQUEST.get('member_id') or _getAuthenticatedUser(self).getUserName()
        kw['member_id'] = member_id

        kw = self._extp('incoming_current', **kw)
        if query: kw = updateQuery( kw, query, restricted=['InvolvedUsers'] )

        return self.searchTasks( REQUEST=REQUEST, IsCatalog=1, **kw )

    security.declareProtected( CMFCorePermissions.View, 'listIncomingTasksWithClosedReport' )
    def listIncomingTasksWithClosedReport( self, REQUEST, **query ):
        """
            Returns the list of closed tasks for the current user
        """
        kw = {}
        member_id = REQUEST.get('member_id') or _getAuthenticatedUser(self).getUserName()
        kw['member_id'] = member_id

        kw = self._extp('incoming_closed', **kw)
        if query: kw = updateQuery( kw, query, restricted=['InvolvedUsers'] )

        return self.searchTasks( REQUEST=REQUEST, IsCatalog=1, **kw )

    security.declareProtected( CMFCorePermissions.View, 'listIncomingTasksWithoutClosedReport' )
    def listIncomingTasksWithoutClosedReport( self, REQUEST, **query ):
        """
            Returns the list of tasks which remain open for the current user
        """
        kw = {}
        member_id = REQUEST.get('member_id')
        involved_users = REQUEST.get('involved_users')
        kw['member_id' ] = member_id

        if involved_users:
            kw['InvolvedUsers'] = { 'query':involved_users, 'operator':'OR' }

        kw = self._extp('incoming_total', **kw)
        if query: kw = updateQuery( kw, query, restricted=['InvolvedUsers'] )

        kw['BrainsType'] = REQUEST.get('brains_type')
        kw['sort_limit'] = None

        total_objects, tasks = self.searchTasks( REQUEST=REQUEST, IsCatalog=1, **kw )

        IsExpired = REQUEST.has_key('IsExpired')
        IsNotAnswered = REQUEST.has_key('IsNotAnswered')

        if IsExpired or IsNotAnswered:
            res = []
            for r in tasks:
                if IsExpired and self._IsExpired( member_id, r ):
                    res.append( r )
                if IsNotAnswered and self._IsNotAnswered( member_id, r ):
                    res.append( r )
            return ( len(res), res, 1, )

        return ( total_objects, tasks, 1, )

    security.declareProtected( CMFCorePermissions.View, 'listIncomingTasksFinalized' )
    def listIncomingTasksFinalized( self, REQUEST, **query ):
        """
            Returns the list of incoming finalized tasks which remain open for the current user
        """
        kw = {}
        member_id = REQUEST.get('member_id') or _getAuthenticatedUser(self).getUserName()
        kw['member_id'] = member_id

        kw = self._extp('incoming_finalized', **kw)
        if query: kw = updateQuery( kw, query, restricted=['InvolvedUsers'] )

        return self.searchTasks( REQUEST=REQUEST, IsCatalog=1, **kw )

    security.declareProtected( CMFCorePermissions.View, 'listOutgoingTasks' )
    def listOutgoingTasks( self, REQUEST, sort_limit=None, **query ):
        """
            Lists user's outgoing tasks
        """
        kw = {}
        kw['Creator'] = _getAuthenticatedUser(self).getUserName()

        if query: kw = updateQuery( kw, query, restricted=['Creator'] )

        member_id = REQUEST.get('member_id')
        task_type = REQUEST.get('brains_type') or None

        if not task_type:
            total_objects, results = self.searchTasks( REQUEST=REQUEST, **kw )
        elif not member_id:
            total_objects, results = self.searchTasks( REQUEST=REQUEST, BrainsType=task_type, **kw )
        else:
            if kw.has_key('isFinalized'):
                del kw['isFinalized']
            total_objects, results = self.searchTasks( REQUEST=REQUEST, IsCatalog=0, BrainsType=task_type, \
                InvolvedUsers=member_id, **kw )

        return ( total_objects, results, )

    security.declareProtected( CMFCorePermissions.View, 'listOutgoingTasksNew' )
    def listOutgoingTasksNew( self, REQUEST, **query ):
        """
            Lists user's new outgoing tasks
        """
        kw = {}
        member_id = REQUEST.get('Creator') or _getAuthenticatedUser(self).getUserName()
        kw['member_id'] = member_id

        kw = self._extp('outgoing_new', **kw)
        if query: kw = updateQuery( kw, query, restricted=['Creator'] )

        return self.searchTasks( REQUEST=REQUEST, IsCatalog=1, **kw )

    security.declareProtected( CMFCorePermissions.View, 'listOutgoingTasksCurrent' )
    def listOutgoingTasksCurrent( self, REQUEST, **query ):
        """
            Lists user outgoing tasks
        """
        kw = {}
        member_id = REQUEST.get('Creator') or _getAuthenticatedUser(self).getUserName()
        kw['member_id'] = member_id

        kw = self._extp('outgoing_current', **kw)
        if query: kw = updateQuery( kw, query, restricted=['Creator'] )

        return self.searchTasks( REQUEST=REQUEST, IsCatalog=1, **kw )

    security.declareProtected( CMFCorePermissions.View, 'listOutgoingTasksClosed' )
    def listOutgoingTasksClosed( self, REQUEST, **query ):
        """
            Lists user's closed outgoing tasks
        """
        kw = {}
        member_id = REQUEST.get('Creator') or _getAuthenticatedUser(self).getUserName()
        kw['member_id'] = member_id

        kw = self._extp('outgoing_closed', **kw)
        if query: kw = updateQuery( kw, query, restricted=['Creator'] )

        return self.searchTasks( REQUEST=REQUEST, IsCatalog=1, **kw )

    security.declareProtected( CMFCorePermissions.View, 'listOutgoingTasksFinalized' )
    def listOutgoingTasksFinalized( self, REQUEST, **query ):
        """
            Lists user's finalized outgoing tasks
        """
        kw = {}
        member_id = REQUEST.get('Creator') or _getAuthenticatedUser(self).getUserName()
        kw['member_id'] = member_id

        kw = self._extp('outgoing_finalized', **kw)
        if query: kw = updateQuery( kw, query, restricted=['Creator'] )

        return self.searchTasks( REQUEST=REQUEST, IsCatalog=1, **kw )

    security.declareProtected( CMFCorePermissions.View, 'listSupervisedTasks' )
    def listSupervisedTasks( self, REQUEST, reviewed=0, **query ):
        """
            Lists tasks supervised by the current user
        """
        kw = {}
        member_id = REQUEST.get('member_id') or _getAuthenticatedUser(self).getUserName()
        kw['member_id'] = member_id

        if not reviewed:
            reviewed = int(REQUEST.get('reviewed') or 0)
        if reviewed == 2:
            # not reviewed
            mask = 'supervised_new'
        elif reviewed == 1:
            # seen and reviewed
            mask = 'supervised_reviewed'
        else:
            # all
            mask = 'supervised_total'
        kw = self._extp(mask, **kw)
        if query: kw = updateQuery( kw, query, restricted=['Supervisors'] )

        return self.searchTasks( REQUEST=REQUEST, IsCatalog=1, **kw )

    security.declareProtected( CMFCorePermissions.View, 'listKickedTasks' )
    def listKickedTasks( self, REQUEST, **query ):
        """
            Lists user kicked tasks
        """
        kw = {}
        member_id = REQUEST.get('member_id') or _getAuthenticatedUser(self).getUserName()
        kw['member_id'] = member_id

        kw = self._extp('kicked_total', **kw)

        return self.searchTasks( REQUEST=REQUEST, IsCatalog=1, **kw )
    #
    #   Statistics functions =====================================================================================
    #
    security.declareProtected( CMFCorePermissions.View, 'getStatistics' )
    def getStatistics( self, task_type, REQUEST=None, **kw ):
        """
            Returns statistical data for the given task type.

            Arguments:

                'task_type' -- Task type string.

            Result:

                Mapping of the following structure:

                { <user_id>: [ <assigned_tasks_count>,
                               <expired_tasks_count>,
                               <pending_tasks_count>,
                               <processed_tasks_ratio>,
                               <list of user responses for each response type>,
                             ]
                }

            Finalized tasks are not included into the stat report.
        """
        results = {}
        now = DateTime()

        tti = self.getTTI( task_type )
        responses = {}
        for response in tti['responses']:
            responses[ response['id'] ] = len(responses)

        kw['isEnabled'] = 1
        kw['sort_limit'] = default_unlimit

        total_objects, tasks = self.searchTasks( REQUEST=REQUEST, IsCatalog=1, BrainsType=task_type, **kw )

        for r in tasks:
            for user in r['InvolvedUsers']:
                record = results.get(user)
                if record is None:
                    record = results[user] = [ 0, 0, 0, 0, [0] * len(responses) ]
                record[0] += 1
                if self._IsExpired( user, r ):
                    record[1] += 1
                if self._IsNotAnswered( user, r ):
                    record[2] += 1

            for response in r['StateKeys']:
                try:
                    code, user = response.split(':', 1)
                except ValueError:
                    pass
                else:
                    if responses.has_key(code) and results.has_key(user):
                        results[user][4][ responses[code] ] += 1

            interrupt_thread( self )

        for counts in results.values():
            counts[3] = counts[0] and ( counts[0] - counts[2] ) / ( counts[0] + 0.0 ) * 100

        return ( total_objects, results, )

    def getExpiredTaskList( self, task_type=None, REQUEST=None, check_only=None ):
        """
            Returns expired task list for current user
        """
        results = {}
        now = DateTime()

        membership = getToolByName( self, 'portal_membership', None )
        if membership is None:
            return ( 0, [], )

        membership.updateLoginTime()
        username = membership.getAuthenticatedMember().getUserName()
        involved_users = [ username ]

        total_objects, tasks = self.searchTasks( REQUEST=REQUEST, IsCatalog=0, InvolvedUsers=involved_users, isFinalized=0, \
            sort_limit=None )

        if check_only:
            if not tasks: return 0
        elif not tasks:
            return ( 0, [], )

        for r in tasks:
            task = r.getObject()
            if task is None:
                continue
            if not username in task.InvolvedUsers( no_recursive=1 ) or task.isFinalized() or not task.expires().isPast():
                continue
            base = task.getBase()
            if base is None or base.implements('isPortalRoot') or not base.implements('isDocument'):
                continue

            IsNotAnswered = username in task.PendingUsers() and 1 or 0
            if not IsNotAnswered:
                continue

            category = base.Category()

            if not results.has_key(category):
                results[category] = []

            expires = task.expiration_date
            info = {}

            if expires:
                info['expired_days'] = int(now - expires) + 1
            else:
                info['expired_days'] = 0

            info['expiration_date'] = expires
            info['document_title'] = base.Title()
            info['creator'] = base.Creator()
            info['registry_id'] = base.registry_ids() and base.getInfoForLink( mode=2 ) or ''
            info['task_type'] = task.BrainsType()
            info['view_url'] = task.absolute_url( canonical=1, no_version=1 ) + '/view?expand=1'
            info['sortkey'] = ( '00000' + str(info['expired_days']) )[ -5: ]

            results[category].append( info )

            interrupt_thread( self )

        if check_only: return len(results.keys()) > 0 and 1 or 0

        res = []

        for category in results.keys():
            index = self._category_index( category )
            category_title = self._category_title( category )
            res.append( ( index, category_title, results[ category ] ) )

        res.sort()

        results = []
        total = 0

        for index, category, tasks in res:
            results.append( { 'category' : category, 'tasks' : tasks } )
            total += len( tasks )

        if check_only: return total > 0 and 1 or 0

        return ( total, results, )
    #
    #   In Progress Settings and Utilities =======================================================================
    #
    def _parseInProgressOptions( self, REQUEST=None ):
        """
            Returns following in-progress request options: ( period, not_finalized_only, not_answered_only )
        """
        enabled_only = None

        if REQUEST is not None:
            period = int(REQUEST.get('period', '0'))
            if REQUEST.has_key('p1'):
                not_finalized_only = int(REQUEST.get('p1'))
            elif REQUEST.has_key('not_finalized_only'):
                not_finalized_only = int(REQUEST.get('not_finalized_only', '0'))
            else:
                not_finalized_only = 1
            if REQUEST.has_key('p2'):
                not_answered_only = int(REQUEST.get('p2'))
            elif REQUEST.has_key('not_answered_only'):
                not_answered_only = int(REQUEST.get('not_answered_only', '0'))
            else:
                not_answered_only = 1
            if REQUEST.has_key('enabled_only'):
                try: enabled_only = int(REQUEST.get('enabled_only'))
                except: pass
        else:
            period = None
            not_finalized_only = 1
            not_answered_only = 1

        #portal_info( '%s._parseInProgressOptions' % self.getId(), \
        #    'period: %s, not_finalized_only: %s, not_answered_only: %s, enabled_only: %s' % ( \
        #    period, not_finalized_only, not_answered_only, enabled_only ) \
        #    )
        return ( period, not_finalized_only, not_answered_only, enabled_only, )

    def _parseInProgressPeriod( self, period, REQUEST=None ):
        """
            Returns in-progress request period: ( date, usage )
        """
        date = usage = None

        if REQUEST is not None and REQUEST.has_key('now'):
            now = REQUEST.get('now').split('/')
            created_from = len(now) == 3 and DateTime( int(now[0]), int(now[1]), int(now[2])) or None
        else:
            created_from = None

        now = DateTime()
        current_date = DateTime(int(now.strftime('%Y')), int(now.strftime('%m')), int(now.strftime('%d')))

        if period < 10:
            days = period_to_days( period )
            if created_from is not None:
                created_till = created_from + days - 1
                date = ( created_from, created_till and created_till + 0.99999 )
                usage = 'min:max'
            else:
                created_till = now
                created_from = current_date - float((days - 1) * 3600 * 24) / 86400
                date = ( created_from, created_till and created_till + 0.99999 )
                usage = 'min:max'
        elif period >= 10 and period < 20:
            # expires
            if period == 10:
                date = now
                usage = 'max'
            else:
                period = period - 10
                days = period_to_days( period )
                expires = current_date - float(days * 3600 * 24) / 86400
                date = ( expires, now ) # + 0.99999
                usage = 'min:max'
        elif period >= 20 and period < 30:
            # finalized
            if period == 20:
                date = now
                usage = 'max'
            else:
                period = period - 20
                days = period_to_days( period )
                finalized = current_date - float(days * 3600 * 24) / 86400
                date = finalized
                usage = 'min'
        else:
            # expires
            if period == 30:
                # today
                expires = current_date
                date = ( expires, expires + 0.99999 )
                usage = 'min:max'
            else:
                # next week, 2 week, month, quater
                period = period - 30
                days = period_to_days( period )
                begin = current_date + float(1)
                expires = now + float(days * 3600 * 24) / 86400
                date = ( begin, expires + 0.99999 )
                usage = 'min:max'

        #portal_info( '%s._parseInProgressPeriod' % self.getId(), 'period: %s, %s, %s' % ( period, date, usage ) )
        return ( date, usage, )

    def _category_index( self, category ):
        """ Returns sorting custom category index """
        custom_categories = CustomCategoryIds()
        max_categories = len(custom_categories)
        x = max_categories
        for n in range(0, max_categories):
            if category == custom_categories[n]:
                x = n
                break
        return x

    def _category_title( self, category ):
        """ Returns custom category title """
        category_info = portalConfiguration.getAttribute( attr='category', key=category )
        if category_info:
            category_title = category_info['title']
        else:
            category_title = 'Another Documents'
        return category_title

    def _task_state( self, ob ):
        """ Returns task state """
        return not ob.isEnabled() and 'disabled' or \
                   ob.isFinalizedSuccessfully() and 'finalized' or \
                   ob.isExpired() and 'expired' or \
                   ob.ResultCode() == 'cancelled' and 'cancelled' or \
                   'running'

    def _get_request_params( self, REQUEST, username ):
        """ Returns commissions params dictionary """
        kw = {}
        membership = getToolByName( self, 'portal_membership', None )

        period, not_finalized_only, not_answered_only, enabled_only = self._parseInProgressOptions( REQUEST )
        #portal_info( '%s._get_request_params' % self.getId(), 'period: %s, not_finalized_only: %s, not_answered_only: %s, enabled_only: %s' % ( \
        #    period, not_finalized_only, not_answered_only, enabled_only ) \
        #    )

        if enabled_only is not None:
            kw['isEnabled'] = enabled_only
        if not_finalized_only:
            kw['isFinalized'] = 0
        if not period:
            pass
        elif period < 10:
            created, usage = self._parseInProgressPeriod( period, REQUEST )
            kw['created'] = { 'query' : created, 'range' : usage }
        elif period < 20 or period >= 30:
            expires, usage = self._parseInProgressPeriod( period, REQUEST )
            kw['isFinalized'] = 0
            kw['expires'] = { 'query' : expires, 'range' : usage }
        else:
            finished, usage = self._parseInProgressPeriod( period, REQUEST )
            kw['isFinalized'] = 1
            kw['finished'] = { 'query' : finished, 'range' : usage }

        category = filter( None, uniqueValues( REQUEST.get('category') ) )
        if category:
            if len(category) > 1:
                kw['DocumentCategory'] = { 'query' : category, 'operator' : 'or' }
            else:
                kw['DocumentCategory'] = category

        if not REQUEST.has_key('no_commissions'):
            comments = getToolByName( self, 'portal_comments', None )
            if comments is not None:
                commissions = filter( None, uniqueValues( REQUEST.get('commissions') ) )
                if not commissions:
                    commissions.extend( [ x.getId() for x in comments.listComments( context='task.directive' ) ] )
                    commissions.extend( [ x.getId() for x in comments.listComments( context='task.request' ) ] )
                if len(commissions) > 1:
                    kw['Commissions'] = { 'query' : commissions, 'operator' : 'or' }
                else:
                    kw['Commissions'] = commissions

        involved_users = REQUEST.get('involved_users') or REQUEST.get('responsible') or []
        involved_users = filter( None, uniqueValues( involved_users ) )
        query_involved_users = None
        if not involved_users and membership is not None:
            group = membership.getMemberProperties( name='commissions' )
            if group and group not in ['all_users']:
                query_involved_users = { 'query' : membership.getGroupMembers( group ), 'operator' : 'or' }
        if len(involved_users) > 1:
            query_involved_users = { 'query' : involved_users, 'operator' : 'or' }
        elif not query_involved_users and involved_users:
            query_involved_users = involved_users

        ctype = REQUEST.get('ctype') or 'incoming'
        #if ctype == 'supervising':
        #    kw['Creator'] = username
        if ctype == 'any':
            if query_involved_users:
                kw['InvolvedUsers'] = query_involved_users
        elif ctype == 'incoming':
            if involved_users:
                query_involved_users = { 'query' : involved_users + [ username ], 'operator' : 'and' }
            else:
                query_involved_users = username
            kw['InvolvedUsers'] = query_involved_users
        else:
            kw['Creator'] = username
            if query_involved_users:
                kw['InvolvedUsers'] = query_involved_users

        brains_type = filter( None, uniqueValues( REQUEST.get('brains_type') ) )
        if brains_type:
            if len(brains_type) > 1:
                kw['BrainsType'] = { 'query' : brains_type, 'operator' : 'or' }
            else:
                kw['BrainsType'] = brains_type

        company = filter( None, uniqueValues( REQUEST.get('company') ) )

        return ( kw,
                 period,
                 not_finalized_only,
                 not_answered_only,
                 enabled_only,
                 category,
                 ctype,
                 involved_users,
                 brains_type,
                 company,
                 )

    def _checkIsNotAnswered( self, r, ob, username, involved_users=None, check_in_turn=None, ctype=None ):
        """
            Checks if task has users who did not answered
        """
        IsNotAnswered = 0
        pending_users = ob.PendingUsers()
        if check_in_turn:
            try:
                IsNotAnswered = username in pending_users and 1 \
                    or ob.isInTurn( check_root=1 ) and ob.listAllowedResponseTypes( check_demand_revision=1 ) and 1 \
                    or 0
            except:
                IsNotAnswered = 0
        elif involved_users:
            for user in involved_users:
                if user in pending_users: # involved user didn't answer
                    IsNotAnswered = 1
                    break
        elif pending_users:
            if not ctype or ctype == 'incoming':
                if username in pending_users:
                    IsNotAnswered = 1
            else:
                IsNotAnswered = 1
        return IsNotAnswered

    def _listRespondedUsers( self, brain, key=None, recursive=None ):
        """
            Returns list user ids with closed reports
        """
        state_keys = brain['StateKeys']
        if state_keys:
            if not key:
                key = 'closed_report'
            try:
                return filter( None, map( lambda x, key=key: \
                    x.startswith(key) and x[len(key)+1:] or None, \
                    state_keys ))
            except: pass
        return []

    def _check_valid_progress( self, ob, username, ctype ):
        """
            Checks if member should view the item
        """
        if not _checkPermission(CMFCorePermissions.View, ob):
            return 0

        IsValid = 1
        if ctype == 'incoming':
            if not username in ob.InvolvedUsers( no_recursive=1 ):
                IsValid = 0
        elif ctype == 'outgoing':
            if not ob.isCreator( username ):
                IsValid = 0
        elif ctype == 'supervising':
            if ob.isCreator( username ):
                pass
            elif not ob.isSupervisor( username ):
                IsValid = 0
            else:
                managed_by_supervisor = ob.isManagedBySupervisor()
                if managed_by_supervisor == 'info':
                    IsValid = 0
                elif managed_by_supervisor == 'request' and not ob.checkKickedUser( username ):
                    IsValid = 0
        return IsValid

    def _check_allowed_users( self, allowed_users, involved_users, ctype ):
        """
            Checks if it's for allowed users
        """
        IsValid = 1
        if allowed_users and ctype in ['outgoing','supervising']:
            IsValid = 0
            for uname in involved_users:
                if not uname in allowed_users:
                    continue
                IsValid = 1
                break
        return IsValid

    def _check_path( self, path, items ):
        """
            Checks valid path for portal_catalog seatchable text index
        """
        IsValid = 0
        for x in items:
            if x is None: continue
            p = x.getPath()
            if path.startswith( p ):
                IsValid = 1
                break
        return IsValid

    def _check_search( self, REQUEST ):
        """
            Checks searchable context via global *portal_catalog*
        """
        creator = None
        category = None
        search = None
        res = []

        IsSearch = 0

        #if REQUEST.has_key('owners'):
        #    creator = filter( None, uniqueValues( REQUEST.get('owners') or [] ) )
        #    portal_info( '%s._check_search' % self.getId(), 'creator: %s' % creator )

        #if REQUEST.has_key('category'):
        #    category = filter( None, uniqueValues( REQUEST.get('category') or [] ) )
        #    portal_info( '%s._check_search' % self.getId(), 'category: %s' % category )

        if REQUEST.has_key('search'):
            search = REQUEST.get('search').strip()
            if search:
                search = re.sub(r'[\%]+', '', search)
                search = ' '.join([ x[0] not in ('+','-','~','>','<') and '+%s' % x or x \
                    for x in search.split() if x ])            
            #portal_info( '%s._check_search' % self.getId(), 'search: %s' % search )

        if creator or category or search:
            catalog = getToolByName( self, 'portal_catalog', None )
            if catalog is not None:
                query = {}
                #if creator:
                #    query['Creator'] = creator
                #if category:
                #    query['category'] = category
                if search:
                    query['SearchableText'] = search
                query['sort_on'] = 'created'
                query['sort_order'] = 'reverse'
                query['sort_limit'] = default_searchable_limit
                query['implements'] = ( 'isDocument', 'isTaskItem', )

                total_objects, res = catalog.unrestrictedSearch( with_limit=1, **query )
                IsSearch = 1

            #portal_info( '%s._check_search' % self.getId(), 'searched paths: %s' % len(res) )

        return ( IsSearch, res, )

    def _check_search_threshold( self ):
        x = self.threshold or 0
        return x <= 5000 and x or 1000

    def get_attachments_info( self, ob, base, responded_file_ids=None, IsPortalRoot=None ):
        """
            Collects attachments item info
        """
        attachments = []
        if not IsPortalRoot:
            for id, file in base.listAttachments():
                if responded_file_ids and id in responded_file_ids:
                    continue
                attachments.append( { 'id'    : id, \
                                      'title' : file.Title(), \
                                      'url'   : file.relative_url() } )
        return attachments

    def get_responses_info( self, ob, bound_tasks=None, status=None ):
        """
            Collects responses item info
        """
        responded_file_ids = []
        if bound_tasks is None: bound_tasks = [ ob ]

        responses = []

        if ob.hasResponses( recursive=1 ):
            for task in bound_tasks:
                for response in task.searchResponses( view=1 ):
                    if status or response['text'] or response['attachment']:
                        x = response.copy()
                        if x['text']:
                            x['text'] = getPlainText(x['text'], no_br_only=1)
                        if x['attachment']:
                            file = task._getOb(x['attachment'])
                            x['attachment_title'] = file.Title()
                            x['attachment_url'] = task.relative_url(action=x['attachment'])
                            responded_file_ids.append( file.getId() )
                        responses.append( x )
            if responses:
                responses.sort( lambda x, y: cmp(x['date'], y['date']) )
                responses.reverse()
        else:
            responses = None

        return ( responses, responded_file_ids, )

    def get_docflow_info( self, ob, base, username, state, base_resolutions, IsNotAnswered=None, IsPortalRoot=None ):
        """
            Collects docflow item info
        """
        now = DateTime()
        base_path = base.physical_path()
        expires = ob.expiration_date

        base_description = base.Description().strip()
        task_description = formatComments( ob.Description( view=1, clean=1 ) )
        resolution = base.getDocumentResolution( no_absolute=1 )

        info = {}

        if expires and now > expires:
            info['expired_days'] = int(now - expires) + 1
            info['expires'] = not ob.isFinalized() and IsNotAnswered
        else:
            info['expired_days'] = 0
            info['expires'] = None

        info['expiration_date'] = expires
        info['state'] = task_states[state]
        info['document_title'] = base.Title().strip()
        info['document_description'] = info['document_title'] != base_description and base_description
        info['task_description'] = info['document_title'] != task_description and base_description != task_description and task_description
        info['creator'] = base.Creator()
        info['involved_users'] = ob.InvolvedUsers( no_recursive=1 )
        info['delivery_date'] = getattr( ob, 'effective_date', None ) or getattr( base, 'created', None ) # or CustomAttributeValue( base, 'delivery_date' )
        info['executing_agency'] = CustomAttributeValue( base, 'executing_agency' )

        executor = CustomAttributeValue( base, 'executor' )
        if executor:
            if type(executor) is StringType:
                executor = [ executor ]
        elif resolution:
            executor = ob.listInvolvedUsers( recursive=1 )
        else:
            executor = []
        info['executor'] = list( filter( None, uniqueValues( executor ) ) )

        signatory = CustomAttributeValue( base, 'signatory' )
        if signatory:
            if type(signatory) not in ( ListType, TupleType ):
                signatory = [ signatory ]
            info['signatory'] = [ x for x in signatory if x not in info['executor'] ]
        else:
            info['signatory'] = []
        info['signatory'] = list( filter( None, uniqueValues( info['signatory'] ) ) )

        info['registry_id'] = base.registry_ids() and base.getInfoForLink( mode=2 ) or ''
        info['task_type'] = ob.BrainsType()

        if resolution and base_path not in base_resolutions:
            info['resolution'] = resolution
            base_resolutions.append( base_path )
        else:
            info['resolution'] = None

        info['view_url'] = ob.absolute_url( canonical=1, no_version=1 ) + '/view?expand=1'
        info['new'] = username not in ob.SeenBy() and IsNotAnswered and 1 or 0

        try: effective_date = int((now - getattr( ob, 'effective_date', now )) * 10**8)
        except: effective_date = 0

        info['sortkey'] = ( '00000' + str(info['expired_days']) )[ -5: ] + ( '0000000000' + str(int(effective_date)) )[ -12: ]

        interrupt_thread( self )
        return info

    def searchItems( self, username, ctype, kw, query, method, IsCatalog=None, REQUEST=None ):
        """
            Search followup brains
        """
        portal_info( '%s.searchItems' % self.getId(), "%s kw: %s" % ( method, kw ) )

        tasks = []
        total_objects = 0
        count, res = self.searchTasks( REQUEST=REQUEST, IsCatalog=IsCatalog, no_subordinate=1, **kw )
        if count:
            total_objects += count
            tasks.extend( res )

        if ctype in ['supervising']:
            if kw.has_key('Creator'):
                del kw['Creator']
            kw['Supervisors'] = username
            count, res = self.searchTasks( REQUEST=REQUEST, IsCatalog=IsCatalog, **kw )
            if count:
                total_objects += count
                tasks.extend( res )

        portal_info( '%s.searchItems' % self.getId(), "%s total_objects: %s, tasks: %s" % ( \
            method, total_objects, len(tasks) ) \
            )
        return ( total_objects, tasks, )
    #
    #   In Progress Reports ======================================================================================
    #
    def getDocflowInProgress( self, REQUEST=None, member=None, check_only=None ):
        """
            Returns progress list of documents for current user (delivered to member,
            accessible documents via tasks)
        """
        results = {}
        applied = []

        membership = getToolByName( self, 'portal_membership', None )
        if membership is None:
            if check_only:
                return 0
            return ( 0, [], )

        membership.updateLoginTime()
        username = member or membership.getAuthenticatedMember().getUserName()

        kw = {}
        kw['InvolvedUsers'] = [ username ]
        period, not_finalized_only, not_answered_only, enabled_only = self._parseInProgressOptions( REQUEST )

        if not_finalized_only:
            kw['isFinalized'] = 0
        if period:
            created, usage = self._parseInProgressPeriod( period, REQUEST )
            kw['created'] = { 'query' : created, 'range' : usage }

        tasks = []
        kw['sort_limit'] = default_unlimit

        total_objects, res = self.searchTasks( REQUEST=REQUEST, IsCatalog=0, **kw )
        if total_objects: tasks.extend( res )

        del kw['InvolvedUsers']
        kw['Supervisors'] = username

        total_objects, res = self.searchTasks( REQUEST=REQUEST, IsCatalog=0, **kw )
        if total_objects: tasks.extend( res )

        if check_only:
            if not tasks: return 0
        elif not tasks:
            return ( 0, [], 0, 0, 0, )

        base_resolutions = []
        total_documents = 0
        bases = []

        for r in tasks:
            ob = r.getObject()
            if ob is None or r['id'] in applied: continue
            applied.append( r['id'] )
            IsSupervisor = ob.isSupervisor( username )

            if not ( username in ob.InvolvedUsers( no_recursive=1 ) or IsSupervisor ) or not ob.isEnabled():
                continue
            if not_answered_only:
                IsNotAnswered = self._checkIsNotAnswered( r, ob, username, check_in_turn=1 )
                if not IsNotAnswered:
                    continue
            else:
                IsNotAnswered = 0

            base = ob.getBase()
            IsPortalRoot = ( base is None or base.implements('isPortalRoot') or \
                             not ( base.implements('isDocument') or base.implements('isVersionable') ) ) and 1 \
                             or 0
            if IsPortalRoot:
                continue

            uid = base.getUid()
            if uid not in bases:
                bases.append( uid )
                total_documents += 1

            state = self._task_state( ob )

            category = base.Category()
            if not results.has_key(category):
                results[ category ] = []

            info = self.get_docflow_info( ob, base, username, state, base_resolutions, IsNotAnswered )

            #info['responses'], responded_file_ids = self.get_responses_info( ob )
            info['attachments'] = self.get_attachments_info( ob, base, [], IsPortalRoot )

            results[ category ].append( info )

        if check_only: return len(results.keys()) > 0 and 1 or 0

        res = []

        for category in results.keys():
            index = self._category_index( category )
            category_title = self._category_title( category )
            res.append( ( index, category_title, results[ category ] ) )

        res.sort()
        results = []
        total = 0

        for index, category, tasks in res:
            results.append( { 'category' : category, 'tasks' : tasks } )
            total += len( tasks )

        if check_only: return total > 0 and 1 or 0
        del base_resolutions, bases

        return ( total, results, total, total_objects, total_documents, )

    def getDocflowSearch( self, REQUEST=None, member=None, check_only=None ):
        """
            Returns progress list of documents for current user (delivered to member,
            accessible documents via tasks) according search request
        """
        results = {}
        applied = []

        membership = getToolByName( self, 'portal_membership', None )
        if membership is None:
            if check_only:
                return 0
            return ( 0, [], )

        membership.updateLoginTime()
        user = membership.getAuthenticatedMember()
        username = user.getUserName()
        IsManager = user.IsManager()
        IsAdmin = user.IsAdmin()
        commission_category = 'BaseCommission'

        REQUEST.set('no_commissions', 1)

        kw, period, not_finalized_only, not_answered_only, enabled_only, category, ctype, requested_involved_users, \
        brains_type, company = \
            self._get_request_params( REQUEST, username )
        requested_state = filter( None, uniqueValues( REQUEST.get('state') ) ) or None

        if not requested_state:
            pass
        elif 'expired' in requested_state:
            kw['isFinalized'] = 0
            kw['isEnabled'] = 1
            kw['expires'] = { 'query' : DateTime() + 0.00001, 'range' : 'max' }
        elif 'disabled' in requested_state:
            kw['isEnabled'] = 0
        elif 'finalized' in requested_state:
            kw['isFinalized'] = 1
        elif 'cancelled' in requested_state:
            kw['isFinalized'] = 1
        elif 'running' in requested_state:
            kw['isFinalized'] = 0
            kw['isEnabled'] = 1
            kw['expires'] = { 'query' : DateTime() + 0.00001, 'range' : 'min' }

        IsSearch, searchable_items = self._check_search( REQUEST )
        IsRun = 1

        if searchable_items:
            kw['sort_limit'] = default_unlimit
        elif IsSearch:
            IsRun = 0
        else:
            searchable_items = [ None ]
            kw['sort_on'] = 'created'
            kw['sort_order'] = 'reverse'
            kw['sort_limit'] = not IsManager and self._check_search_threshold() or default_unlimit

        if IsRun:
            query = { 'requested_state'   : requested_state,
                      'enabled_only'      : enabled_only,
                      'not_answered_only' : not_answered_only,
                      'ctype'             : ctype,
                      'company'           : company,
                    }
            if category:
                query['DocumentCategory'] = category

            #portal_info( '%s.getDocflowSearch' % self.getId(), "query: %s" % query )

            tasks = []
            total_objects = 0
            for x in searchable_items:
                if x is None:
                    pass
                elif 'isDocument' in x['implements']:
                    kw['path'] = x.getPath() + '%'
                elif 'isTaskItem' in x['implements']:
                    kw['path'] = x.getPath()

                count, res = self.searchItems( username, ctype, kw, query, \
                    method='getDocflowSearch', IsCatalog=1, \
                    REQUEST=REQUEST )

                if count:
                    total_objects += count
                    tasks.extend(res)
        else:
            tasks = None

        if check_only:
            if not tasks: return 0
        elif not tasks:
            return ( 0, [], 0, 0, 0, )

        base_resolutions = []
        total_documents = 0
        bases = []
        n = 0

        for r in tasks:
            #if IsSearch and not self._check_path( r.getPath(), searchable_items ):
            #    continue
            ob = r.getObject()
            if ob is None or r['id'] in applied:
                continue
            applied.append( r['id'] )
            #involved_users = ob.InvolvedUsers( no_recursive=1 )

            base = ob.getBase()
            IsPortalRoot = ( base is None or base.implements('isPortalRoot') or \
                             not ( base.implements('isDocument') or base.implements('isVersionable') ) ) and 1 \
                             or 0
            if IsPortalRoot:
                continue

            if not self._check_valid_progress( ob, username, ctype ):
                continue
            if not_answered_only:
                IsNotAnswered = self._checkIsNotAnswered( r, ob, username, requested_involved_users, ctype=ctype )
                if not IsNotAnswered:
                    continue
                if ctype != 'incoming': IsNotAnswered = 0
            else:
                IsNotAnswered = 0

            state = self._task_state( ob )

            if requested_state:
                if state not in requested_state:
                    continue
            if company:
                if not CustomAttributeValue( base, 'company' ) in company:
                    continue

            uid = base.getUid()
            if uid not in bases:
                bases.append( uid )
                total_documents += 1

            n += 1
            if not IsAdmin and n > default_visible_limit:
                continue

            category = base.Category()
            if not results.has_key(category):
                results[ category ] = []

            info = self.get_docflow_info( ob, base, username, state, base_resolutions, IsNotAnswered )

            info['responses'], responded_file_ids = self.get_responses_info( ob )
            info['attachments'] = self.get_attachments_info( ob, base, responded_file_ids, IsPortalRoot )

            results[ category ].append( info )

        if check_only:
            return len(results.keys()) > 0 and 1 or 0
        res = []

        for category in results.keys():
            index = self._category_index( category )
            category_title = self._category_title( category )
            res.append( ( index, category_title, results[ category ] ) )

        res.sort()
        results = []
        total = 0

        for index, category, tasks in res:
            results.append( { 'category' : category, 'tasks' : tasks } )
            total += len( tasks )

        if check_only:
            return total > 0 and 1 or 0
        del base_resolutions, bases

        return ( total, results, n, total_objects, total_documents, )

    def getCommissionsInProgress( self, REQUEST=None, member=None, check_only=None ):
        """
            Returns progress list of commissions/resolutions for current user (delivered to or from member,
            accessible documents via tasks)
        """
        results = {}
        now = DateTime()
        applied = []

        membership = getToolByName( self, 'portal_membership', None )
        if membership is None:
            if check_only:
                return 0
            return ( 0, [], )

        if REQUEST is None:
            REQUEST = aq_get( self, 'REQUEST', None )

        membership.updateLoginTime()
        username = member or membership.getAuthenticatedMember().getUserName()
        commission_category = 'BaseCommission'

        kw, period, not_finalized_only, not_answered_only, enabled_only, category, ctype, requested_involved_users, \
        brains_type, company = \
            self._get_request_params( REQUEST, username )

        requested_state = filter( None, uniqueValues( REQUEST.get('state') ) ) or None
        awaiting = REQUEST.get('awaiting') or None
        sortkey = REQUEST.get('sortkey') or None

        finalized = REQUEST.has_key('finalized') and int(REQUEST.get('finalized')) or 0
        in_time = REQUEST.has_key('in_time') and int(REQUEST.get('in_time')) or 0
        with_delay = REQUEST.has_key('with_delay') and int(REQUEST.get('with_delay')) or 0
        on_work = REQUEST.has_key('on_work') and int(REQUEST.get('on_work')) or 0

        IsSearch, searchable_items = self._check_search( REQUEST )
        IsRun = 1

        if IsSearch:
            if not searchable_items:
                IsRun = 0
        else:
            searchable_items = [ None ]

        kw['sort_limit'] = default_unlimit

        if IsRun:
            query = { 'requested_state'   : requested_state,
                      'enabled_only'      : enabled_only,
                      'not_answered_only' : not_answered_only,
                      'ctype'             : ctype,
                    }
            if company != 'nonselected':
                query['company'] = company
            if category:
                query['DocumentCategory'] = category

            #portal_info( '%s.getCommissionsInProgress' % self.getId(), "query: %s" % query )

            tasks = []
            total_objects = 0
            for x in searchable_items:
                if x is None:
                    pass
                elif 'isDocument' in x['implements']:
                    kw['path'] = x.getPath() + '%'
                elif 'isTaskItem' in x['implements']:
                    kw['path'] = x.getPath()

                count, res = self.searchItems( username, ctype, kw, query, \
                    method='getCommissionsInProgress', IsCatalog=1, \
                    REQUEST=REQUEST )

                if count:
                    total_objects += count
                    tasks.extend(res)
        else:
            tasks = None

        if check_only:
            if not tasks: return 0
        elif not tasks:
            return ( 0, [], )

        base_resolutions = []
        date_max = DateTime( 2019, 1, 1 )

        allowed_users = None
        try:
            group = membership.getMemberProperties( name='commissions' )
            if group:
                allowed_users = membership.getGroupMembers( group )
        except:
            pass

        company_ids = departmentDictionary.listCompanyIds()

        for r in tasks:
            #if IsSearch and not self._check_path( r.getPath(), searchable_items ):
            #    continue
            ob = r.getObject()
            if ob is None or r['id'] in applied:
                continue
            applied.append( r['id'] )
            involved_users = ob.InvolvedUsers( no_recursive=1 )

            if not self._check_valid_progress( ob, username, ctype ):
                continue
            if not self._check_allowed_users( allowed_users, r['InvolvedUsers'], ctype ):
                continue
            if not_answered_only:
                IsNotAnswered = self._checkIsNotAnswered( r, ob, username, requested_involved_users )
                if not IsNotAnswered:
                    continue
            else:
                IsNotAnswered = 0

            base = ob.getBase()
            IsPortalRoot = ( base is None or base.implements('isPortalRoot') ) and 1 or 0

            if company:
                if IsPortalRoot:
                    continue
                x = CustomAttributeValue( base, 'company' )
                if company == 'nonselected':
                    if x in company_ids:
                        continue
                elif not x in company:
                    continue

            expires = ob.expiration_date
            state = self._task_state( ob )

            if finalized:
                if state != 'finalized':
                    continue
            if requested_state:
                if state not in requested_state:
                    continue
            if state == 'disabled':
                if enabled_only and ( not requested_state or state not in requested_state ):
                    continue
            if in_time:
                if not ( state == 'finalized' and ob.finished() <= expires ):
                    continue
            elif with_delay:
                if not ( state == 'finalized' and ob.finished() > expires ):
                    continue
            elif on_work:
                if not state == 'running':
                    continue

            if not IsPortalRoot:
                category = base.Category()
                base_path = base.physical_path()
            else:
                category = commission_category
                base_path = ob.physical_path()

            if not results.has_key(category): results[ category ] = []
            info = {}

            if expires and now > expires:
                info['expired_days'] = int(now - expires) + 1
                info['expires'] = not ob.isFinalized() and IsNotAnswered
            else:
                info['expired_days'] = 0
                info['expires'] = None

            bound_tasks = [ ob ] + ob.followup.getBoundTasks( recursive=1 )
            info['expiration_date'] = expires
            info['state'] = task_states[state]

            if not IsPortalRoot:
                info['document_title'] = base.Title().strip()
                base_description = base.Description().strip()
                info['executing_agency'] = CustomAttributeValue( base, 'executing_agency' )
                info['registry_id'] = base.registry_ids() and base.getInfoForLink( mode=2 ) or ''
                resolution = base.getDocumentResolution( no_absolute=1, tasks=bound_tasks )
            else:
                info['document_title'] = ob.Title().strip()
                base_description = ''
                info['executing_agency'] = ''
                info['registry_id'] = ''
                resolution = None

            info['document_description'] = info['document_title'] != base_description and base_description or ''
            info['creator'] = ob.Creator()
            info['supervisors'] = ob.Supervisors()
            info['delivery_date'] = ob.created()

            executor = involved_users
            info['executor'] = []
            if executor:
                if type(executor) is StringType:
                    executor = [ executor ]
            else: #if not resolution:
                executor = ob.InvolvedUsers() #ob.listInvolvedUsers( recursive=1 )
            info['executor'] = list( membership.listSortedUserNames( executor, contents='id' ) )

            signatory = CustomAttributeValue( base, 'signatory' )
            if signatory:
                if type(signatory) not in ( ListType, TupleType ):
                    signatory = [ signatory ]
                info['signatory'] = [ x for x in signatory if x not in info['executor'] ]
            else:
                info['signatory'] = []
            info['signatory'] = list( filter( None, uniqueValues( info['signatory'] ) ) )

            info['task_type'] = ob.BrainsType()
            task_description = formatComments(ob.Description( view=1, clean=1 ))
            info['task_description'] = info['document_title'] != task_description and base_description != task_description and \
                task_description

            if resolution and base_path not in base_resolutions:
                info['resolution'] = resolution
                base_resolutions.append( base_path )
            else:
                info['resolution'] = None

            info['responses'], responded_file_ids = self.get_responses_info( ob, bound_tasks )
            info['attachments'] = self.get_attachments_info( ob, base, responded_file_ids, IsPortalRoot )

            info['view_url'] = ob.absolute_url( canonical=1, no_version=1 ) + '/view?expand=1'
            info['new'] = username not in ob.SeenBy() and IsNotAnswered and 1 or 0

            try:
                effective_date = int((now - getattr( ob, 'effective_date', now )) * 10**8)
            except:
                effective_date = 0

            if not sortkey:
                info['sortkey'] = ( '00000' + str(info['expired_days']) )[ -5: ] + \
                    ( '0000000000' + str(int(date_max-expires)) )[ -10: ]
            elif sortkey == 'expires':
                info['sortkey'] = expires

            results[ category ].append( info )
            interrupt_thread( self )

        if check_only: return len(results.keys()) > 0 and 1 or 0

        res = []

        for category in results.keys():
            index = self._category_index( category )
            category_title = self._category_title( category )
            res.append( ( index, category_title, results[ category ] ) )

        res.sort()
        results = []
        total = 0

        for index, category, tasks in res:
            results.append( { 'category' : category, 'tasks' : tasks, 'before' : total } )
            total += len( tasks )

        if check_only:
            return total > 0 and 1 or 0
        return ( total, results, )

    def getCommissionsStatistics( self, REQUEST=None, member=None ):
        """
            Returns progress list of commissions/resolutions for current user (delivered to or from member,
            accessible documents via tasks)
        """
        results = []

        membership = getToolByName( self, 'portal_membership', None )
        if membership is None:
            if check_only:
                return 0
            return ( 0, [], )

        if REQUEST is None:
            REQUEST = aq_get( self, 'REQUEST', {} )

        membership.updateLoginTime()
        username = member or membership.getAuthenticatedMember().getUserName()
        commission_category = 'BaseCommission'

        kw, period, not_finalized_only, not_answered_only, enabled_only, category, ctype, requested_involved_users, \
        brains_type, company = \
            self._get_request_params( REQUEST, username )
        requested_state = filter( None, uniqueValues( REQUEST.get('state') ) ) or None

        statistics = {}

        if kw.has_key('created'):
            created = kw['created']
            if type(created) is TupleType:
                kw['created'] = ( created[0].strftime('%Y/%m/%d'), created[1].strftime('%Y/%m/%d'), )
            else:
                kw['created'] = created.strftime('%Y/%m/%d')

        query = { 'kw' : kw or {} }
        query['username'] = username
        query['InvolvedUsers'] = requested_involved_users
        query['not_finalized_only'] = not_finalized_only
        query['not_answered_only'] = not_answered_only
        query['company'] = company
        query['requested_state'] = requested_state
        query['ctype'] = ctype or ''

        instances = portalConfiguration.getAttribute( attr='remote_portal_addresses', key='anonymous', context=self )
        #portal_info( '%s.getCommissionsStatistics' % self.getId(), 'query: %s, instances: %s' % ( query, str(instances) ) )

        total_objects = total_finalized = total_in_time = total_with_delay = total_on_work = total_expired = total_disabled = 0

        for n in range(len(instances)+1):
            if n > 0:
                addr = instances[n-1]
                try:
                    remote_followup = xmlrpclib.Server( '%s/%s' % ( addr, 'portal_followup' ) )
                    info = remote_followup.get_ci( query )
                except:
                    #portal_error( '%s.getCommissionsStatistics' % self.getId(), 'addr: %s' % addr, exc_info=True )
                    continue
            else:
                addr = None
                info = self.get_ci( query )

            for uname in info.keys():
                if uname == 'total':
                    total_objects += info[uname][0]
                    total_finalized += info[uname][1]
                    total_in_time += info[uname][2]
                    total_with_delay += info[uname][3]
                    total_on_work += info[uname][4]
                    total_expired += info[uname][5]
                    total_disabled += info[uname][6]
                    continue

                total, finalized, in_time, with_delay, on_work, expired, not_answered, disabled = info[ uname ]
                if not statistics.has_key( uname ):
                    statistics[ uname ] = [ 0, 0, 0, 0, 0, 0, 0, 0 ]

                total += statistics[ uname ][0]
                finalized += statistics[ uname ][1]
                in_time += statistics[ uname ][2]
                with_delay += statistics[ uname ][3]
                on_work += statistics[ uname ][4]
                expired += statistics[ uname ][5]
                not_answered += statistics[ uname ][6]
                disabled += statistics[ uname ][7]

                statistics[ uname ] = [ total, finalized, in_time, with_delay, on_work, expired, not_answered, disabled, ]

            #portal_info( '%s.getCommissionsStatistics' % self.getId(), 'n: %s, addr: %s, info: %s, statistics: %s' % ( \
            #    n, addr, info, statistics ) \
            #    )

        for uname in statistics.keys():
            member = membership.getMemberById( uname )
            if member is None:
                statistics[ uname ] = None
                continue

            total = statistics[ uname ][0]
            finalized = statistics[ uname ][1]

            if not ( finalized > 0 and total > 0 ):
                statistics[ uname ][2] = ( 0, 0, )
                statistics[ uname ][3] = ( 0, 0, )
            else:
                # in time
                in_time = statistics[ uname ][2]
                p_in_time = 100.0 * in_time / total #finalized
                statistics[ uname ][2] = ( in_time, p_in_time, )
                # with delay
                with_delay = statistics[ uname ][3]
                p_with_delay = 100.0 * with_delay / total #finalized
                statistics[ uname ][3] = ( with_delay, p_with_delay, )

            if not total > 0:
                statistics[ uname ][5] = ( 0, 0, )
            else:
                # expired
                expired = statistics[ uname ][5]
                p_expired = 100.0 * expired / total
                statistics[ uname ][5] = ( expired, p_expired, )

        total_results = [ 0, 0, [0,0], [0,0], 0, [0,0], 0, 0 ]

        for key in statistics.keys():
            if not statistics[ key ]:
                continue

            x = statistics[ key ]

            results.append( { \
                'member'       : key,
                'name'         : membership.getMemberName( key ),
                'total'        : x[0],
                'check_up'     : x[4]+x[5][0],
                'finalized'    : x[1],
                'in_time'      : x[2][0], 'p_in_time'    : formatFloat( x[2][1] ),
                'with_delay'   : x[3][0], 'p_with_delay' : formatFloat( x[3][1] ),
                'on_work'      : x[4],
                'expired'      : x[5][0], 'p_expired'    : formatFloat( x[5][1] ),
                'not_answered' : x[6],
                'disabled'     : x[7],
                }
            )

            total_results[0] += x[0]
            total_results[1] += x[1]
            total_results[2][0] += x[2][0]
            total_results[3][0] += x[3][0]
            total_results[4] += x[4]
            total_results[5][0] += x[5][0]
            total_results[6] += x[6]
            total_results[7] += x[7]

        if total_results[0] > 0:
            total_results[2][1] += 100.0 * total_results[2][0] / total_results[0]
            total_results[3][1] += 100.0 * total_results[3][0] / total_results[0]
            total_results[5][1] += 100.0 * total_results[5][0] / total_results[0]

        results.sort( lambda x, y: cmp(x['name'], y['name']) )

        x = total_results

        results.append( { \
                'member'       : 'total', 
                'name'         : 'Total results', 
                'total'        : ( ( total_objects, total_finalized, total_in_time, total_with_delay, total_on_work, total_expired, total_disabled, ), x[0], ),
                'check_up'     : x[4]+x[5][0],
                'finalized'    : x[1],
                'in_time'      : x[2][0], 'p_in_time'    : formatFloat( x[2][1] ),
                'with_delay'   : x[3][0], 'p_with_delay' : formatFloat( x[3][1] ),
                'on_work'      : x[4],
                'expired'      : x[5][0], 'p_expired'    : formatFloat( x[5][1] ),
                'not_answered' : x[6],
                'disabled'     : x[7],
                }
            )

        #portal_info( '%s.getCommissionsStatistics' % self.getId(), 'finished' )
        return results

    def getCIO_ABCD( self, REQUEST=None, member=None ):
        """
            Returns progress list of CIO report for current user (delivered to or from member,
            accessible documents via tasks)
        """
        results_A = []
        results_D = []

        membership = getToolByName( self, 'portal_membership', None )
        if membership is None:
            if check_only:
                return 0
            return ( 0, 0, 0, [], 0, 0, [], )

        if REQUEST is None:
            REQUEST = aq_get( self, 'REQUEST', {} )

        membership.updateLoginTime()
        username = member or membership.getAuthenticatedMember().getUserName()

        kw, period, not_finalized_only, not_answered_only, enabled_only, category, ctype, requested_involved_users, \
        brains_type, company = \
            self._get_request_params( REQUEST, username )
        requested_state = filter( None, uniqueValues( REQUEST.get('state') ) ) or None

        statistics = {}

        if kw.has_key('created'):
            created = kw['created']
            if type(created) is TupleType:
                kw['created'] = ( created[0].strftime('%Y/%m/%d'), created[1].strftime('%Y/%m/%d'), )
            elif type(created) is DictType:
                if created.has_key('query'):
                    x = created['query']
                    kw['created'] = ( x[0].strftime('%Y/%m/%d'), x[1].strftime('%Y/%m/%d'), )
            else:
                kw['created'] = created.strftime('%Y/%m/%d')

        query = { 'kw' : kw or {} }
        query['username'] = username
        query['InvolvedUsers'] = requested_involved_users
        query['company'] = company
        query['requested_state'] = requested_state
        query['ctype'] = ctype

        instances = portalConfiguration.getAttribute( attr='remote_portal_addresses', key='anonymous', context=self )
        #portal_info( '%s.getCIO_ABCD' % self.getId(), 'query: %s, instances: %s' % ( query, str(instances) ) )
        portal_info( '%s.getCIO_ABCD' % self.getId(), 'query: %s' % query )
        company_ids = []

        for n in range(len(instances)+1):
            if n > 0:
                addr = instances[n-1]
                try:
                    remote_followup = xmlrpclib.Server( '%s/%s' % ( addr, 'portal_followup' ) )
                    info = remote_followup.get_cio_abcd( query )
                except:
                    #portal_error( '%s.getCIO_ABCD' % self.getId(), 'addr: %s' % addr, exc_info=True )
                    continue
            else:
                addr = None
                info = self.get_cio_abcd( query )

            for key in info.keys():
                total, new, finalized, expired, expires_info, companies_info = info[ key ]
                if not statistics.has_key( key ):
                    statistics[ key ] = [ 0, 0, 0, 0, {}, {} ]

                total += statistics[ key ][0]
                new += statistics[ key ][1]
                finalized += statistics[ key ][2]
                expired += statistics[ key ][3]
                users = statistics[ key ][4]
                companies = statistics[ key ][5]

                for uname, expires in expires_info:
                    if not users.has_key( uname ):
                        users[ uname ] = [ 0, 0 ]
                    users[ uname ][0] += 1
                    users[ uname ][1] += expires

                for x in companies_info.keys():
                    if not companies.has_key( x ):
                        companies[ x ] = 0
                    companies[ x ] += companies_info[ x ]
                    if x not in company_ids:
                        company_ids.append( x )

                statistics[ key ] = [ total, new, finalized, expired, users, companies ]

            #portal_info( '%s.getCIO_ABCD' % self.getId(), 'n: %s, addr: %s, info: %s, statistics: %s' % ( \
            #    n, addr, info, statistics ) \
            #    )

        total = new = finalized = expired = 0

        for key in statistics.keys():
            x = statistics[ key ]

            category_total = x[0]
            category_expired = x[3]

            total += category_total
            new += x[1]
            finalized += x[2]
            expired += category_expired

            A = [ 0, 0 ]
            D = []

            members_expires_info = x[4]

            for uname in members_expires_info.keys():
                member = membership.getMemberById( uname )
                if member is None:
                    continue
                name = member.getMemberName()
                member_total = members_expires_info[ uname ][0]
                member_expired = members_expires_info[ uname ][1]

                A[0] += member_total
                A[1] += member_expired

                if member_expired:
                    D.append( { 'member' : uname, 'name' : name, 'total' : member_total, 'expired' : member_expired } )

            companies_info = {}
            category_companies = x[5]

            for x in company_ids:
                companies_info[ x ] = 0
            for company in category_companies.keys():
                companies_info[ company ] += category_companies[ company ]

            index = self._category_index( key )

            results_A.append( { \
                'category'       : key, 
                'index'          : index,
                'total'          : category_total,
                'expired'        : category_expired,
                'member_total'   : A[0],
                'member_expired' : A[1],
                'p_expired'      : formatFloat( category_total > 0 and 100.0 * category_expired / category_total or 0 ),
                'companies_info' : companies_info,
                }
            )

            if A[1] == 0: continue

            D.sort( lambda x, y: cmp(x['name'], y['name']) )

            results_D.append( { \
                'category'       : key, 
                'index'          : index,
                'results'        : D,
                }
            )

        p_expired = formatFloat( total > 0 and 100.0 * expired / total or 0 )

        results_A.sort( lambda x, y: cmp(x['index'], y['index']) )
        results_D.sort( lambda x, y: cmp(x['index'], y['index']) )

        companies = []
        msg = getToolByName( self, 'msg', None )
        another = msg('Another')
        for id in company_ids:
            if id != 'nonselected':
                title = departmentDictionary.getCompanyTitle( id, name=1 )
            else:
                title = another
            companies.append( { 'id' : id, 'title' : title } )
        companies.sort( lambda x, y: cmp(x['title'], y['title']) )

        res = ( total, expired, p_expired, results_A, new, finalized, results_D, tuple(companies) )

        #portal_info( '%s.getCIO_ABCD' % self.getId(), 'results: %s' % str(res) )
        return res

    security.declareProtected( CMFCorePermissions.View, 'get_ci' )
    def get_ci( self, query ):
        """
            Returns commissions members statisticts for given portal instance
        """
        results = {}
        now = DateTime()
        applied = []

        try: current_instance = getToolByName( self, 'portal_properties' ).instance_name()
        except: current_instance = ''

        kw = query.get('kw', {}).copy()
        kw['sort_limit'] = default_unlimit

        username = query.get('username')
        not_answered_only = query.get('not_answered_only')
        requested_involved_users = query.get('InvolvedUsers') or []
        requested_company = query.get('company') or []
        requested_state = query.get('requested_state') or []
        #kw['isEnabled'] = requested_state != 'disabled' and 1 or 0
        ctype = query.get('ctype')

        if kw.has_key('created'):
            created = kw['created']
            if len(created) == 2:
                kw['created'] = ( DateTime( created[0] ), DateTime( created[1] ) + 0.99999, )
            else:
                kw['created'] = DateTime( created )

        total_objects, tasks = self.searchItems( username, ctype, kw, query, 'get_ci' )

        allowed_users = None
        membership = getToolByName( self, 'portal_membership', None )
        try:
            group = membership.getMemberProperties( name='commissions' )
            if group: allowed_users = membership.getGroupMembers( group )
        except: pass

        total_objects = total_finalized = total_in_time = total_with_delay = total_on_work = total_expired = total_disabled = 0

        for r in tasks:
            ob = r.getObject()
            if ob is None or r['id'] in applied: continue
            applied.append( r['id'] )
            involved_users = requested_involved_users or ob.InvolvedUsers( no_recursive=1 )

            recursive = 0
            if not involved_users:
                involved_users = ob.InvolvedUsers()
                if involved_users:
                    recursive = 1

            if not self._check_valid_progress( ob, username, ctype ):
                continue
            if not self._check_allowed_users( allowed_users, involved_users, ctype ):
                continue
            if not_answered_only:
                IsNotAnswered = self._checkIsNotAnswered( r, ob, username, requested_involved_users )
                if not IsNotAnswered:
                    continue
            else:
                IsNotAnswered = 0

            expires = ob.expiration_date
            state = self._task_state( ob )
            #portal_info( '%s.get_ci' % self.getId(), 'ob: %s, state: %s' % ( r['id'], state ) )

            if requested_state:
                if state not in requested_state:
                    continue

            base = ob.getBase()
            IsPortalRoot = ( base is None or base.implements('isPortalRoot') ) and 1 or 0
            IsValid = 0

            if not IsPortalRoot:
                company = CustomAttributeValue( base, 'company' )
            else:
                company = None
            if requested_company and ( company is None or company not in requested_company ):
                continue

            answered = ob.listRespondedUsers( status='', recursive=recursive ) #ob.listUsersWithClosedReports( recursive=recursive )

            for uname in involved_users:
                if allowed_users and not uname in allowed_users:
                    continue
                if not uname in r['InvolvedUsers']:
                    continue
                if not results.has_key( uname ):
                    results[ uname ] = ( 0, 0, 0, 0, 0, 0, 0, 0, )
                IsValid = 1

                total, finalized, in_time, with_delay, on_work, expired, not_answered, disabled = results[ uname ]

                total += 1
                if state == 'disabled':
                    disabled += 1
                elif state == 'running':
                    on_work += 1
                elif state == 'finalized':
                    finalized += 1
                    if ob.isFinalized( in_time=1 ):
                        in_time += 1
                    else:
                        with_delay += 1
                elif state == 'expired':
                    expired += 1
                if uname not in answered and state in ['running', 'expired']:
                    not_answered += 1

                results[ uname ] = ( total, finalized, in_time, with_delay, on_work, expired, not_answered, disabled, )

            if not IsValid: continue

            total_objects += 1
            if state == 'disabled':
                total_disabled += 1
            elif state == 'finalized':
                total_finalized += 1
                if ob.finished() <= expires:
                    total_in_time += 1
                else:
                    total_with_delay += 1
            elif state == 'running':
                total_on_work += 1
            elif state == 'expired':
                total_expired += 1

            interrupt_thread( self )

        results['total'] = ( total_objects, total_finalized, total_in_time, total_with_delay, total_on_work, total_expired, total_disabled )

        #portal_info( '%s.get_ci' % self.getId(), 'results: %s' % len(results) )
        return results

    security.declareProtected( CMFCorePermissions.View, 'get_cio_abcd' )
    def get_cio_abcd( self, query ):
        """
            Returns CIO members report statisticts for given portal instance
        """
        results = {}
        now = DateTime()
        applied = []

        try: current_instance = getToolByName( self, 'portal_properties' ).instance_name()
        except: current_instance = ''

        kw = query.get('kw', {}).copy()
        kw['sort_limit'] = default_unlimit

        username = query.get('username')
        requested_involved_users = query.get('InvolvedUsers') or []
        requested_company = query.get('company') or []
        requested_state = query.get('requested_state') or []
        ctype = query.get('ctype')

        if kw.has_key('created'):
            created = kw['created']
            if len(created) == 2:
                created = ( DateTime( created[0] ), DateTime( created[1] ), )
            else:
                created = ( DateTime( created ), now )
            del kw['created']
        else:
            created = None

        #total_objects, res = self.searchTasks( IsCatalog=0, **kw )
        #if total_objects: tasks.extend( res )

        total_objects, tasks = self.searchItems( username, ctype, kw, query, 'get_cio_abcd' )

        #if kw.has_key('Creator'): del kw['Creator']
        #kw['Supervisors'] = username
        #total_objects, res = self.searchTasks( IsCatalog=0, **kw )
        #if total_objects: tasks.extend( res )

        allowed_users = None
        membership = getToolByName( self, 'portal_membership', None )
        try:
            group = membership.getMemberProperties( name='commissions' )
            if group: allowed_users = membership.getGroupMembers( group )
        except: pass

        commission_category = 'BaseCommission'
        expires_info = []

        for r in tasks:
            ob = r.getObject()
            if ob is None or r['id'] in applied: continue
            #portal_info( '%s.get_cio_abcd' % self.getId(), 'check ob: %s' % r['id'] )
            applied.append( r['id'] )
            involved_users = requested_involved_users or ob.InvolvedUsers( no_recursive=1 )

            recursive = 0
            if not involved_users:
                involved_users = ob.InvolvedUsers()
                if involved_users:
                    recursive = 1

            if not self._check_valid_progress( ob, username, ctype ):
                continue
            if not self._check_allowed_users( allowed_users, involved_users, ctype ):
                continue

            state = self._task_state( ob )
            if requested_state and state not in requested_state:
                continue

            base = ob.getBase()
            IsPortalRoot = ( base is None or base.implements('isPortalRoot') ) and 1 or 0

            if not IsPortalRoot:
                category = base.Category()
                company = CustomAttributeValue( base, 'company' )
            else:
                category = commission_category
                company = None
            if requested_company and ( company is None or company not in requested_company ):
                continue

            if not results.has_key(category): results[ category ] = [ 0, 0, 0, 0, [], { 'nonselected' : 0 } ]

            # new
            if not created or r['created'] >= created[0]:
                results[ category ][1] += 1
            # finalized
            if state == 'finalized':
                finalized_date = getattr( ob, 'finalized_date', None )
                if not created or ( finalized_date >= created[0] and finalized_date <= created[1] ):
                    results[ category ][2] += 1
                continue
            if state == 'cancelled':
                continue
            #portal_info( '%s.get_cio_abcd' % self.getId(), 'ob: %s' % r['id'] )

            # total
            results[ category ][0] += 1

            answered = ob.listRespondedUsers( status='commit', recursive=recursive ) #ob.listUsersWithClosedReports( recursive=recursive )

            # members task info
            for uname in involved_users:
                if allowed_users and not uname in allowed_users:
                    continue
                if not uname in r['InvolvedUsers']:
                    continue
                expired = state == 'expired' and uname not in answered and 1 or 0
                results[ category ][4].append( ( uname, expired ) )

            # company document info
            if not IsPortalRoot:
                if company:
                    x = results[ category ][5]
                    if x.has_key(company):
                        x[ company ] += 1
                    else:
                        x[ company ] = 1
            else:
                x = results[ category ][5]
                x['nonselected'] += 1

            if state != 'expired':
                continue

            # expired
            results[ category ][3] += 1

            interrupt_thread( self )

        #portal_info( '%s.get_cio_abcd' % self.getId(), 'results: %s' % results )
        return results
    #
    #   Another functions ========================================================================================
    #
    security.declareProtected( CMFCorePermissions.View, 'saveLinkedReport' )
    def saveLinkedReport( self, folder, title, description, report_generator, REQUEST=None, \
            category_id=None, transition=None ):
        """
            Create an HTMLDocument containing a report previously generated with ReportWizard
        """
        id = str( int(DateTime().timeTime()) )
        dest_folder_uid = REQUEST.get('dest_folder_uid')
        container = None

        html_text = report_generator(folder, REQUEST)
        if title:
            html_caption = '<P style="font-size:14px;font-family:verdana;"><STRONG>' + title + '</STRONG></P>'
            if description:
                html_caption = html_caption + '<P style="font-size:10px;font-family:verdana;">' + description + '</P>'
            html_text = html_caption + html_text

        if REQUEST.get('no_css', None) is not None:
            html_text = HTMLCleaner( html_text, None, 2, '', 'SCRIPT STYLE' )

        # Find the folder where to place the overall report
        if dest_folder_uid:
            container = getObjectByUid( self, dest_folder_uid )
            if container is not None:
                while not container.implements('isPortalRoot') and container.meta_type != 'Heading':
                    container = aq_parent( aq_inner( container ) )

        # or locate it inside the given object document's version
        if container is None:
            container = folder
            if container.meta_type != 'HTMLDocument':
                while not ( container.implements('isVersion') or container.implements('isDocument') ):
                    container = aq_parent( aq_inner( container ) )

        if container.implements('isPortalRoot'):
            container = container.storage

        ob = HTMLDocument( id, title, description, 'html', html_text )

        if ob is not None:
            metadata = getToolByName( self, 'portal_metadata', None )
            if metadata is None:
                return None
            category = metadata.getCategoryById( category_id or 'Document' )
            ob.setCategory( category )
            container._setObject( id, ob )
            ob = container._getOb(id)
            if transition:
                try:
                    workflow = getToolByName( self, 'portal_workflow', None )
                    workflow.doActionFor( ob, transition, comment='run by system process' )
                except:
                    pass
            #r = getattr( container, id )
            url = ob.relative_url()
            #self._set_remote_link( container, ob, url )
            return ( url, ob.getUid(), )
        else:
            #portal_error( '%s.saveReport' % self.getId(), 'folder not found, uid: %s' % dest_folder_uid )
            return None

    def _set_remote_link( self, container, ob, url ):
        """
            Sets remote link inside the given container
        """
        if not container.implements('isDocument'):
            return
        remote_links = getattr(container, 'remote_links', None) or []
        remote_links.append( { 'url'   : url,
                               'uid'   : ob.getUid(),
                               'title' : ob.Title() }
                            )
        setattr(container, 'remote_links', remote_links)

    security.declareProtected( CMFCorePermissions.View, 'listAllowedTaskTypes' )
    def listAllowedTaskTypes( self, context, visible=None ):
        """
            Returns the list of allowed task types in the given context.

            Arguments:

                'context' -- User context.

            Result:

                List of task type information mappings (see TaskBrains for
                details).
        """
        results = []

        brains_list = listTaskBrains( visible )
        uname = _getAuthenticatedUser(self).getUserName()
        for brains in brains_list:
             tti = brains.task_type_information
             available = 1
             if tti.has_key('condition'):
                 condition = Expression(tti['condition'])
                 if not condition(getEngine().getContext( {'here': context, 'member': uname } )):
                     available = 0

             if tti.has_key('permissions') and available:
                  available = 0

                  permissions = tti['permissions']
                  if type(permissions) is StringType:
                      permissions = [permissions,]
                  for permission in permissions:
                       if _checkPermission(permission, context):
                           available = 1
                           break

             if available:
                 results.append( tti )

        return results

    security.declareProtected( CMFCorePermissions.View, 'listTTIs' )
    def listTTIs( self ):
        """
            Returns the list of portal task types.

            Result:

                List of task type information mappings (see TaskBrains for
                details).
        """
        brains_list = listTaskBrains()
        results = [ b.task_type_information for b in brains_list ]
        return results

    security.declareProtected( CMFCorePermissions.View, 'getTTI' )
    def getTTI( self, task_type ):
        """
            Returns the task type information for the given task type.

            Arguments:

                'task_type' -- Task type name.

            Result:

                Task type information mapping.
        """
        brains = getTaskBrains( task_type )
        if brains:
            return brains.task_type_information
        return

    security.declarePublic( 'getTasksFor' )
    def getTasksFor( self, content ):
        """
            Return the tasks container for content, creating it if need be.

            Arguments:

                'content' -- Content object.

            Result:

                Reference to the TaskItemContainer class instance.
        """
        followup = getattr( content, 'followup', None )
        if not followup:
            followup = self._createFollowupFor( content )
        return followup

    def getLogger( self ):
        """
            Returns the task logger instance used for tracking the user activity.

            Result:

                Reference to the logger object.
        """
        return getattr( self, 'logger', None )
    #
    #   Utility methods ==========================================================================================
    #
    security.declarePrivate( '_createFollowupFor' )
    def _createFollowupFor( self, content ):
        """
            Create the object that holds task items.

            Arguments:

                'content' -- Content object.

            Result:

                Reference to the TaskItemContainer class instance.
        """
        content.followup = TaskItemContainer()
        return content.followup

    def getOptionValue( self, name, typ, prefix, REQUEST=None, default=None ):
        """
            Checks and return cookies option value
        """
        if REQUEST is None:
            return None
        full_name = '%s:%s' % ( name, typ )
        cookie_name = '%s_%s' % ( prefix, name )
        IsUpdate = 0
        if REQUEST.has_key( name ):
            value = REQUEST.get( name )
        elif REQUEST.has_key( full_name ):
            value = REQUEST.get( full_name )
        elif not REQUEST.has_key( 'no_cookie' ) and REQUEST.cookies.has_key( cookie_name ):
            value = REQUEST.cookies.get( cookie_name )
            IsUpdate = 1
        elif default is not None:
            value = default
            IsUpdate = 1
        else:
            value = ''
        #portal_info( '%s.getOptionValue' % self.getId(), 'option: %s:%s:%s' % ( name, typ, value ) )
        if typ == 'list':
            if value:
                if type(value) is StringType:
                    try:
                        value = value.split('%20')
                        value = filter( None, uniqueValues( value ) )
                    except: pass
                elif value:
                    value = filter( None, uniqueValues( value ) )
            else:
                value = []
        elif typ == 'string':
            if value:
                value = str(value)
            else:
                value = ''
        elif typ == 'int':
            try: value = int(value)
            except: value = 0
        #portal_info( '%s.getOptionValue' % self.getId(), 'value: %s' % value )
        if IsUpdate:
            REQUEST.set( name, value )
        return value

    def getDocflowDescription( self ):
        """
            Returns portal description to use inside reporting
        """
        msg = getToolByName( self, 'msg', None )
        default = msg('DOCFLOW SYSTEM')
        properties = getToolByName( self, 'portal_properties', None )
        if properties is None:
            return default
        description = properties.getProperty('description')
        if not description:
            return default
        x = description.split('\n')
        return x[0] or default

InitializeClass( FollowupActionsTool )


def period_to_days( period ):
    return period == 7 and 360 or period == 6 and 180 or period == 5 and 90 or \
           period == 4 and 30  or period == 3 and 14  or period == 2 and 7  or \
           1

def updateQuery( kw, query=None, restricted=[] ):
    if not query or type(query) != type({}):
        return kw
    for x in query.keys():
        if kw.has_key(x):
            if x in restricted:
                kw[x] = { 'query':( kw[x], query[x] ), 'operator':'AND' }
                continue
        kw[x] = query[x]
    return kw