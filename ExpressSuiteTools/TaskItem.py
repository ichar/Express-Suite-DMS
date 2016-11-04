"""
Defines TaskItem, TaskItemsContainer and ResponseCollection classes.
$Id: TaskItem.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 15/06/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import re, string, os.path, sys
from DateTime import DateTime
from types import StringType, ListType, TupleType, DictType, IntType
from string import join

from Globals import DTMLFile, package_home
from Acquisition import Implicit, aq_inner, aq_base, aq_parent, aq_get
from AccessControl import ClassSecurityInfo, Permissions
from AccessControl.SecurityManagement import get_ident

from zExceptions import Unauthorized

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.utils import getToolByName, _getAuthenticatedUser, _checkPermission
from Products.CMFCore.Expression import Expression
from Products.CMFCore.FSPythonScript import FSPythonScript
from Products.PageTemplates.Expressions import getEngine

from OFS.ObjectManager import ObjectManager
from OFS.Traversable import Traversable
from OFS.SimpleItem import SimpleItem
from ZODB.POSException import ConflictError, ReadConflictError
from ExtensionClass import Base

from Config import EditorRole, WriterRole, ReaderRole, OwnerRole, VersionOwnerRole, \
     TaskResultCodes, DemandRevisionCodes, CheckZODBBeforeInstall, \
     FollowupMenu, AttachmentTypes
import Features
from ConflictResolution import ResolveConflict
from ISAMSupporter import ISAMMapping
from File import addFile
from SimpleObjects import Persistent, InstanceBase, ContentBase
from Exceptions import SimpleError
from PortalLogger import portal_log, portal_info, portal_debug, portal_error
from TaskBrains import getTaskBrains
from TemporalExpressions import DateTimeTE, UniformIntervalTE
from TransactionManager import BeginThread, CommitThread, IsThreadActivated, UpdateRequestRuntime, interrupt_thread

from Utils import InitializeClass, parseTime, uniqueValues, CheckAntiSpam, UpdateRolePermissions, \
     getPlainText, getBTreesItem, check_request

from CustomObjects import IsPrivateObject

from logging import getLogger
logger = getLogger( 'TaskItem' )


factory_type_information = ( { 'id'            : 'Task Item'
                            , 'meta_type'      : 'Task Item'
                            , 'description'    : """\
Followup task item"""
                            , 'icon'           : 'taskitem_icon.gif'
                            , 'product'        : '' # leave blank to suppress
                            , 'factory'        : ''
                            , 'immediate_view' : ''
                            , 'disallow_manual': 1
                            , 'allow_discussion': 1
                            , 'actions'        :
                                ( { 'id'            : 'view'
                                  , 'name'          : 'View task'
                                  , 'action'        : 'task_view'
                                  , 'permissions'   : ( CMFCorePermissions.View, )
                                  },
                                ),
                             }
                           ,
                           )

_comments = [ '<div class=comments>', '</div>', '<p.*?id="(.*?)" title=comments>', '</p>' ]

def _parse_comments( text ):
    text = re.sub(r'<P title=comments>&nbsp;</P>', '<br>', text)
    text = re.sub(r'(<P title=comments>)+', '<P title=comments>', text)
    text = re.sub(r'(&nbsp;<br>)+(?i)', '', text)
    text = re.sub(r'(<br>)+</div>(?i)', '</div>', text)
    return text


class ResponseCollection( Persistent, Implicit ):
    """
        Lightweight user responses storage. It is not aware of the task type brains and 
        treats responses as a dict data.
    """
    id = 'ResponseCollection'

    security = ClassSecurityInfo()
    indexes = ( 'status', 'member', 'layer', 'isclosed', )

    def __init__( self ):
        Persistent.__init__( self )
        self._collection = {}
        self._last_id = 0

    def _p_resolveConflict( self, o, s, n ):
        """
            Try to resolve conflict between container's objects
        """
        state = ResolveConflict('ResponseCollection', o, s, n, '_collection', mode=2 )
        state['_last_id'] = max(o['_last_id'], s['_last_id'], n['_last_id'])
        return state

    def getId( self ):
        return getattr(self, 'id', None)

    def getRecordId( self, ob=None, response_id=None ):
        thread_id = get_ident()
        id = response_id or 0
        uid = ob is not None and '-%s' % ob.getUid() or ''
        return '%s%s-%s' % ( thread_id, uid, str(id) )

    def setup( self, container, force=None ):
        """
            Initialize class instance
        """
        if not force and CheckZODBBeforeInstall:
            if getattr(self, '_collection', None) is not None:
                return

        if not hasattr(self, '_values') or self._values is None:
            self._values = ISAMMapping( self.getId(), 'default_response_collection_columns' )

        collection = {}
        last_id = 0

        rid = '%s-%s' % ( container.getUid(), '%' )
        values = self._values.get( rid, mode='records', default={} )

        for x in values:
            id = self.getRecordId(container, x['response_id'])
            item = x.copy()
            item['ID'] = id
            collection[id] = item
            last_id = max(last_id, x['response_id'])

        self._collection = collection
        self._last_id = last_id

        logger.info('ResponseCollection: updated %s items, last_id %s' % ( \
            len(self._collection.keys()), self._last_id ) \
            )
        self._p_changed = 1

    def addResponse( self, ob, layer, status, text, member, isclosed, attachment=None, uip=None, remarks=None ):
        """
            Adds a new user response

            Append a new user response in case there is no response
            with the given member, layer, status already stored in the
            collection or replace it otherwise.

            Arguments:

                'layer'      -- Layer id string. There can be only *one* response on
                                each layer per user.

                'status'     -- Response status id string.

                'text'       -- User report text.

                'member'     -- User id string.

                'isclosed'   -- Boolean. Indicates whether the response can be
                                changed later or not.

                'attachment' -- An id string of the file attachment associated
                                with the response.

                'uip'        -- User ip address for the electronic signature.
        """
        task_id = ob.getId()
        response_id = self.getLastResponseId() + 1

        rid = self.getRecordId( ob, response_id )

        response = { 'date'        : DateTime(),
                     'member'      : member,
                     'status'      : status,
                     'layer'       : layer,
                     'text'        : text,
                     'isclosed'    : isclosed,
                     'attachment'  : attachment,
                     'uip'         : uip,
                     'remarks'     : remarks,
                     'response_id' : response_id,
                     'task_id'     : task_id,
                     'ID'          : rid,
                   }

        self._collection[rid] = response
        self._last_id = response_id
        self._p_changed = 1

    def editResponse( self, rid, items ):
        """
            Lets update some items inside response
        """
        response = self.getResponse( rid )
        if not response:
            return

        for key in items.keys():
            if key in ( 'isclosed', 'response_status', 'remarks', ):
                response[key] = items[key]

        self._collection[rid] = response
        self._p_changed = 1

    def getResponse( self, rid ):
        return self._collection.get( rid ) or None

    def getResponseById( self, response_id ):
        x = self.searchResponses( response_id=response_id )
        return x and x[0] or None

    security.declareProtected( CMFCorePermissions.View, 'getIndexKeys' )
    def getIndexKeys( self, **kw ):
        """
            Returns the keys of a given index.

            Arguments:

                'kw' -- Index id string.

            For example getIndexKeys(member=1) will return a list of
            responded users ids.
        """
        if not kw:
            return None
        key = kw.keys()[0]
        return uniqueValues([ x[key] for x in self._collection.values() ])

    def searchResponses( self, view=None, **kw ):
        """
            Returns a set of responses according to the search query.

            Arguments:

                '**kw' -- Search query. Each argument defines the value of the particular index.

            Example:

                The following query will return the list of user responses with the given 
                status and layer within the current task.

                >>> searchResponses(layer='involved_users', status='commit')

            Results:
                Mapping tuple of responses dictionaries.
        """
        res = []
        for x in self._collection.values():
            matched = 1
            for key in kw.keys():
                if x[key] != kw[key]:
                    matched = 0
                    break
            if matched:
                res.append(x.copy())
        return tuple(res)

    def _searchResponsesIds( self, **kw ):
        """
            Returns a set of responses ids according to the search query
        """
        return [ x['response_id'] for x in self.searchResponses( **kw ) ]

    def hasResponses( self ):
        return getattr(self, '_collection', None) and 1 or 0

    security.declarePrivate( 'getLastResponseId' )
    def getLastResponseId( self ):
        """
            Returns id of last response
        """
        return getattr(self, '_last_id', None) or 0

InitializeClass( ResponseCollection )


class TaskItem( ContentBase, ObjectManager ):
    """ 
        Task item base class. Declares brain-independent methods.
    """
    _force_autoupdate = None
    _class_version = 1.02

    __implements__ = ( Features.isTaskItem,
                       ContentBase.__implements__,
                       ObjectManager.__implements__,
                     )

    __unimplements__ = ( Features.isPortalContent,
                       )

    meta_type = 'Task Item'
    portal_type = 'Task Item'

    allow_discussion = 1
    notify_mode = None
    finalize_settings = {}
    auto_finalized = None

    mail_notify_users = DTMLFile( 'skins/mail_templates/task.notify_users', globals() )
    mail_expiration_alarm = DTMLFile( 'skins/mail_templates/task.expiration_alarm', globals() )
    mail_alarm = DTMLFile( 'skins/mail_templates/task.alarm', globals() )
    dateperiod = FSPythonScript('dateperiod', '%s/skins/common/dateperiod.py' % package_home(globals()))

    security = ClassSecurityInfo()

    def __init__( self
                , id
                , title
                , involved_users
                , brains
                , description=''
                , creator=None
                , effective_date=None
                , expiration_date=None
                , followup_tasks=None
                , task_template_id=None
                , version_id=None
                , enabled=None
                , temporal_expr=None
                , notify_mode=None
                , finalize_settings=None
                , resolution=None
                , hand_roles=None
                , workflow_state=None
                ):

        ContentBase.__init__( self )

        self.id = id
        self.title = title

        self.brains = brains()
        self.description = _parse_comments( description )
        self.creator = creator or _getAuthenticatedUser(self).getUserName()
        self.supervisors = []
        self.involved_users = involved_users
        self.suspended_users = None
        self.followup_tasks = followup_tasks or []
        self.enabled = enabled
        self.notify_mode = notify_mode
        self.effective_date = effective_date
        self.finalized_date = None
        self.expiration_date = expiration_date
        self.finalize_settings = finalize_settings is not None and finalize_settings.copy() or {}
        self.auto_finalized = None
        self.finalized = None
        self.responses = ResponseCollection()
        self.resolution = resolution
        self.result = None
        self.task_template_id = task_template_id
        self.task_is_automated = task_template_id and 1 or 0
        self.temporal_expr = temporal_expr
        self.duration = None
        self.version_id = version_id
        self.hand_roles = hand_roles or [ ReaderRole ]
        self.workflow_state = workflow_state
        self.modification_date = DateTime()

    # CHECK THE OBJECT STATES AND ADVISABLE IGNORE CONFLICT !!!
    # =========================================================
    def _p_resolveConflict( self, o, s, n ):
        """
            Try to resolve conflict between container's objects
        """
        #if ResolveConflict('TaskItem', o, s, n, 'modification_date', mode=-1):
        #    raise ConflictError
        return 1

    def _initstate( self, mode ):
        """
            Initialize attributes
        """
        if not ContentBase._initstate( self, mode ):
            return 0

        if mode:
            logger.info('initstate autoupdate class version: %s (%s)' % ( self._class_version, self.id ))

        if getattr(self, 'notification_history', None) is None:
            self.notification_history = []
        if not hasattr(self, '_task_schedule_id'):
            default = getattr(self, 'schedule_id', None)
            self._task_schedule_id = default
        if not hasattr(self, '_expiration_schedule_id'):
            self._expiration_schedule_id = None
        if not hasattr(self, '_effective_schedule_id'):
            self._effective_schedule_id = None
        if not hasattr(self, '_alarm_schedule_id'):
            self._alarm_schedule_id = None
        if not hasattr(self, '_finalize_schedule_id'):
            self._finalize_schedule_id = None
        if not hasattr(self, 'followup_tasks'):
             self.followup_tasks = []
        if not hasattr(self, 'plan_time'):
             self.plan_time = None
        if not hasattr(self, 'actual_times'):
             self.actual_times = {}
        if not hasattr(self, 'bind_to'):
             self.bind_to = None
        if not hasattr(self, 'enabled'):
             self.enabled = None
        if not hasattr(self, 'notify_mode'):
             self.notify_mode = None
        if not hasattr(self, 'finalize_settings'):
             self.finalize_settings = {}
        if not hasattr(self, 'auto_finalized'):
             self.auto_finalized = None
        if not hasattr(self, 'temporal_expr'):
             self.temporal_expr = None

        if not hasattr(self, 'version_id'):
            # in HTMLDocument's _initstate this initialized also
            self.version_id = None

        if not hasattr(self, 'supervisors'):
            supervisor = getattr(self, 'supervisor', None)
            if supervisor:
                supervisors = [ supervisor ]
                delattr(self, 'supervisor')
            else:
                supervisors = []
            self.supervisors = supervisors

        if hasattr(self, '_old_supervisor'):
            old_supervisors = getattr(self, '_old_supervisor', None)
            if old_supervisors:
                self._old_supervisors = [ old_supervisors ]
                delattr(self, '_old_supervisor')
            else:
                self._old_supervisors = None

        if not hasattr(self, 'modification_date'):
             self.modification_date = DateTime()

        if mode and hasattr(self, 'responses'):
            self.responses.setup( self )

        return 1

    def __call__( self, REQUEST=None ):
        """
            Invokes the default view
        """
        if not self.get_brains().validate():
            raise Unauthorized, self.getId()
        return ContentBase.__call__( self, REQUEST )

    def HasBeenSeenByFor( self, task=None, uname=None, REQUEST=None ):
        """
            Add slogger for current user. *** User has been viewed the task ***
        """
        if not uname:
            uname = _getAuthenticatedUser(self).getUserName()

        # Check task as read by the current user
        if REQUEST is not None and REQUEST.get('x_committed') == 1:
            return
        if not ( self.isSuperuser( uname ) or self.isInvolved( uname ) ):
            return
        slogger = self.get_logger()
        if slogger is None:
            return

        if task is not None: 
            ob = task
        else:
            ob = self

        slogger.addSeenByFor( ob, uname=uname )

    def ShouldBeSeenByFor( self, task=None, uname=None ):
        """
            Prepares SeenByLog for add a new task item. *** User should be viewed the task ***
        """
        slogger = self.get_logger()
        if slogger is None:
            return

        if task is not None: 
            ob = task
        else:
            ob = self

        slogger.delSeenByFor( ob, uname=uname )

    def get_logger( self ):
        """
            Returns the followup tool slogger instance.

            Logger object is used to store statistical data for each task.
            See FollowupActionsTool.SeenByLog for details.

            Result:

              Reference to the FollowupActionsTool.SeenByLog instance.
        """
        followup = getToolByName( self, 'portal_followup', None )
        if followup is not None:
            return followup.getLogger()
        return None

    security.declarePrivate( 'get_brains' )
    def get_brains( self ):
        """
            Returns the reference to the task brains instance associated with the current task item.

            Brains are the component-like way to define custom behaviour
            for the different task types. See TaskBrains.py for details.

            Result:

                Reference to the TaskBrains instance.
        """
        return self.brains

    security.declarePrivate( 'get_responses' )
    def get_responses( self ):
        """
            Returns the responses collection instance associated with the task object.

            Responses collection instance is created within every task item;
            it is responsible for storing and retrieving the user responses.

            Result:

                Reference to the ResponseCollection instance.
        """
        return self.responses

    #security.declareProtected( CMFCorePermissions.View, 'validate' )
    def validate( self ):
        """
            Checks whether the current user is allowed to access the given task
        """
        base = self.getBase()
        document_version_id = None

        if base is not None:
            if base.implements('isVersionable'):
                document_version_id = base.getVersion().id
            else:
                document_version_id = base.getId()

        task_version_id = self.version_id
        validate_version_id = ( task_version_id is None or document_version_id is None ) and 1 or \
            task_version_id == document_version_id

        return self.get_brains().validate() and validate_version_id

    def objectIds( self, spec=None ):
        # It's allowed to pass sequence type 'spec' list, such as: ( 'Image Attachment', 'File Attachment', )
        if not spec:
            ids = ObjectManager.objectIds(self)
        else:
            if type(spec) == type(''):
                spec = [spec]
            ids = []
            for x in spec:
                ids.extend( ObjectManager.objectIds(self, x) )

        #XXXXXX how could TaskItemContainer be in TaskItem
        #followup = ( hasattr( aq_base( self ), 'followup' ) and self.followup or None )
        #if followup is not None:
        #    ids.append('followup')
        return ids

    security.declareProtected( CMFCorePermissions.View, 'deleteObject')
    def deleteObject( self, REQUEST=None ):
        """
            Delete me!
        """
        id = self.getId()
        self.deleteTask( id )

        if REQUEST is None:
            return
        base = self.getBase()
        if base is None:
            return

        params = { '_UpdateSections:tokens' : FollowupMenu }
        if base.implements('isPortalRoot'):
            url = base.absolute_url( action='followup_tasks_form', params=params )
        else:
            url = base.absolute_url( action='document_follow_up_form', params=params )

        REQUEST['RESPONSE'].redirect( url )

    def getBase( self ):
        try:
            base = self.parent().getBase()
        except:
            parents = self.parentsInThread()
            base = parents and parents[0] or None
        return base

    def getTaskPortalLink( self, uid=None, check_catalog=None ):
        """
            Checks and returns task's portal url by uid
        """
        if not uid:
            check_catalog = 0
            IsUidValid = 0
            ob = None

        if check_catalog:
            catalog = getToolByName( self, 'portal_catalog', None )
            if catalog is None:
                return None

            res = catalog.searchResults( nd_uid=uid )

            try:
                ob = res[0].getObject()
                if not ob or ob != self:
                    portal_error( 'TaskItem.getTaskPortalLink', "uncataloged object with uid: %s, res: %s, path: %s !!!" % ( \
                        uid, len(res), self.physical_path() ) 
                        )
                    IsUidValid = 0
                elif ob.getId() == self.id:
                    IsUidValid = 1
            except:
                portal_error( 'TaskItem.getTaskPortalLink', "cannot get object: %s, self: %s !!!" % ( \
                    uid, `self` ) 
                    )
                return None
        else:
            IsUidValid = 1

        if IsUidValid:
            task_url ='%s/portal_links/locate?uid=%s' % ( self.portal_url(), uid )
        else:
            if ob is not None:
                task_url = ob.absolute_url( canonical=1, no_version=1 ) + '/view?expand=1'
            else:
                task_url = self.absolute_url( canonical=1, no_version=1 ) + '/view?expand=1'

        return task_url

    security.declareProtected( CMFCorePermissions.View, 'isBoundTo' )
    def isBoundTo( self, task_only=None, REQUEST=None ):
        """
            Returns the task parent.

            Result:

                Task item reference or None.
        """
        followup = getToolByName( self, 'portal_followup', None )
        if followup is None:
            return
        bound_tasks = followup.getTasksFor( self )
        parent = None
        try:
           parent = bound_tasks._getTaskParent( self.bind_to )
        except KeyError:
           # This case is totally impossible in stable
           # releases - child tasks are always removed with
           # their parent.
           self.bind_to = None
           parent = bound_tasks._getTaskParent()
        if task_only and parent is not None:
            if not parent.implements('isTaskItem'):
                parent = None
        return parent

    security.declarePrivate( 'BindTo' )
    def BindTo( self, bind_to ):
        """
            Binds this task to the parent with id 'bind_to'

            Arguments:

                'bind_to' -- Parent task id string.
        """
        if getattr( bind_to, 'meta_type', None ) == self.meta_type:
            self.bind_to = bind_to.getId()
        else:
            self.bind_to = None

    security.declareProtected( CMFCorePermissions.View, 'parentsInThread' )
    def parentsInThread( self, size=0 ):
        """
            Returns the list of items which are "above" this item in the task thread.

            Arguments:

                'size' -- Integer. If 'size' is not zero, only the closest
                          'size' parents will be returned.

            Result:

                List of parent task items.
        """
        parents = []
        current = self
        while not size or len( parents ) < size:
            parent = current.isBoundTo()
            if parent is None:
                break
            assert not parent in parents  # sanity check
            parents.insert( 0, parent )
            if parent.meta_type != self.meta_type:
                break
            current = parent
        return parents

    #
    #   Restore overloaded methods by PortalContent ==============================================================
    #
    objectValues = ObjectManager.objectValues
    objectItems = ObjectManager.objectItems
    tpValues = ObjectManager.tpValues
    #
    #   Followup catalog metadata ================================================================================
    #
    security.declarePublic( 'BrainsType' )
    def BrainsType( self ):
        """
            Returns the brains type id associated with the task.

            Result:

                String. Task brains type id.
        """
        try: tti = self.get_brains().task_type_information
        except: tti = None
        return tti and tti['id'] or None

    security.declarePublic( 'Creator' )
    def Creator( self ):
        """
            Returns the task author.

            Result:

                String.
        """
        try: creator = self.creator
        except: creator = TaskItem.inheritedAttribute('Creator')( self )
        return creator

    security.declarePublic( 'Description' )
    def Description( self, view=None, clean=None ):
        """
            Returns the task description.

            Arguments:

                view -- description for html viewing, Boolean.

                clean -- checks and clean comments fileld tag, Boolean.

            Result:

                String.
        """
        try:
            description = getattr(self, 'description', None) or ''
        except:
            description = ''
        if not view and not clean:
            description = getPlainText( description )
        elif clean == 1:
            if description.startswith( _comments[0] ):
                description = re.sub(r'%s(.*?)%s' % ( _comments[0], _comments[1] ), r'\1', description)
        elif clean == 2:
            description = re.sub(r'%s(.*?)%s(?i)' % ( _comments[0], _comments[1] ), r'\1', description)
            description = re.sub(r'%s.*?%s(?i)' % ( _comments[2], _comments[3] ), r'\n', description)
            description = getPlainText( description )
        return description.strip()

    security.declarePublic( 'InvolvedUsers' )
    def InvolvedUsers( self, no_recursive=None ):
        """
            Returns a plain list of users involved into the task. Opposite of clean duplicate listInvolvedUsers.

            Result:

                List of the user id strings.
        """
        if no_recursive is None:
            #return self.involved_users or self.getTaskResolutionInvolvedUsers() or []
            return self.involved_users or \
                   self.BrainsType() in ('directive','information',) and self.Supervisors() and \
                       self.listInvolvedUsers( recursive=1 ) or \
                   []
        return self.involved_users or []

    def OldInvolvedUsers( self ):
        """
            Returns last updated involved users list
        """
        old_involved_users = getattr( self, '_old_involved_users', None )
        return old_involved_users and old_involved_users[-1] or []

    security.declarePublic( 'Supervisors' )
    def Supervisors( self ):
        """
            Returns the supervisors assigned with the task.
            Supervisors are able to track and review the task progress in order
            to share owner's duties.

            Note:

                None result value indicates that no supervisors was assigned.

            Result:

                Users ids list or None.
        """
        res = []
        supervisors = getattr( self, 'supervisors', None ) or []
        for x in supervisors:
            if type(x) is TupleType:
                group, IsDAGroup, members = x
                res += members
            else:
                res.append( x )
        return res

    security.declarePublic( 'KickedUsers' )
    def KickedUsers( self ):
        """
            Checks and returns a plain list of users kicked into the task.

            Result:

                List of the user id strings.
        """
        if not self.canBePublished():
            return []

        old_kicked_users = getattr( self, 'kicked_users', None ) or []
        kicked_users = []
        res = []

        for user_id, kicked_date in old_kicked_users:
            user_has_response = 0
            responses = [ x for x in self.searchResponses( member=user_id ) ]
            if responses:
                responses.sort( lambda x, y: cmp(x['date'], y['date']) )
                responses.reverse()

            for x in responses:
                if x['date'] > kicked_date:
                    user_has_response = 1
                break

            if not user_has_response:
                kicked_users.append( ( user_id, kicked_date ) )
                if user_id not in res:
                    res.append( user_id )

        setattr( self, 'kicked_users', kicked_users )
        return res

    def checkKickedUser( self, uname ):
        """
            Returns true if given user has been kicked earlier
        """
        kicked_users = getattr( self, 'kicked_users', None ) or []
        for user_id, kicked_date in kicked_users:
            if user_id == uname:
                return 1
        return None

    security.declarePublic( 'SeenBy' )
    def SeenBy( self ):
        """
            Returns the list of users that have already viewed this object.

            Note:

                Should be obsolete in future releases.

            Result:

                List of user id strings.
        """
        slogger = self.get_logger()
        if slogger is not None:
            seen_by = slogger.listSeenByFor( self, default=[] )
            return seen_by
        return []

    security.declarePublic( 'StateKeys' )
    def StateKeys( self ):
        """
            A special index that describes current task state in a short string.
            Huge and dirty, rdbms should make it obsolete.
        """
        list_users_with_closed_reports = self.listUsersWithClosedReports()
        involved_users = self.InvolvedUsers( no_recursive=1 )
        pending_users = self.PendingUsers()

        state = []
        count_involved = len(involved_users)
        count_pending = len(pending_users)

        def add_state( x, state ):
            if x in state: return
            state.append( x )

        # 'task_not_started' flag indicating that task have to respondes
        if count_involved:
            if count_involved == count_pending:
                add_state( 'task_not_started', state )
            elif count_pending < count_involved:
                add_state( 'task_started', state )

        responded_users = []

        # revise or some more
        for rti in self.listResponseTypes():
            status = rti['id']
            responses = self.searchResponses( status=status )
            for r in responses:
                member = r['member']
                if member in list_users_with_closed_reports:
                    add_state( 'closed_report:%s'  % member, state )
                add_state( '%s:%s' % ( status, member ), state )
                responded_users.append( member )

        for u in involved_users:
            if u in responded_users:
                add_state( '%s:%s' % ( 'user_responded', u ), state )
            elif u in pending_users:
                add_state( '%s:%s' % ( 'pending', u ), state )

        # 'task_closed' flag indicating that task is closed by all involved users
        if not pending_users:
            add_state( 'task_closed', state )

        return state

    security.declarePublic( 'Title' )
    def Title( self, parent=None ):
        """
            Returns the task title.

            Result:

                String.
        """
        if parent:
            base = self.getBase()
            if base is not None and base.implements('isDocument'):
                return base.Title()
        try:
            title = self.title
        except:
            title = ''
        return title

    security.declarePublic( 'SearchableText' )
    def SearchableText( self ):
        """
            Used by the catalog for basic full text indexing
        """
        base = self.getBase()
        return '%s %s %s' % ( self.Title(), self.Description(), \
            base is not None and hasattr(base, 'registry_numbers') and base.registry_numbers() or '', \
            )

    security.declarePublic( 'isFinalized' )
    def isFinalized( self, in_time=None ):
        """
            Checks whether this task is finalized.

            No further responds expected from the involved users since the
            task was finalized.

            Result:

                Boolean.
        """
        if not in_time:
            return self.finalized and 1 or 0
        if not self.finalized:
            return 0
        finalized_date = self.finished()
        if finalized_date:
            return finalized_date <= self.expiration_date and 1 or 0
        return 1

    security.declarePublic( 'Commissions' )
    def Commissions( self ):
        """
            Returns the task commissions list.

            Result:

                Commissions ids. List.
        """
        commissions = []
        description = self.Description( clean=1 )
        #rfrom = re.compile( r'%s' % _comments[2], re.I+re.DOTALL )
        rfrom = re.compile( r'%s(.*)%s' % (_comments[2], _comments[3]), re.I+re.DOTALL )
        matched = rfrom.search( description )

        if description:
            a = commissions.append
            while matched:
                id = description[ matched.start(1) : matched.end(1) ]
                if id not in commissions:
                    a( id )
                matched = rfrom.search( description, matched.end() )

        return commissions

    def finished( self ):
        """ Returns finalized date """
        return self.isFinalized() and getattr( self, 'finalized_date', None) or None
    #
    #   Attributes implementation ================================================================================
    #
    security.declareProtected( CMFCorePermissions.View, 'Duration' )
    def Duration( self ):
        """
            Returns the duration of the periodical task.

            None value indicates a nonrecurrent task.

            Result:

                Integer. Time period in seconds.
        """
        return getattr( self, 'duration', None )

    security.declareProtected( CMFCorePermissions.View, 'Frequency' )
    def Frequency( self ):
        """
            Returns the frequency of the periodical task

            None value indicates a nonrecurrent task.

            Result:

                Integer. Time period in seconds.
        """
        return getattr(self, 'frequency', None)

    security.declarePublic( 'TaskTemplateDefinition' )
    def TaskTemplateDefinition( self, attr=None ):
        """
            Returns task template definition
        """
        template_id = self.TaskTemplateId()
        if not template_id:
            return None

        x = {}
        if self.isTaskAutomated():
            try:
                category_id = self.Category()
                category = self.getCategory()
                task_template_container = category.taskTemplateContainerAdapter.getTaskTemplateContainerByCategoryId( category_id )
                template = getattr( task_template_container, 'taskTemplates' )[ template_id ]
                tdef = getattr( template, 'taskDefinitions' )[0]
                x = tdef.toArray()
            except: pass

        if attr:
            if x.has_key(attr):
                x = x[ attr ]
            else:
                x = None

        return x

    def CreatedOnWorkflowState( self ):
        """ Returns workflow state at the time when task was created """
        return getattr( self, 'workflow_state', None )

    security.declarePublic( 'SuccessStatus' )
    def SuccessStatus( self ):
        """
            Returns the brains type success_status associated with the task
        """
        tti = self.get_brains().task_type_information
        try: success_status = tti['success_status']
        except: success_status = None
        return success_status

    security.declarePublic( 'TaskTemplateId' )
    def TaskTemplateId( self ):
        """ Returns task template id for workflow action
        """
        task_template_id = getattr( self, 'task_template_id', None )
        return task_template_id

    security.declareProtected( CMFCorePermissions.View, 'DocumentCategory' )
    def DocumentCategory( self ):
        """
            Indexing routine: returns the category of the parent document.

            Result:

               String.
        """
        base = self.getBase()
        if base is not None and base.implements('isCategorial'):
            return base.Category()
        elif self.Commissions():
            return 'BaseCommission'
        return None

    security.declareProtected( CMFCorePermissions.View, 'DocumentFolder' )
    def DocumentFolder( self, title_only=1 ):
        """
            Indexing routine: returns the folder title of the parent document.

            Result:

                String.
        """
        base = self.getBase()
        if base is not None and not base.implements('isPortalRoot'):
            folder = aq_parent(base)
            return title_only and folder.Title() or folder
        return None

    security.declarePublic( 'AlarmSettings' )
    def AlarmSettings( self ):
        """ Sets alarm setting
        """
        alarm_settings = getattr( self, 'alarm_settings', None )
        return alarm_settings

    security.declarePublic( 'FinalizeSettings' )
    def FinalizeSettings( self ):
        """ Sets finalize setting
        """
        finalize_settings = getattr( self, 'finalize_settings', None ) or {}
        return finalize_settings

    security.declarePrivate( 'ExpirationAlarm' )
    def ExpirationAlarm( self ):
        """
            Notifies users that task is going to expire soon.
            The method is called automatically by the portal scheduling service.
        """
        exclude_list = []
        for r in self.searchResponses():
            if r['status'] in ['commit','reject','informed','failure','task_start','task_register','revise'] and r['member'] not in exclude_list:
                exclude_list.append( r['member'] )

        self.get_brains().ExpirationAlarm( exclude_list=exclude_list, SendToCreator=0 )

    security.declareProtected( CMFCorePermissions.View, 'getHistory' )
    def getHistory( self ):
        """
            Returns the notifications history
        """
        return self.notification_history

    security.declarePublic( 'getState' )
    def getTaskState( self ):
        """
            Returns the task current state
        """
        expires = self.expires()
        effective = self.effective()
        alarm_date = expires - (expires - effective) / 10
        state = self.isFinalized() and 'finalized' or \
            expires.isPast() and 'expired' or \
            alarm_date < DateTime() and 'beforeexpiration' or \
            'inprogress'
        return state

    security.declareProtected( CMFCorePermissions.View, 'ResultCode' )
    def ResultCode( self ):
        """
            Returns the task finalization status.

            None value indicates that task is still in progress. Available
            task result codes are defined in the task brain information
            mapping.

            Result:

                String.
        """
        if hasattr(self, 'result'):
             return self.result
        else:
             return None

    security.declareProtected( CMFCorePermissions.View, 'PendingUsers' )
    def PendingUsers( self, force=None ):
        """
            Returns the list of users involved into the task who did not make any response.

            Arguments:

                force -- Boolean, 1 - used if we want to check real closed responses only (for report statistics).

            Result:

                List of the user id strings.
        """
        if self.temporal_expr:
            return []

        involved_users = self.InvolvedUsers( no_recursive=1 )

        if self.BrainsType() in ('directive',):
            responded_users = self.listRespondedUsers('commit') # [] why?
        elif self.BrainsType() in ('request','signature_request',) and self.TaskTemplateId() not in ('SelfSignature',):
            if force and self.hasDelegationOfAuthority():
                responded_users = self.listRespondedUsers()
            else:
                responded_users = self.listUsersWithClosedReports()
        else:
            responded_users = self.listRespondedUsers()

        pending_users = []
        for user in involved_users:
             if user not in responded_users:
                  pending_users.append( user )

        return pending_users

    security.declareProtected( CMFCorePermissions.View, 'SuspendedMode' )
    def SuspendedMode( self ):
        su = getattr(self, 'suspended_users', None)
        return su and 1 or 0

    security.declareProtected( CMFCorePermissions.View, 'SuspendedUsers' )
    def SuspendedUsers( self ):
        su = getattr(self, 'suspended_users', None)
        return type(su) is ListType and su or []

    def isCreator( self, uname=None ):
        """
            Checks whether the member is a task author.

            Arguments:

                'uname' -- User id string. None value indicates that current
                           authenticated member id has to be used.

            Result:

                Boolean.
        """
        if not uname:
            uname = _getAuthenticatedUser(self).getUserName()
        return uname == self.Creator()

    def isSupervisor( self, uname=None ):
        """
            Checks whether the member is a task supervisor.

            Arguments:

                'uname' -- User id string. None value indicates that current
                           authenticated member id has to be used.

            Result:

                Boolean.
        """
        if not uname:
            uname = _getAuthenticatedUser(self).getUserName()
        return uname in self.Supervisors()

    def isSuperuser( self, uname=None ):
        """
            Checks whether the member is a task author or a supervisor.

            Arguments:

                'uname' -- User id string. None value indicates that current
                           authenticated member id has to be used.

            Result:

                Boolean.
        """
        if not uname:
            uname = _getAuthenticatedUser(self).getUserName()
        return uname == self.Creator() or uname in self.Supervisors()

    def isInvolved( self, uname=None ):
        """
            Checks whether the member is involved into the task.

            Arguments:

                'uname' -- User id string. None value indicates that current
                           authenticated member id has to be used.

            Result:

                Boolean.
        """
        if not uname:
            uname = _getAuthenticatedUser(self).getUserName()
        return uname in self.InvolvedUsers( no_recursive=1 )

    def isDocumentOwner( self, uname=None ):
        """
            Checks whether the member is a document owner.

            Arguments:

                'uname' -- User id string. None value indicates that current
                           authenticated member id has to be used.

            Result:

                Boolean.
        """
        if not uname:
            uname = _getAuthenticatedUser(self).getUserName()

        base = self.getBase()
        if base is None or base.implements('isPortalRoot'):
            return 0
        if not base.implements('isDocument'):
            return 0

        if base.Creator() == uname:
            return 1
        local_roles = base.get_local_roles_for_userid( uname ) or []
        if OwnerRole in local_roles or VersionOwnerRole in local_roles:
            return 1

        return 0

    security.declarePublic( 'isViewer' )
    def isViewer( self, uname=None, check_roles=None ):
        """
            Checks whether the member participates in the task.

            Arguments:

                'uname' -- User id string. None value indicates that current
                           authenticated member id has to be used.

            Result:

                Boolean.
        """
        membership = getToolByName( self, 'portal_membership', None )
        if membership is None:
            return None

        base = self.getBase()

        if not uname:
            user = _getAuthenticatedUser(self)
            uname = user.getUserName()
        else:
            user = membership.getMemberById( uname )

        if base is not None and user:
            uroles = user.getRolesInContext( base )
        else:
            uroles = []

        IsPortalRoot = base is not None and base.implements('isPortalRoot') and 1 or 0

        if self.isInvolved( uname ) or self.isCreator( uname ) or self.isSupervisor( uname ):
            if not check_roles:
                return 1
            #elif IsPortalRoot:
            #    return 1
            elif _checkPermission('View', self):
                return 1
        if self.isDelivered( uname ):
            return 1

        if base is not None:
            if not base.implements('isDocument'):
                return None
            if base.Creator() == uname:
                return 1
            registrators = membership.expandUserList( user_groups=('REGISTRATOR',) )
            if self.Creator() in registrators and ReaderRole in uroles:
                return 1

        if check_roles:
            portal_log( self, 'TaskItem', 'isViewer', 'member, roles, IsPortalRoot, task', ( uname, uroles, IsPortalRoot, `self` ) )

        return None

    security.declarePublic( 'isTaskAutomated' )
    def isTaskAutomated( self ):
        """
            Returns true if task should be checked by workflow

            Result:

                Boolean.
        """
        return getattr( self, 'task_is_automated', None ) and 1 or 0

    security.declarePublic( 'isFinalizedSuccessfully' )
    def isFinalizedSuccessfully( self ):
        """
            Checks whether this task is finalized with success code result.

            Result:

                Boolean.
        """
        finalized_successfully = self.isFinalized() and self.ResultCode() == TaskResultCodes.TASK_RESULT_SUCCESS and 1 or 0
        return finalized_successfully

    security.declarePublic( 'isExpired' )
    def isExpired( self ):
        """
            Checks whether this task is expired.

            Result:

                Boolean.
        """
        # not self.isFinalizedSuccessfully()
        expired = not self.isFinalized() and DateTime() > getattr( self, 'expiration_date', None ) and 1 or 0
        return expired

    security.declarePublic( 'isDelivered' )
    def isDelivered( self, by_user=None ):
        """ Returns true if task was delivered
            Checks whether this task was delivered to another members.

            Result:

                Boolean.
        """
        task_was_delivered = getattr(self, 'task_was_delivered', None)
        if by_user is not None and type(task_was_delivered) is TupleType:
            delivered = task_was_delivered[0] == by_user and 1 or 0
        else:
            delivered = task_was_delivered and 1 or 0
        return delivered

    security.declarePublic( 'isEnabled' )
    def isEnabled( self ):
        """
            Checks whether this task is enabled.

            Result:

                Boolean.
        """
        return self.enabled and 1 or 0

    security.declarePublic( 'isManagedBySupervisor' )
    def isManagedBySupervisor( self ):
        """
            Returns true if supervisor will be informed only after the task is realized
        """
        return getattr( self, 'managed_by_supervisor', None ) or 'default'

    security.declarePublic( 'isFollowupFinalized' )
    def isFollowupFinalized( self, template_id, base=None ):
        """
            Checks if followup of automated bound tasks with given template id are finalized
        """
        if not self.isFinalized():
            return 0

        if base is None:
            base = self.getBase()
        if base is None or base.implements('isPortalRoot'):
            return 1

        followup = base.followup.getBoundTasks( recursive=None )
        if not followup:
            return 1

        for task in followup:
            if task.getId() == self.getId():
                continue
            if task.isTaskAutomated() or task.isBoundTo():
                if task.TaskTemplateId() == template_id:
                    if not task.isFinalized():
                        return 0

        return 1

    security.declarePublic( 'canBePublished' )
    def canBePublished( self ):
        """
            Checks whether the task can be publish
        """
        if self.isFinalized() or not self.isEnabled():
            return 0
        return 1

    security.declareProtected( CMFCorePermissions.View, 'canRespond' )
    def canRespond( self, status=None, force=None ):
        """
            Checks whether the user is able to respond with the given status.

            Arguments:

                'force' -- ignore response condition property, Boolean.

            Result:

                Boolean.
        """
        allowed_ids = [ rti['id'] for rti in self.listAllowedResponseTypes( force=force, check_demand_revision=1 ) ]
        if status:
            return status in allowed_ids and 1 or 0
        return allowed_ids and 1 or 0

    security.declareProtected( CMFCorePermissions.View, 'canSendNotifications' )
    def canSendNotifications( self ):
        """
            Checks whether the user can send notifications to the involved users.

            Result:

                Boolean.
        """
        user = _getAuthenticatedUser(self)
        IsManager = user.has_role('Manager')
        IsWriter = user.has_role('Writer')
        uname = user.getUserName()

        can_send_notifications = self.canBePublished() and ( \
            self.InvolvedUsers( no_recursive=1 ) or \
            self.isCreator( uname ) or \
            self.isSupervisor( uname ) or \
            self.isDocumentOwner( uname ) or \
            self.isDelivered( uname ) or \
            IsManager or \
            IsWriter )

        return can_send_notifications

    security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'setInvolvedUsers' )
    def setInvolvedUsers( self, involved_users ):
        """
            Sets the task involved users.
            Involved users are responsible for perfoming the task.

            Arguments:

                'involved_users' -- List of the involved users id strings.
        """
        if self.involved_users:
            old_involved_users = getattr( self, '_old_involved_users', None ) or []
            old_involved_users.append( tuple(self.involved_users) )
            setattr( self, '_old_involved_users', old_involved_users )
        self.involved_users = involved_users
        if self.isEnabled():
            self.updateIndexes( idxs=['InvolvedUsers',] )

    security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'setSupervisors' )
    def setSupervisors( self, supervisors=None ):
        """
            Sets the task supervisors.

            Arguments:

                'supervisors' -- Superisors tuple: ( [ ids ], managed_by_supervisor option, ).
        """
        if self.Supervisors():
            setattr( self, '_old_supervisors', self.Supervisors() )
        if supervisors is not None and type(supervisors) is TupleType:
            if supervisors[0] is not None:
                self.supervisors = supervisors[0]
            self.managed_by_supervisor = supervisors[1]
        else:
            self.supervisors = None
        if self.isEnabled():
            self.updateIndexes( idxs=['Supervisors',] )

    security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'setKickedUsers' )
    def setKickedUsers( self, kicked_users ):
        """
            Updates kicked users list
        """
        if not kicked_users:
            return

        old_kicked_users = getattr( self, 'kicked_users', None ) or []
        now = DateTime()

        for user_id in kicked_users:
            if not user_id in old_kicked_users:
                old_kicked_users.append( ( user_id, now ) )

        setattr( self, 'kicked_users', old_kicked_users )
        self.updateIndexes( idxs=['KickedUsers',] )

    security.declareProtected( CMFCorePermissions.View, 'setFollowupTasks' )
    def setFollowupTasks( self, followup_tasks ):
        """
            Sets the list of tasks that to be enabled just after current task finishes.

            Arguments:

                'followup_tasks' -- List of task ids.
        """
        self.followup_tasks = followup_tasks

    security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'setPlanTime' )
    def setPlanTime( self, time ):
        """
            Sets the time required to acomplish with the task as it was planned by the task author.

            Arguments:

                'time' -- Integer. Planned time in seconds.
        """
        self.plan_time = time

    def setWorkflowState( self, base=None ):
        """
            Sets wor
        """
        if base is None:
            base = self.getBase()
        workflow_state = base.implements('isDocument') and base.getWorkflowState() or None
        self.workflow_state = workflow_state

    security.declareProtected( CMFCorePermissions.View, 'getPlanTime' )
    def getPlanTime( self ):
        """
            Returns the time required to acomplish with the task as it was planned by the task author.

            Result:

              'time' -- Integer. Planned time in seconds.
        """
        return self.plan_time

    security.declarePrivate( 'setActualTimeFor' )
    def setActualTimeFor( self, uname, time):
        """
           Sets the time actual required to acomplish with the task as it was reported by the involved user.

           Arguments:

               'uname' -- User id string.

               'time' -- Integer. Planned time in seconds.
        """
        self.actual_times[uname] = time

    security.declareProtected( CMFCorePermissions.View, 'getActualTimeFor' )
    def getActualTimeFor( self, uname ):
        """
            Returns the actual time required to acomplish with the task as it was reported by the involved user.

            Result:

                'time' -- Integer. Planned time in seconds.
        """
        return self.actual_times.get(uname, None)

    security.declareProtected( CMFCorePermissions.View, 'setEffectiveDate' )
    def setEffectiveDate( self, effective_date=None ):
        """
            Sets the task effective date.

            Arguments:

                'effective_date' -- DateTime class instance.

            Note:

                In case the task expiration date is less then effective date,
                expiration date becomes equal to next day after the task
                effective date.
        """
        if effective_date is not None:
            self.effective_date = self._datify( effective_date )
        is_future = self.effective().isFuture()

        if self.isEnabled() and is_future:
            self.Disable()
        if self.effective() > self.expires():
            self.setExpirationDate( self.effective() + 1.0 )
        if not is_future:
            return
        scheduler = getToolByName( self, 'portal_scheduler', None )
        if scheduler is None:
            return

        element_ids = self._effective_schedule_id
        self.delScheduleIds( element_ids )

        task_url = self.getTaskPortalLink( uid=self.getUid(), check_catalog=0 ) or ''
        temporal_expr = DateTimeTE( self.effective() )

        self._effective_schedule_id = scheduler.addScheduleElement( self.Enable
                    , title="[Begin] %s $ %s" % ( self.Title(), task_url )
                    , temporal_expr=temporal_expr
                    , prefix='B'
                    )

    security.declareProtected( CMFCorePermissions.View, 'setExpirationDate' )
    def setExpirationDate( self, expiration_date=None ):
        """
            Sets the task expiration date.

            Arguments:

                'effective_date' -- DateTime class instance.
        """
        if expiration_date is not None:
            self.expiration_date = self._datify( expiration_date )

        if not getattr(self, 'expiration_date', None):
            return
        if self.TaskTemplateId() in ( 'SelfSignature', ):
            return
        scheduler = getToolByName( self, 'portal_scheduler', None )
        if scheduler is None:
            return

        element_ids = self._expiration_schedule_id
        self.delScheduleIds( element_ids )

        task_url = self.getTaskPortalLink( uid=self.getUid(), check_catalog=0 ) or ''

        # Notify when task time is left
        time_next = self.expires() # - ( self.expires() - self.effective() ) / 10
        temporal_expr = DateTimeTE( time_next )

        self._expiration_schedule_id = scheduler.addScheduleElement( self.ExpirationAlarm
                    , title="[Expiration Alarm] %s $ %s" % ( self.Title(), task_url )
                    , temporal_expr=temporal_expr
                    , prefix='E'
                    )

    security.declareProtected( CMFCorePermissions.View, 'setPeriodicalScheduleEvents' )
    def setPeriodicalScheduleEvents( self, temporal_expr=None, duration=None ):
        """
            Sets up the peridical task schedule events
        """
        if temporal_expr and duration:
            self.temporal_expr = temporal_expr
            self.duration = duration

        if not ( self.temporal_expr and not self.duration ):
            return
        scheduler = getToolByName( self, 'portal_scheduler', None )
        if scheduler is None:
            return

        task_url = self.getTaskPortalLink( uid=self.getUid(), check_catalog=0 ) or ''

        element_ids = self._task_schedule_id
        self.delScheduleIds( element_ids )

        self._task_schedule_id = scheduler.addScheduleElement( self.createTask
                    , temporal_expr=self.temporal_expr
                    , title="%s $ %s" % ( self.Title(), task_url )
                    , prefix='C'
                    , kwargs={ \
                          'title'          : self.Title()
                        , 'description'    : self.Description()
                        , 'creator'        : self.Creator()
                        , 'involved_users' : self.involved_users
                        , 'duration'       : self.duration
                        , 'bind_to'        : self.getId()
                    } \
                )

    security.declarePublic( 'setNotifyMode' )
    def setNotifyMode( self, notify_mode=None ):
        """
            Sets notify mode: 1 - with NotifyList.
        """
        self.notify_mode = notify_mode and 1 or 0
        return

    security.declarePublic( 'getNotifyMode' )
    def getNotifyMode( self ):
        """
            Returns notify mode: 1 - with NotifyList
        """
        return self.notify_mode and 1 or 0

    security.declarePublic( 'getNotifyList' )
    def getNotifyList( self, isclosed=None ):
        """
            Returns users who did not satisfied request
        """
        notify_list = []
        involved_users = self.InvolvedUsers( no_recursive=1 )

        for member in involved_users:
            if not self.UserSatysfiedRequest( layer=None, member=member, isclosed=isclosed ):
                notify_list.append( member )

        for member in self.Supervisors():
            if member not in notify_list:
                notify_list.append( member )

        return notify_list

    security.declarePublic( 'getCreatorAndSupervisors' )
    def getCreatorAndSupervisors( self, send=None ):
        """
            Returns Creator and Supervisors users name. Check 'managed by supervisor' if we send alarm message
        """
        notify_list = []

        creator = self.Creator()
        if creator:
            notify_list.append( creator )

        if not send or not self.isManagedBySupervisor():
            for member in self.Supervisors():
                if member not in notify_list:
                    notify_list.append( member )

        return notify_list

    security.declarePublic( 'getEnableDate' )
    def getEnableDate( self ):
        return getattr( self, 'enable_date', None )
    #
    #   Management implementation ================================================================================
    #
    def check_and_update_permissions( self, members=None, roles=None, reindex=None, check_only=None, notify=None ):
        """
            Checks and updates tasks involved users permissions for allowed objects list.

            Arguments:

                'members' -- List, involved users list.

                'roles' -- List, roles list to check.

                'reindex' -- Boolean, should be reindexed in any case.

                'check_only' -- Boolean, try to check it only, don't modify.

                'notify' -- Boolean, notify members if updated.

            Results:

                Int, count of modified objects.
        """
        #membership = getToolByName( self, 'portal_membership', None )
        if not self.isEnabled(): # or membership is None:
            return 0

        base = self.getBase()
        objects = [ self ]
        if base is not None:
            IsPortalRoot = base.implements('isPortalRoot')
            if not IsPortalRoot:
                objects.append( base )
                links = getToolByName( self, 'portal_links', None )
                if links is not None:
                    for ob in links.getObjectLinks( base, return_objects=1 ):
                        if ob is None or not ob.implements('isDocument'):
                            continue
                        objects.append( ob )

        if not members:
            members = self.InvolvedUsers()
        if not roles:
            roles = not self.isFinalized() and self.hand_roles or [ ReaderRole ]

        updated_members = []
        total_updated = 0

        for item in range(len(objects)):
            ob = objects[ item ]
            if ob is None: continue
            #editors = membership.listAllowedUsers( ob, [ EditorRole ], 0 )
            IsUpdated = 0
            for user in members:
                #if user in editors:
                #    continue
                local_roles = ob.get_local_roles_for_userid( user ) or []
                if OwnerRole in local_roles: # or EditorRole in local_roles:
                    continue
                updated_roles = [ x for x in roles if not x in local_roles ]
                if updated_roles:
                    if not check_only:
                        UpdateRolePermissions( ob, user, updated_roles )
                        if item == 0 and not user in updated_members:
                            updated_members.append( user )
                    IsUpdated = 1

            if ( IsUpdated and not check_only ) or reindex:
                ob.reindexObject( idxs=['allowedRolesAndUsers'] )
            if IsUpdated:
                total_updated += 1

        self.modification_date = DateTime()

        if notify and updated_members:
            self.send_notifications( updated_members, no_supervisor=1 )

        if total_updated:
            portal_log( self, 'TaskItem', 'check_and_update_permissions', 'members', ( \
                updated_members, roles, total_updated, self.physical_path() ) \
                )

        return total_updated

    security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'updateIndexes' )
    def updateIndexes( self, idxs=None, check_path=None ):
        """
            Catalog object in *portal_followup*
        """
        followup = getToolByName( self, 'portal_followup', None )
        if followup is None:
            return

        task = self
        current_path = self.physical_path()
        if idxs is None: idxs = []
        IsUncataloged = 0

        if check_path == 1 and not IsThreadActivated( followup ):
            res = followup.unrestrictedSearch( id=self.getId() )
            for x in res:
                try: ob = x.getObject()
                except: continue
                path = x.getPath()
                if ob is None:
                    followup.uncatalog_object( path )
                    IsUncataloged = 1
                elif current_path != path:
                    task = ob

        self.modification_date = DateTime()

        portal_log( self, 'TaskItem', 'pdateIndexes', 'reindexed', ( idxs, task.physical_path(), IsUncataloged ) )
        followup.reindexObject( task, idxs )

    security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'Enable' )
    def Enable( self, no_mail=None ):
        """
            Enables the task.

            Arguments:

                'no_mail' -- Disable mail notifications.

            Sends mail notifications and allows involved users to write their reports.
        """
        self.enabled = 1
        setattr( self, 'enable_date', DateTime() )
        self.updateIndexes( idxs=['isEnabled', 'Commissions',] )

        involved_users = self.InvolvedUsers( no_recursive=1 )
        old_involved_users = self.OldInvolvedUsers()
        included_users = filter( lambda x, t=old_involved_users: x not in t, involved_users )
        excluded_users = filter( lambda x, t=involved_users: x not in t, old_involved_users )
        restricted_users = list( excluded_users )
        granted_users = list( included_users )
        granted_supervisors = []
        creator = self.Creator()

        old_supervisors = getattr( self, '_old_supervisors', [] )
        supervisors = self.Supervisors()

        # Check whether the task supervisors have been changed since last Enable() call
        if supervisors != old_supervisors:
            if old_supervisors:
                restricted_users.extend( old_supervisors )
            if supervisors:
                granted_supervisors = supervisors
        for supervisor in supervisors:
            if supervisor in restricted_users:
                restricted_users.remove( supervisor )
            if supervisor in granted_users:
                granted_users.remove( supervisor )
        if creator in granted_supervisors:
            granted_supervisors.remove( creator )
        if creator in restricted_users:
            restricted_users.remove( creator )

        base = self.getBase()
        IsPortalRoot = base is not None and base.implements('isPortalRoot')
        reindex = 0

        if restricted_users:
            self.manage_delLocalRoles( restricted_users )
            reindex = 1
            if not IsPortalRoot:
                # Delete local roles from the document only for those users who are not participating
                # in any of the document's tasks.
                participants = []
                for task in self.followup.objectValues():
                    participants.extend( task.InvolvedUsers( no_recursive=1 ) )
                    participants.append( task.Creator() )
                    participants.extend( task.Supervisors() )

                if participants:
                    restricted_users = filter( lambda u, p=participants: u not in p, restricted_users )
                if restricted_users:
                    base.manage_delLocalRoles( restricted_users )

        if granted_supervisors:
            self.check_and_update_permissions( members=granted_supervisors, roles=[ WriterRole ] )
        self.check_and_update_permissions( members=granted_users, reindex=reindex )

        if not no_mail:
            self.send_notifications( included_users, excluded_users )

    security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'Disable' )
    def Disable( self ):
        """
            Disables the task
        """
        self.enabled = 0
        self.updateIndexes( idxs=['isEnabled',] )

    security.declareProtected( CMFCorePermissions.View, 'DeliverExecution' )
    def DeliverExecution( self, REQUEST ):
        """
            Deliver the task to new executors.
            This function is used in order to deliver (entrust) the duties to another members
        """
        if REQUEST is None:
            return None
        involved_users = REQUEST.get('involved', None)

        portal_info( 'TaskItem.DeliverExecution', '%s:%s' % ( self.getId(), involved_users ) )
        if not involved_users:
            return None

        user_id = _getAuthenticatedUser(self).getUserName()
        if not user_id in self.InvolvedUsers( no_recursive=1 ):
            return None

        self.setInvolvedUsers( involved_users )
        self.check_and_update_permissions( members=involved_users, reindex=1 )

        description = REQUEST.get('description', None)
        if description and self.Description( view=1 ) != description:
            self.setDescription( description )
            self.updateIndexes( idxs=['Commissions',] )

        setattr(self, 'task_was_delivered', (user_id, involved_users, DateTime()))
        return 1

    security.declareProtected( CMFCorePermissions.View, 'edit' )
    def edit( self
                , title=None
                , involved_users=None
                , description=None
                , supervisors=None
                , duration=None
                , alarm_settings=None
                , finalize_settings=None
                , temporal_expr=None
                , plan_time=None
                , notify_mode=None
                , effective_date=None
                , expiration_date=None
                , expiration_alarm=None
                , notify_of_changes=None
                , no_commit=None
            ):
        """
            Changes task properties and sends mail notfications.
        """
        portal_info( 'TaskItem.edit', '%s:%s:%s' % ( self.getId(), involved_users, supervisors ) )

        excluded_users = included_users = suspended_users = None
        changes = {}

        def apply_changes( context, method, *args ):
            bound_tasks = context.isInTurn() and context.listFollowupTasks() or []
            for task_id in bound_tasks:
                task = context.getTask(task_id)
                if task is None:
                    continue
                apply( getattr(task, method), args )
            apply( getattr(context, method), args )

        if title is not None and self.Title() != title:
            self.setTitle( title )
            changes.update( { 'task_title' : self.Title() } )

        if description is not None and self.Description( view=1 ) != description:
            self.description = _parse_comments( description )
            changes.update( { 'task_description' : self.Description() } )

        if involved_users is not None:
            current_involved_users = self.InvolvedUsers( no_recursive=1 )
            excluded_users = filter( lambda x, t=involved_users: x not in t, current_involved_users )
            included_users = filter( lambda x, t=current_involved_users: x not in t, involved_users )
            suspended_users = []

            if included_users:
                suspended_users, included_users = self.checkInvolvedUsersThreshold( included_users )

            if excluded_users or included_users or suspended_users:
                self.setInvolvedUsers( involved_users )
                changes.update({'task_included_users': suspended_users+included_users, 'task_excluded_users': excluded_users})

        if supervisors is not None:
            self.setSupervisors( supervisors )
            changes.update({'task_supervisors': supervisors})

        if expiration_date is not None and self.expires() != expiration_date:
            apply_changes( self, 'setExpirationDate', expiration_date )
            changes.update({'task_expiration_date': self.expires()})

        if effective_date is not None and self.effective() != effective_date:
            apply_changes( self, 'setEffectiveDate', effective_date )
            changes.update({'task_effective_date': self.effective()})

        self.finalize_settings = finalize_settings and finalize_settings.copy() or {}
        self.setAlarm( alarm_settings or {} )

        if temporal_expr or duration:
            if not temporal_expr:
                temporal_expr = self.temporal_expr
            elif temporal_expr != self.temporal_expr:
                changes['task_te'] = temporal_expr
            if not duration:
                duration = self.duration
            elif duration != self.duration:
                changes['task_duration'] = duration

            self.setPeriodicalScheduleEvents( temporal_expr, duration )

        if plan_time is not None:
            self.setPlanTime( plan_time )
            changes['plan_time'] = plan_time

        if self.notify_mode != notify_mode:
            apply_changes( self, 'setNotifyMode', notify_mode )
            changes['notify_mode'] = notify_mode

        if len(changes) == 0:
            return

        self.ShouldBeSeenByFor()

        apply_changes( self, 'updateIndexes' )

        if self.isEnabled() and ( included_users or excluded_users or supervisors ):
            self.Enable( no_mail=1 )
            self.send_notifications( included_users, excluded_users )

        if notify_of_changes:
            notify_list = self.getNotifyList()
            self.send_mail( notify_list, 'mail_changes', **changes )

        self.HasBeenSeenByFor()

        if not self.CreatedOnWorkflowState():
            self.setWorkflowState()

    security.declareProtected( CMFCorePermissions.View, 'Respond' )
    def Respond( self, status, text='', document=None, close_report=None, redirect=1, no_commit=None, 
            no_update_runtime=None, force=None, REQUEST=None, **kw ):
        """
            Adds user response to the collection.

            Arguments:

                'status' -- response type. This can one of the status values
                           defined in the task type info mapping

                'text' -- user comment

                'close_report' -- indicates whether this report is modifiable or not

                'REQUEST' -- additional parameters to be passed to the response handlers
        """
        # for testing reason
        x_user_name = kw is not None and kw.get('x_user_name')
        # if not, check real authorization
        if not x_user_name:
            if not self.canRespond( status, force ):
                raise Unauthorized, 'unauthorized to respond'

        membership = getToolByName( self, 'portal_membership', None )
        catalog = getToolByName( self, 'portal_catalog', None )
        links = getToolByName( self, 'portal_links', None )
        msg = getToolByName( self, 'msg', None )
        message= ''

        if membership is None or catalog is None or links is None or msg is None:
            return ( None, '' )

        if not no_commit:
            BeginThread( self, 'TaskItem.Respond', force=1 )

        start_time = DateTime()
        uname = x_user_name or _getAuthenticatedUser(self).getUserName()
        task_id = self.getId()

        REQUEST = check_request( self, REQUEST )

        uip = REQUEST.get('HTTP_X_FORWARDED_FOR', None) or REQUEST.REMOTE_ADDR
        remarks = REQUEST.get('remarks', [])
        text = text.strip()
        text = re.sub(r'(<br>)+</div>(?i)', '</div>', text)
        fileid = ''

        disable = REQUEST.get('disable')
        check_if_we_should_update_seenbyfor = 0 # don't apply it for increase in efficiency

        base = self.getBase()
        if base is not None:
            if not base.implements('isDocument'):
                base = None
            else:
                base_uid = base.getUid()
                base_absolute_url = base.absolute_url()

        rti = self.getResponseTypeById( status )
        if rti.get('manual_report_close', None):
            isclosed = close_report
        else:
            isclosed = 1
        layer = rti['layer']

        if not ( REQUEST.has_key('notify_after_commit') or no_commit ):
            REQUEST.set('notify_after_commit', {})

        try:
            file = REQUEST.get('attachment', '')
            if file:
                fileid = addFile(self, file=file)
                if base is not None and REQUEST.get('make_as_baseattachment', ''):
                    base.addFile(file=file)
        except:
            file = None

        if self.hasResponses() and remarks:
            if text:
                text += '<br>'
            text += '<font color=#cc0000>%s:</font><br>' % msg('Satisfied with remarks')

            for remark_id in remarks:
                try:
                    response = self.get_responses().getResponseById( int(remark_id) )
                except:
                    response = None
                if response is not None and type(response) is DictType:
                    r_text = response.get('text').strip() or ''
                    r_date = response.get('date').strftime('%Y-%m-%d %H:%M')
                    text += '%s %s' % ( r_date, r_text )
            REQUEST.set('text', text)

        try:
            self.get_responses().addResponse( self \
                    , layer=layer
                    , status=status
                    , text=text
                    , member=uname
                    , isclosed=isclosed
                    , attachment=fileid
                    , uip=uip
                    , remarks=remarks
                    )

            response_id = self.get_responses().getLastResponseId()

            portal_info( 'TaskItem.Respond', 'task_id: %s, uname: %s, uip: %s, response_id: %s' % ( \
                task_id, uname, uip, response_id ) \
                )

            try:
                actual_time = parseTime('actual_time', REQUEST)
            except KeyError:
                actual_time = None

            if actual_time is not None:
                self.setActualTimeFor( uname, actual_time )

            if document is not None and document.uid:
                links.createLink( source_uid=self.getUid()
                    , destination_uid=document.uid
                    , destination_ver_id=document.version
                    , relation=0
                    , uname=uname
                    , status=status
                    , response_id=response_id
                    )

            self.updateIndexes( idxs=['StateKeys',], check_path=1 )

            if check_if_we_should_update_seenbyfor:
                if self.isInvolved():
                    users = self.getCreatorAndSupervisors()
                elif self.isCreator():
                    users = self.InvolvedUsers( no_recursive=1 )
                elif self.isSupervisor():
                    users = self.InvolvedUsers( no_recursive=1 ) + [ self.Creator() ]
                self.ShouldBeSeenByFor( uname=users )

            IsError = 0

        except ( ConflictError, ReadConflictError ):
            raise

        except Exception, msg_error:
            message = str(msg_error)
            portal_error( 'TaskItem.Respond', 'task_id: %s, uname: %s, uip: %s, response_id: %s, message: %s' % ( \
                task_id, uname, uip, response_id, message ), exc_info=1 \
                )
            IsError = 1

        if not IsError:
            if rti.has_key('handler'):
                handler = rti['handler']
                handler_func = getattr( self.get_brains(), handler )
                assert callable(handler_func), 'Handler func is not callable!'
                REQUEST.set('notify_after_commit', {})
                REQUEST.set('no_commit', 1)
                apply(handler_func, ( REQUEST, ))

        if not no_commit:
            IsDone = CommitThread( self, 'TaskItem.Respond', IsError, force=1, subtransaction=None, \
                info='%s:%s:%s' % ( uname, task_id, response_id ) )

            if IsDone == -1:
                message = '%s $ $ error' % ( 'Members weren\'t notified because of error' )

        end_time = DateTime()
        if not no_update_runtime:
            UpdateRequestRuntime( self, uname, start_time, end_time, 'TaskItem.Respond' )

        # code to prevent error when object moved via docflow:
        if redirect and REQUEST is not None:
            try:
                IsMoved = 0
                if base is not None:
                    r = catalog.searchResults( nd_uid=base_uid )
                    if r:
                        base = r[0].getObject()
                        if base.absolute_url() != base_absolute_url:
                            aq_parent(base)._getOb( base.getId() )
                            ob = base
                            IsMoved = 1
                if not IsMoved:
                    base = self.getBase()
                    if base is not None:
                        aq_parent(base)._getOb( base.getId() )
            except AttributeError:
                ob = membership.getPersonalFolder() # XXX may not exist!
            else:
                if IsError or base is None:
                    ob = self
                else:
                    ob = base
            if not message:
                message = rti.get('message', "You have committed to a task")
            params = { '_UpdateSections:tokens' : FollowupMenu }
            REQUEST['RESPONSE'].redirect( ob.absolute_url( message=message, params=params ) )
        elif IsError:
            return ( None, '' )
        else:
            return ( response_id, '', )

    security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'Finalize' )
    def Finalize( self, result_code=None, REQUEST=None ):
        """
            Finalizes task.

            Arguments:

                'result_code' -- String. Task finalization code.

            Nobody is allowed to write reports after the task was finalized.
        """
        if not result_code:
            membership = getToolByName( self, 'portal_membership', None )
            try:
                member = membership.getAuthenticatedMember()
                IsAdmin = member.IsAdmin()
            except:
                IsAdmin = 0
            if not IsAdmin:
                return
            result_code = TaskResultCodes.TASK_RESULT_SUCCESS

        if REQUEST is None:
            REQUEST = aq_get( self, 'REQUEST', None ) or {}
        if REQUEST.get('disable'):
            self.Disable()
            self.stopSchedule()
            return

        self.finalized = 1
        self.finalized_date = DateTime()
        self.result = result_code
        task_id = self.getId()

        self.check_and_update_permissions()

        portal_info( 'TaskItem.Finalize', 'task_id: %s, result_code: %s' % ( task_id, result_code ) )
        workflow = getToolByName( self, 'portal_workflow', None )

        try:
            if workflow is not None and self.isBoundTo( task_only=1 ) is None:
                workflow.onFinalize( self )

            self.stopSchedule()
            self.updateIndexes( idxs=['isFinalized','StateKeys',], check_path=1 )
            IsError = 0

        except ( ConflictError, ReadConflictError ):
            raise

        except Exception, msg_error:
            message = str(msg_error)
            portal_error( 'TaskItem.Finalize', 'task_id: %s, message: %s' % ( task_id, message ), exc_info=True )
            IsError = 1

        if not IsError:
            # Always finalize subtasks, exclude confirmed by turn
            bound_tasks = self.followup.getBoundTasks( recursive=1 )
            for task in bound_tasks:
                if task.getId() == task_id or task.isFinalized(): 
                    continue
                if result_code == TaskResultCodes.TASK_RESULT_SUCCESS and not task.isEnabled():
                    continue
                brains = task.get_brains()
                # Check acquire finalization flag to check finalize or not the subtask
                if brains.task_type_information.get('acquire_finalization_status'):
                    code = result_code
                    if code == TaskResultCodes.TASK_RESULT_FAILED and task.BrainsType() == 'request' and \
                        task.isInTurn( check_root=1, turn_type='cycle_by_turn', parent_only=1 ):
                        if task.checkDemandRevisionSuccess( check_root=0 ):
                            code = TaskResultCodes.TASK_RESULT_SUCCESS
                    task.get_brains().onFinalize( REQUEST=REQUEST, result_code=code )

        if not REQUEST.get('no_commit'):
            CommitThread( self, 'TaskItem.Finalize', IsError )

    security.declareProtected( CMFCorePermissions.View, 'KickUsers' )
    def KickUsers( self, selected_users, text, open_reports=None, REQUEST=None, **kw ):
        """
            Send and log notification to the users involved in this task.

            Results:

                Int. Count of perfomed notifications.
        """
        template_name = 'mail_notify_users'
        count = IsError = 0
        message = ''

        try:
            # Mark task as 'new' to selected users and reopen reports
            self.ShouldBeSeenByFor( uname=selected_users )

            if open_reports:
                for user in selected_users:
                    self.OpenReportFor( user )

            self.check_and_update_permissions( members=selected_users )
            uname = _getAuthenticatedUser(self).getUserName()

            notification = { 'date' : DateTime()
                           , 'actor': uname
                           , 'rcpt' : selected_users
                           , 'text' : text
                           }

            self.notification_history.append( notification )
            self._p_changed = 1

            if type(kw) is not DictType: 
                kw = {}

            #kw['task_url'] = self.absolute_url( canonical=1, no_version=1 ) + '/view?expand=1'
            kw['message'] = getPlainText( text )
            kw['open_reports'] = open_reports
            kw['actor'] = uname
            kw['raise_exc'] = 1

            count = self.send( template_name, selected_users, **kw )
            self.setKickedUsers( selected_users )

        except ( ConflictError, ReadConflictError ):
            raise

        except Exception, msg_error:
            message = str(msg_error)
            portal_error( 'TaskItem.KickUsers', 'task_id: %s, uname: %s' % ( self.getId(), uname ), exc_info=True )
            IsError = 1

        if REQUEST is not None:
            if not IsError and not message and count:
                message = 'You have sent notification to the users'
            elif IsError and not count:
                message = '%s $ $ error' % 'You haven\'t sent notification to the users because of error'
            elif not count:
                message = '%s $ $ error' % 'It\'s impossible to send notification to the users'
            REQUEST['RESPONSE'].redirect( self.absolute_url( message=message ) ) # + '?portal_status_message=' + message
        else:
            if count and type(count) is IntType:
                return count
            else:
                return 0

    security.declareProtected( CMFCorePermissions.View, 'NotifyUsers' )
    def NotifyUsers( self, in_turn=None, selected_users=None, selected_responses=None, text=None, open_reports=None, \
            REQUEST=None, **kw ):
        """
            Send and log notification to the users involved in this task
        """
        template_name = 'mail_notify_users'

        membership = getToolByName( self, 'portal_membership', None )
        msg = getToolByName( self, 'msg', None )
        if membership is None or msg is None:
            return 0

        uname = _getAuthenticatedUser(self).getUserName()

        properties = getToolByName( self, 'portal_properties', None )
        no_mail = properties is None or not properties.smtp_server()
        revision_info = revision_message = message = ''
        count = IsError = 0
        message = ''

        if selected_responses:
            responses = self.parseSelectedResponses( selected_responses, in_turn=in_turn )
            if in_turn:
                revision_info = '<span style="font-size:11px;color:purple"><strong>%s:</strong></span>' % msg('Notification for selected responses')
                revision_message = '%s:' % msg('Selected responses to inform')
            else:
                revision_info = '<span style="font-size:11px;color:purple"><strong>%s:</strong></span>' % msg('Report(s) was rejected')
                revision_message = '%s:' % msg('Report(s) was rejected')

            for response in responses:
                try:
                    member = response['member']
                    date = response['date']
                    if member and date:
                        revision_info += '\n<span style="font-size:10px;color:black"><strong>%s %s</strong></span>' % ( date.strftime('%Y-%m-%d %H:%M'), membership.getMemberName(member) )
                        revision_message += '\n\n%s %s:' % ( membership.getMemberName(member), date.strftime('%Y-%m-%d %H:%M') )
                        revision_message += '\n%s' % getPlainText(str(response['text']))
                except SimpleError, message:
                    IsError = 1
        else:
            return 0

        if not selected_users:
            selected_users = [ x['member'] for x in responses ]

        if not IsError:
            if revision_message:
                revision_message += '\n\n%s:\n\n' % msg('Author remarks')
                revision_info += '\n'

            text = getPlainText(str(text))

            notification = { 'date' : DateTime()
                           , 'actor': uname
                           , 'rcpt' : selected_users
                           , 'text' : '%s%s' % ( revision_info, text )
                           }

            self.notification_history.append( notification )
            self._p_changed = 1

            if type(kw) is not DictType: 
                kw = {}

            kw['message'] = '%s%s' % ( revision_message, text )
            kw['open_reports'] = open_reports
            kw['actor'] = uname
            kw['raise_exc'] = 1
        else:
            return 0

        try:
            if in_turn:
                for task_id in self.listFollowupTasks():
                    task = self.getTask( task_id )
                    if task is None:
                        continue
                    #kw['task_url'] = task.absolute_url( canonical=1, no_version=1 ) + '/view?expand=1'
                    involved_users = task.InvolvedUsers( no_recursive=1 )

                    self.ShouldBeSeenByFor( task=task, uname=selected_users )

                    kicked_users = []
                    for user in selected_users:
                        if user in involved_users:
                            count += task.send( template_name, [ user ], **kw )
                            kicked_users.append( user )

                    if kicked_users:
                        task.setKickedUsers( kicked_users )

                if count > 0 or no_mail:
                    self.setDemandRevisionCode()

            else:
                #kw['task_url'] = self.absolute_url( canonical=1, no_version=1 ) + '/view?expand=1'
                if open_reports:
                    try:
                        selected_responses = [ x['id'] for x in responses ]
                        self.OpenReportFor( selected_responses=selected_responses )
                    except:
                        for uname in selected_users:
                            self.OpenReportFor( uname )
                count += self.send( template_name, selected_users, **kw )

        except Exception, msg_error:
            message = str(msg_error)
            portal_error( 'TaskItem.NotifyUsers', 'task_id: %s, uname: %s' % ( self.getId(), uname ), exc_info=True )
            IsError = 1

        if REQUEST is not None:
            if not IsError and not message:
                message = "You have sent notification to the users"
            if IsError and not count:
                message = '%s $ $ error' % 'You haven\'t sent notification to the users because of error'
            REQUEST['RESPONSE'].redirect( self.absolute_url( message=message ) ) # + '?portal_status_message=' + message
        else:
            if count and type(count) is IntType:
                return count
            else:
                return 0

    def UserSatysfiedRequest( self, layer=None, member=None, isclosed=None ):
        """
            Returns if user satysfied request or not.

            Result:

                Boolean.
        """
        if not member:
            member = _getAuthenticatedUser(self).getUserName()
        if layer or isclosed:
            responses = self.searchResponses( layer=layer, member=member, isclosed=isclosed )
        else:
            responses = self.searchResponses( member=member )

        IsOk = 0        
        # check revise respone only
        for r in responses:
            if r['status'] not in ['revise']:
                IsOk = 1
                break

        return IsOk

    def _isResponseManuallyClosed( self, r ):
        """ return 1 if this response are manually closed
            (not automatically)
        """
        if r['isclosed'] != 1:
            return 0
        # if closed, test attribute of manually closed
        status = r['status']
        followup = getToolByName( self, 'portal_followup', None )
        typeInfo = followup.getResponseTypeById( status )
        if typeInfo.get('manual_report_close') is not None:
            # accept this response
            return 1
        return 0

    security.declareProtected( CMFCorePermissions.View, 'listAttachments' )
    def listAttachments( self, no_inline=False, no_emailed=False ):
        """
            Returns a list of the task's file attachments (attached via responses).

            Result:

                List of (id, attachment) pairs.
        """
        items = []
        for x in self.objectItems():
            if x[0] in ('followup', 'version'):
                continue
            if getattr(x[1], 'meta_type', None) not in AttachmentTypes:
                continue
            if not _checkPermission( CMFCorePermissions.View, x[1] ):
                continue
            items.append( x )
        return items

    def listUsersWithClosedReports( self, recursive=None ):
        """
            Returns the list of users who have closed their reports.

            Result:

                List of user id strings.
        """
        res = []
        if not self.isEnabled():
            return res
        tasks = [ self ]
        if recursive:
            tasks += self.followup.getBoundTasks( recursive=1 )
        for task in tasks:
            for uname in task.InvolvedUsers( no_recursive=1 ):
                if not task.listAllowedResponseTypes( uname, check_only=1 ):
                    if uname not in res:
                        res.append( uname )
        return res

    def listUsersWithoutClosedReports( self, recursive=None ):
        """
            Returns the list of users who have not closed their reports.

            Result:

                List of user id strings.
        """
        res = []
        if not self.isEnabled():
            return res
        tasks = [ self ]
        if recursive:
            tasks += self.followup.getBoundTasks( recursive=1 )
        finalized_users = self.listUsersWithClosedReports( recursive=recursive )
        for task in tasks:
            for uname in task.InvolvedUsers( no_recursive=1 ):
                if uname not in finalized_users:
                    if uname not in res:
                        res.append( uname )
        return res

    security.declareProtected( CMFCorePermissions.View, 'listRespondedUsers' )
    def listRespondedUsers( self, status=None, recursive=None ):
        """
            Returns the list of responded users.

            Result:

                List of user id strings.
        """
        if status:
            users = map( lambda x: x['member'], self.get_responses().searchResponses( status=status ) )
        else:
            users = self.get_responses().getIndexKeys( member=1 )
        if not recursive:
            return users
        else:
            for task in self.followup.getBoundTasks( recursive=1 ):
                users.extend( task.listRespondedUsers( status=status ) )
        return uniqueValues( users )

    security.declareProtected( CMFCorePermissions.View, 'listInvolvedUsers' )
    def listInvolvedUsers( self, recursive=None ):
        """
            Returns the list of involved members. List can include involved group items also.

            Result:

                List of user/group id strings.
        """
        res = []
        finalize_settings = self.FinalizeSettings()
        queue = finalize_settings.get('queue', None)
        if queue:
            for x in queue:
                try: id = x['id']
                except: id = None
                if id is not None and id != 'users':
                    res.append( id )
                else:
                    res += x['members']
        else:
            res = getattr( self, 'involved_users', None ) or []
        if recursive:
            for task in self.followup.getBoundTasks( recursive=1 ):
                for uname in task.InvolvedUsers( no_recursive=1 ):
                    if uname not in res:
                        res.append( uname )
        return res

    security.declareProtected( CMFCorePermissions.View, 'listSupervisors' )
    def listSupervisors( self ):
        """
            Returns the list of supervisors. List can include involved group items also.

            Result:

                List of user/group id strings.
        """
        res = []
        if self.supervisors is None:
            return []
        for x in self.supervisors:
            if type(x) is TupleType:
                group, IsDAGroup, members = x
                res.append( '%s%s' % ( not group.startswith('group') and 'group:' or '', group ) )
                #res.append( group )
            else:
                res.append( x )
        return res

    security.declareProtected( CMFCorePermissions.View, 'listResultCodes' )
    def listResultCodes( self, check=None ):
        """
            Returns a list of task result codes.

            Arguments:

                'check' -- Boolean. Object state should be checked before.

            Result:

                List of codes id strings.
        """
        tti = self.get_brains().task_type_information
        codes = tti.get('results', [])

        if check:
            brains_type = self.BrainsType()
            supervisors = self.Supervisors()
            involved_users = self.InvolvedUsers( no_recursive=1 )
            pending_users = self.listUsersWithoutClosedReports()
            IsInTurn = self.isInTurn( check_root=1 )

        res = []

        for x in codes:
            id = x['id']
            if id == 'cancelled' or not check:
                res.append( x )
                continue

            IsAdd = 0

            if brains_type in ('directive','information','inspection',) and id == 'success':
                if not supervisors:
                    if not pending_users or self.get_brains().check_if_shouldFinalize():
                        IsAdd = 1
                elif self.isManagedBySupervisor() in ('default','request',):
                    if self.searchResponses( status='review' ):
                        IsAdd = 1
                elif not pending_users:
                    IsAdd = 1
            elif brains_type == 'request':
                if id == 'success':
                    if involved_users:
                        if not pending_users and not IsInTurn:
                            IsAdd = 1
                    else:
                        if self.checkDemandRevisionSuccess( check_root=1 ):
                            IsAdd = 1
                        elif self.checkIfShouldFinalize():
                            IsAdd = 1
                elif id == 'failed' and not involved_users and IsInTurn:
                    IsAdd = 1

            if IsAdd: res.append( x )

        return res

    security.declareProtected( CMFCorePermissions.View, 'listResponseTypes' )
    def listResponseTypes( self, sort=None ):
        """
          Returns a list of the user response types found in the task responses collection.

          Note:

              Should become obsolete soon.

          Result:

                List of task response type information mappings.
        """
        response_types = filter(None, [ \
            self.getResponseTypeById(id) for id in self.get_responses().getIndexKeys( status=1 ) ] )
        if not sort:
            return response_types

        ids = [ ( response_types[n]['id'], n ) for n in range(len(response_types)) ]

        if self.BrainsType() in ('request','signature_request','registration',):
            ids.sort()
            ids.reverse()
        else:
            ids.sort()

        result = [ response_types[item] for id, item in ids ]
        return result

    security.declareProtected( CMFCorePermissions.View, 'getResponseTypeById' )
    def getResponseTypeById( self, id ):
        """
            Returns a response type information, given it's id.

            Arguments:

                'id' -- Id string.

            Result:

                Response type information mapping.
        """
        tti = self.get_brains().task_type_information
        responses = tti['responses']
        for rti in responses:
            if rti['id'] == id:
                return rti
        return

    security.declareProtected( CMFCorePermissions.View, 'getResultById' )
    def getResultById( self, id ):
        """
            Returns a task result code information, given it's id.

            Task brains component defines the available task result codes.

            Arguments:

                'id' -- Code id string.

            Result:

                Result code information mapping.

        """
        tti = self.get_brains().task_type_information
        results = tti['results']
        for result in results:
            if result['id'] == id:
                return result

        return

    security.declareProtected( CMFCorePermissions.View, 'getTaskResponses' )
    def getTaskResponses( self ):
        """
            Returns the ResponseCollection object
        """
        return self.get_responses().__of__(self)

    security.declarePrivate( 'OpenReportFor' )
    def OpenReportFor( self, uname=None, selected_responses=None ):
        """
            Opens selected reports list for the given user.

            Arguments:

                'uname' -- User id string.

                'selected_responses' -- Responses ids list to update as opened.

            Opened reports can be modified in any time until the task is not finalized.
        """
        container = self.get_responses()

        if not selected_responses:
            kw = {}
            if self.BrainsType() == 'directive':
                kw['status'] = 'commit'
            kw['member'] = uname
            kw['isclosed'] = 1
            selected_responses = list(self.get_responses()._searchResponsesIds( **kw ))

        for rid in selected_responses:
            container.editResponse( rid, { 'isclosed' : 0, 'response_status' : 'rejected' } )

        return
    #
    #   Containment events handlers ==============================================================================
    #       'self' -- TaskItem object, not container
    #       'item' -- HTMLDocument object, which consists this discussion container
    #       'container' -- Heading object, which consists this document
    #
    def _check_containment( self, mode=None ):
        """
            Checks either task exists in the followup catalog
        """
        followup = getToolByName( self, 'portal_followup', None )
        if followup is None:
            return None

        id = self.getId()
        uid = self.getUid()

        if IsThreadActivated( followup ):
            IsFound = mode == 'delete' and 1 or -1
        else:
            try:
                res = followup.unrestrictedSearch( id=id )
                IsFound = res and len(res) or -1
                if IsFound > 1 and uid:
                    for x in res:
                        obj = x.getObject()
                        if obj.getUid() == uid:
                            IsFound = 1
                            break
                if IsFound > 1:
                    raise
            except:
                IsFound = None

        if mode == 'add':
            if IsFound == -1:
                followup.registerTask( self )
        elif mode == 'delete':
            if IsFound == 1:
                followup.unindexObject( self )

        return IsFound

    def _containment_onAdd( self, item, container ):
        """
            Create tasks container and try to reindex task if exists.
        """
        if aq_base(container) is aq_base(self):
            return
        IsFound = self._check_containment('add')
        if IsFound is None or IsFound == 1:
            return
        if self.isFinalized() or self.isExpired():
            return
        portal_log( self, 'TaskItem', '_containment_onAdd', 'IsFound', IsFound )
        self.resetSchedule()

    def _containment_onDelete( self, item, container ):
        """
            Remove self from the catalog.
        """
        if aq_base(container) is aq_base(self):
            return
        IsFound = self._check_containment('delete')
        if IsFound is None or IsFound == -1:
            return
        portal_log( self, 'TaskItem', '_containment_onDelete', 'IsFound', IsFound )
        self.stopSchedule()

    #def manage_beforeDelete( self, item, container ):
    #    pass

    #
    #   Scheduler tasks interface ================================================================================
    #
    security.declareProtected( CMFCorePermissions.View, 'getScheduleStatus' )
    def getScheduleStatus( self ):
        """
            Returns schedule element associated with the task.
        """
        scheduler = getToolByName( self, 'portal_scheduler', None )
        if scheduler is None:
            return None
        schedule_id = self._task_schedule_id
        try: 
            x = schedule_id and scheduler.getScheduleElement( schedule_id )
        except: 
            x = None
        return x

    security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'setSchedule' )
    def setSchedule( self ):
        """
            Sets up the task schedule events
        """
        self.setEffectiveDate()
        self.setExpirationDate()
        self.setPeriodicalScheduleEvents()
        self.setAlarm( force=1 )
        self.setSuspendedMail( force=1 )

    security.declarePrivate( 'resetSchedule' )
    def resetSchedule( self ):
        """
            Restarts all recurrent events associated with the task.
        """
        self.stopSchedule()
        try:
            self.setSchedule()
        except:
            pass

    security.declarePrivate( 'stopSchedule' )
    def stopSchedule( self ):
        """
            Disables all recurrent events associated with the task.

            Result:

                Boolean. Returns True in case every schedule element was
                successfully stopped or False otherwise.
        """
        IsStoped = self.delScheduleIds()
        if IsStoped:
            self._effective_schedule_id = None
            self._expiration_schedule_id = None
            self._task_schedule_id = None
            self._alarm_schedule_id = None
            self._finalize_schedule_id = None
            self._suspended_mail_id = None
            self._notify_schedule_id = None
        return IsStoped

    security.declarePrivate( 'delScheduleIds' )
    def delScheduleIds( self, ids=MissingValue ):
        if ids is MissingValue:
            ids = [ self._effective_schedule_id, self._expiration_schedule_id, self._task_schedule_id, \
                    self._alarm_schedule_id, self._finalize_schedule_id, \
                    getattr(self, '_suspended_mail_id', None), \
                    getattr(self, '_notify_schedule_id', None)
                    ]
        if type(ids) is not ListType:
            ids = [ ids ]
        ids = filter( None, ids )
        if not ids:
            return 1
        try:
            scheduler = getToolByName( self, 'portal_scheduler', None )
            scheduler.delScheduleElement( ids )
        #except ( ConflictError, ReadConflictError ):
        #    raise
        except AttributeError:
            pass
        except SimpleError, message:
            raise message
        except:
            pass
        portal_log( self, 'TaskItem', 'delScheduleIds', 'element_ids:[%s]' % ids, force=1 )
        return 1
    #
    #   Mail supporter ===========================================================================================
    #
    def send_notifications( self, included_users=None, excluded_users=None, no_supervisor=None ):
        """
            Sends mail notifications to involved and restricted users
        """
        involved_users = self.InvolvedUsers( no_recursive=1 )
        old_involved_users = self.OldInvolvedUsers()

        # Notify included users via email
        if included_users is None:
            included_users = filter( lambda x, t=old_involved_users: x not in t, involved_users )
        if included_users:
            self.send_mail( included_users, 'mail_user_included' )

        # Notify excluded users via email
        if excluded_users is None:
            excluded_users = filter( lambda x, t=involved_users: x not in t, old_involved_users )
        if excluded_users:
            self.send_mail( excluded_users, 'mail_user_excluded' )

        if no_supervisor:
            return

        # Check whether the task supervisors have been changed since last Enable() call
        old_supervisors = getattr( self, '_old_supervisors', [] )
        supervisors = self.Supervisors()
        if supervisors != old_supervisors:
            if old_supervisors:
                self.send_mail( old_supervisors, 'mail_supervisor_canceled' )
            if supervisors:
                self.send_mail( supervisors, 'mail_supervisor_notify' )

    def send_mail( self, members, template_name, **kw ):
        """
            Sends mail notification to the selected users

            Arguments:

                'members' -- List of user id strings.

                'template_name' --  DTML mail template id string. Mail templates
                                    objects are defined within the task brains
                                    component.

                '**kw' -- Additional keyword parameters will be passed to the
                          mail template.

            TODO: template args (task_title, task_url, lang...)
        """
        IsSystemProcess = kw.get('user_who_finalize') == 'System Processes' and 1 or 0
        if self.hasAutoFinalized() and IsSystemProcess:
            return
        # don't send mail to yourself
        uname = _getAuthenticatedUser(self).getUserName()
        if type(members) is ListType and uname in members:
            members.remove( uname )
        if not members:
            return

        REQUEST = check_request( self )

        if REQUEST.has_key('notify_after_commit'):
            logger.info('REQUEST has notify_after_commit')
            uid = self.getUid()
            notify_after_commit = REQUEST.get('notify_after_commit') or {}
            x = notify_after_commit.get( uid, [] )
            antispam = {}
            if CheckAntiSpam( self ):
                brains_type = self.BrainsType()
                for member_id in members:
                    antispam[ member_id ] = CheckAntiSpam( self, member_id, brains_type )
            x.append( ( self.send_and_check, ( template_name, members, antispam ), kw ) )
            notify_after_commit[ uid ] = x
            REQUEST.set('notify_after_commit', notify_after_commit)
        else:
            logger.info('TaskItem.send_mail no notify_after_commit' )
            self.send( template_name, members, **kw )

    def send_and_check( self, *args, **kw ):
        try:
            return apply( self.send, args, kw )
        except:
            if getattr(self, '_notify_schedule_id', None):
                self.delScheduleIds( [ self._notify_schedule_id ] )

            scheduler = getToolByName( self, 'portal_scheduler', None )
            properties = getToolByName( self, 'portal_properties', None )
            if scheduler is None:
                return

            try:
                frequency = int(properties.getProperty('mail_frequency', '1')) * 60
            except:
                frequency = 3 * 60

            start_date = DateTime() + float(frequency) / 86400

            task_url = self.getTaskPortalLink( uid=self.getUid(), check_catalog=0 ) or ''
            temporal_expr = UniformIntervalTE( frequency, start_date=start_date, end_date=self.expires() )

            kw['notify_after_commit'] = 1

            self._notify_schedule_id = scheduler.addScheduleElement( self.send
                    , title="[NAC] %s $ %s" % ( self.Title(), task_url )
                    , temporal_expr=temporal_expr
                    , prefix='S'
                    , args=args, kwargs=kw
                )

            raise

    def send( self, template_name, members, antispam=None, **kw ):
        """
            Sends mail with antispam control
        """
        if not template_name:
            return 0
        if hasattr(self, template_name):
            template = getattr( self, template_name )
        else:
            template = getattr( self.get_brains(), template_name )
        if template is None:
            return 0

        assert callable(template), 'Template func is not callable!'

        task_url = self.getTaskPortalLink( uid=self.getUid(), check_catalog=0 )
        if not task_url:
            portal_info( 'TaskItem.send', 'task url is undefined, item: %s' % self.physical_path() )
            return 0

        if not ( kw and kw.get('no_commit', 0) ):
            if not CommitThread( self, 'TaskItem.send', force=1, info=( task_url, members, ) ):
                return 0

        try:
            base = self.getBase()
        except:
            base = None

        if base is not None:
            IsDocument = base.implements('isDocument') and 1 or 0
            IsPortalRoot = base.implements('isPortalRoot') and 1 or 0
        else:
            IsDocument = IsPortalRoot = 0

        if IsDocument:
            topic = str(base.Title()).strip()
            doc_description = str(base.Description()).strip()
            doc_title = base.getInfoForLink( mode=1 ) or topic
            if not doc_title.endswith('.'):
                doc_title += '.'
        else:
            topic = ''
            doc_description = None
            doc_title = None

        task_description = self.Description()
        if task_description == topic:
            task_description = None
        elif task_description and task_description[-1:] not in '.!?':
            task_description += '.'

        kw['doc_title'] = doc_title
        kw['doc_description'] = doc_description
        kw['task_description'] = task_description

        if not kw.has_key('task_url') or kw['task_url'] != task_url:
            kw['task_url'] = task_url

        lang = hasattr(self, 'REQUEST') and self.REQUEST.get('lang')
        IsAntiSpam = antispam and 1 or CheckAntiSpam( self )

        raise_exc = kw.has_key('raise_exc') and kw['raise_exc'] or False

        host = self.MailHost

        if not IsAntiSpam:
            mail_text = template( self
                             , task_id=self.id
                             , task_title=self.Title()
                             , lang=lang
                             , IsPortalRoot=IsPortalRoot
                             , IsAntiSpam=0
                             , **kw 
                             )

            count = host.send( msg=host.createMessage( source=mail_text )
                             , mto=members
                             , IsAntiSpam=0
                             , object_url=self.physical_path()
                             , raise_exc=raise_exc
                             )
        else:
            count = 0
            check_list_to = []
            brains_type = self.BrainsType()

            for member_id in members:
                if member_id in check_list_to:
                    continue

                if antispam and antispam.has_key( member_id ):
                    IsAntiSpam = antispam[member_id]
                else:
                    CheckAntiSpam( self, member_id, brains_type )

                mail_text = template( self
                             , task_id=self.id
                             , task_title=self.Title()
                             , lang=lang
                             , IsAntiSpam=IsAntiSpam
                             , **kw 
                             )

                if host.send( msg=host.createMessage( source=mail_text ), mto=( member_id, ), from_member=1
                             , IsAntiSpam=IsAntiSpam, object_url=self.physical_path()
                             , raise_exc=raise_exc \
                             ):
                    check_list_to.append( member_id )
                    count += 1

        del host

        if kw and kw.has_key('notify_after_commit') and getattr(self, '_notify_schedule_id', None) and count > 0:
            self.delScheduleIds( [ self._notify_schedule_id ] )
            setattr(self, '_notify_schedule_id', None)

            #return { 'auto_remove':1 }

        return count

    security.declarePublic( 'AutoFinalize')
    def AutoFinalize( self ):
        """
            Finalizes task by scheduler event. See alarm settings.
            The method is called automatically by the portal scheduling service.
        """
        if not self.canBePublished():
            return
        if not self.hasAutoFinalized():
            return

        self.get_brains().onFinalize( result_code=TaskResultCodes.TASK_RESULT_SUCCESS )
        portal_log( self, 'TaskItem', 'AutoFinalize', 'task_id, finalized', ( self.getId(), self.finalized ) )
        self.auto_finalized = self.finalized

    security.declarePublic( 'isAutoFinalized' )
    def isAutoFinalized( self ):
        """
            Returns 1 if task was finalized by scheduler
        """
        return self.auto_finalized

    security.declarePublic( 'hasAutoFinalized' )
    def hasAutoFinalized( self, check=None ):
        """
            Returns 1 if task will be finalized by scheduler
        """
        finalize_settings = self.FinalizeSettings()
        if finalize_settings and finalize_settings.has_key('auto') and finalize_settings['auto']:
            if not check:
                return 1
            scheduler = getToolByName( self, 'portal_scheduler', None )
            if scheduler is None:
                return 0
            if self._finalize_schedule_id and scheduler.hasScheduleElement( self._finalize_schedule_id ):
                return 1
        return 0

    security.declarePublic( 'hasDelegationOfAuthority' )
    def hasDelegationOfAuthority( self ):
        """
            Returns 1 if the task has delegation of members authority permission
        """
        finalize_settings = self.FinalizeSettings()
        if finalize_settings and finalize_settings.has_key('delegate') and finalize_settings['delegate'] == 1:
            return 1
        return 0

    def isFinalizedByDAGroup( self, member=None, **kw ):
        """
            Checks either the task has been or should be finalized by DA group
        """
        if not self.hasDelegationOfAuthority():
            return 0
        if kw.has_key('queue'):
            queue = kw['queue']
        else: 
            queue = self.FinalizeSettings().get('queue', None)
        if kw.has_key('finalized_users'):
            finalized_users = kw['finalized_users']
        else:
            finalized_users = self.listUsersWithClosedReports()
        if not queue:
            if member and member in finalized_users:
                return 1
            return 0

        IsFinalize = 1

        for x in queue:
            any = 0
            for user in x['members']:
                if x['type'] == 'all':
                    if user not in finalized_users:
                        IsFinalize = 0
                        break
                elif x['type'] == 'any':
                    if user in finalized_users:
                        any = 1
                        break
            if x['type'] == 'any' and not any:
                IsFinalize = 0
                break

        return IsFinalize

    security.declarePublic( 'hasResponses' )
    def hasResponses( self, recursive=None ):
        """
            Returns 1 if the task has responses
        """
        x = self.get_responses().hasResponses()
        if not recursive or x:
            return x
        for task in self.followup.getBoundTasks( recursive=1 ):
            if task.hasResponses():
                return 1
        return None

    security.declarePublic( 'getTaskResolution' )
    def getTaskResolution( self ):
        """
            Returns resolution attributes dictionary
        """
        if not hasattr(self, 'resolution'):
            return None
        if self.resolution is None or type(self.resolution) is not DictType:
            return None
        if self.finalized and self.ResultCode() in ['cancelled']:
            return None

        resolution = self.resolution
        if len(resolution.keys()) == 0:
            return None

        return resolution

    security.declarePublic( 'getTaskResolutionInvolvedUsers' )
    def getTaskResolutionInvolvedUsers( self, with_groups=None ):
        """
            Returns resolution invoved users ids
        """
        resolution = self.getTaskResolution()
        if not resolution:
            return []
        if not resolution.has_key('involved_users'):
            return []
        membership = getToolByName( self, 'portal_membership', None )
        if membership is None:
            return []

        # Implement it if groups should be presents inside involved users/groups list
        users = []

        for x in resolution['involved_users']:
            if x.startswith('group') and not with_groups:
                group_id = x[6:]
                group_users = membership.getGroup(group_id).getUsers()
                users += list(group_users)
            else:
                users.append( x )

        return uniqueValues( users )

    security.declarePrivate( 'setAlarm' )
    def setAlarm( self, settings=None, force=None ):
        """
            Alarm and auto finalize settings.

            Arguments:

                'settings' -- alarm setting dictionary.

                'force' -- used if it's called by objectManager, for instance when associated
                        document will be routed by workflow.
        """
        if self.TaskTemplateId() in ( 'SelfSignature', ) or not self.InvolvedUsers( no_recursive=1 ):
            self.alarm_settings = {}
            return

        scheduler = getToolByName( self, 'portal_scheduler', None )
        if scheduler is None:
            return

        if force:
            settings = self.AlarmSettings()
            if not settings or not self.canBePublished():
                return
            elif self.expiration_date is None or self.effective_date is None:
                return
            #we want to finalize expired task that was not finalized intime
            #it's running in progress of archiving process
            #so don't implement the next lines
            #elif self.expiration_date.isPast():
            #    return
        elif not settings:
            settings = {}
            settings['type'] = 'disable'
            settings['value'] = 0
            settings['note'] = None
            settings['include_descr'] = 0

        self.alarm_settings = settings

        element_ids = [ self._alarm_schedule_id, self._finalize_schedule_id ]
        if self._expiration_schedule_id and settings['type'] in ['disable']:
            element_ids.append( self._expiration_schedule_id )
        self.delScheduleIds( element_ids )

        task_url = self.getTaskPortalLink( uid=self.getUid(), check_catalog=0 ) or ''

        # build TE from alarm settings
        type, value = settings['type'], settings['value']

        if type == 'percents':
            value = ( not value or value < 0 )  and 10 or value
            date = self.expiration_date - (self.expiration_date - self.effective_date) * float(value) / 100
            temporal_expr = DateTimeTE( date )

            self._alarm_schedule_id = scheduler.addScheduleElement( self.Alarm
                        , title="[Percents Alarm] %s $ %s" % ( self.Title(), task_url )
                        , temporal_expr=temporal_expr
                        , prefix='A'
                        )

        elif type == 'periodical':
            period_type = settings['period_type']
            if period_type == 'minutes':
                frequency = value * 60
            elif period_type == 'hours':
                frequency = value * 3600
            elif period_type == 'days':
                frequency = value * 3600 * 24
            elif period_type == 'months':
                frequency = value * 3600 * 24 * 31
            date = DateTime() + float(frequency) / 86400
            temporal_expr = UniformIntervalTE( frequency, start_date=date, end_date = self.expires() )

            self._alarm_schedule_id = scheduler.addScheduleElement( self.Alarm
                        , title="[Periodical Alarm] %s $ %s" % ( self.Title(), task_url )
                        , temporal_expr=temporal_expr 
                        , prefix='A'
                        )

        elif type == 'custom':
            for date in value:
                temporal_expr = DateTimeTE( date )

                self._alarm_schedule_id = scheduler.addScheduleElement( self.Alarm
                        , title="[Custom Alarm] %s $ %s" % ( self.Title(), task_url )
                        , temporal_expr=temporal_expr
                        , prefix='A'
                        )

        if self.hasAutoFinalized():
            date = self.expiration_date + (self.expiration_date - self.effective_date) / float(10)
            temporal_expr = DateTimeTE( date )

            self._finalize_schedule_id = scheduler.addScheduleElement( self.AutoFinalize
                        , title="[Auto finalize] %s $ %s" % ( self.Title(), task_url )
                        , temporal_expr=temporal_expr
                        , prefix='F'
                        )

            #portal_log( self, 'TaskItem', 'setAlarm', 'finalize_settings at date, id', ( \
            #    date, self._finalize_schedule_id ) )

    security.declarePublic( 'Alarm' )
    def Alarm( self ):
        """
            Reminders users about task.
            The method is called automatically by the portal scheduling service.
        """
        if self.TaskTemplateId() in ( 'SelfSignature', ):
            return

        if not self.canBePublished():
            return

        SendToCreator = 0
        status = ('commit', 'satisfy', 'sign', 'task_register', 'informed', 'failure', 'reject')
        exclude_list = [ r['member'] for r in self.searchResponses() if r['status'] in status ]
        exclude_list += self.listUsersWithClosedReports()
        notify_list = [ user for user in self.InvolvedUsers( no_recursive=1 ) if user not in exclude_list ]

        if SendToCreator:
            notify_list.append( self.Creator() )

        supervisors = self.Supervisors()
        if supervisors and not self.searchResponses( status='review' ):
            notify_list.extend( supervisors )

        self.send_mail( uniqueValues( notify_list ), 'mail_alarm' )

    security.declarePrivate( 'checkInvolvedUsersThreshold' )
    def checkInvolvedUsersThreshold( self, involved=None, suspended_timeout=None ):
        """
            Check if we should run suspended mail when involved users is too much
        """
        if not involved:
            involved = []
        elif type(involved) is not ListType:
            involved = [ involved ]

        properties = getToolByName( self, 'portal_properties', None )
        if properties is None:
            return ( [], involved )

        suspended_mail = properties.getProperty('suspended_mail', 1)
        max_involved_users = properties.getProperty('max_involved_users', 10)
        mail_threshold = properties.getProperty('mail_threshold', 50)

        suspended_users = []

        if not involved:
            involved = self.InvolvedUsers( no_recursive=1 )
            len_current_involved_users = len(involved)
            len_involved = 0
            if len_current_involved_users > max_involved_users:
                n = len_current_involved_users - max_involved_users
            else:
                n = -1
        else:
            len_current_involved_users = len(self.InvolvedUsers( no_recursive=1 ))
            len_involved = len(involved)
            if len_current_involved_users + len_involved > max_involved_users:
                if len_current_involved_users <= max_involved_users:
                    n = max_involved_users - len_current_involved_users
                else:
                    n = 0
            else:
                n = -1

        if not suspended_mail:
            return ( [], n > 0 and len_involved > n and involved[:n] or involved )
        elif n > -1 and involved:
            included_users = involved[:-n]
            suspended_users = involved[-n:]
            portal_info( 'TaskItem.checkInvolvedUsersThreshold', 'init suspended mail, URL: %s\n>suspended: %s\n>involved: %s' % ( \
                self.absolute_url(), suspended_users, included_users ) \
                )
            self.setSuspendedMail( suspended_users, suspended_timeout )
        else:
            included_users = involved

        return ( suspended_users, included_users )

    security.declarePrivate( 'setSuspendedMail' )
    def setSuspendedMail( self, suspended_users=None, suspended_timeout=None, force=None ):
        """
            Sets task's suspended distribution mode
        """
        if not suspended_users and not force:
            return 0

        scheduler = getToolByName( self, 'portal_scheduler', None )
        properties = getToolByName( self, 'portal_properties', None )
        if scheduler is None or properties is None:
            return 0

        old_suspended_users = getattr( self, 'suspended_users', suspended_users )
        if old_suspended_users:
            if not suspended_users:
                suspended_users = []
            if type(old_suspended_users) is not ListType or old_suspended_users == suspended_users:
                old_suspended_users = []
            suspended_users = old_suspended_users + suspended_users

        setattr( self, 'suspended_users', suspended_users )
        if not suspended_users:
            return 0

        task_url = self.getTaskPortalLink( uid=self.getUid(), check_catalog=0 ) or ''

        element_ids = [ getattr( self, '_suspended_mail_id', None ) ]
        self.delScheduleIds( element_ids )

        try:
            frequency = int(properties.getProperty('mail_frequency', '1')) * 60
        except:
            frequency = 5 * 60

        start_date = DateTime() + float(frequency) / 86400
        if suspended_timeout:
            start_date += float(int(suspended_timeout) * 60) / 86400
        if force and self.isExpired():
            end_date = self.expiration_date
            while end_date < DateTime():
                end_date += float(int(force) * 3600 * 24) / 86400
            setattr( self, 'expiration_date', end_date )
        temporal_expr = UniformIntervalTE( frequency, start_date=start_date, end_date=self.expires() )

        self._suspended_mail_id = scheduler.addScheduleElement( self.SuspendedMail
                    , title="[Suspended Mail] %s $ %s" % ( self.Title(), task_url )
                    , temporal_expr=temporal_expr
                    , prefix='S'
                    )

        portal_log( self, 'TaskItem', 'setSuspendedMail', 'suspended queue', ( len(self.suspended_users), self._suspended_mail_id ) )
        return 1

    security.declarePublic( 'SuspendedMail' )
    def SuspendedMail( self ):
        """
            Suspended task mail distribution to involved users.
            The method is called automatically by the portal scheduler service.
        """
        if not self.canBePublished():
            return

        template_name = 'mail_notify_users'

        element_ids = [ getattr( self, '_suspended_mail_id', None ) ]
        su = getattr( self, 'suspended_users', None )

        if su and type(su) is ListType:
            included_users = [ su.pop(0) ]
            if included_users[0] not in self.listRespondedUsers():
                self.send_notifications( included_users, [], no_supervisor=1 )
            self.suspended_users = su
            portal_info( 'TaskItem.SuspendedMail', 'sent to users: %s, suspended queue: %s' % ( \
                included_users, len(self.suspended_users) ) \
                )

        if not su and element_ids:
            self.delScheduleIds( element_ids )
            self.suspended_users = 1
            self.updateIndexes( idxs=['StateKeys',] )
            portal_info( 'TaskItem.SuspendedMail', 'deleted suspended: %s' % element_ids )

        CommitThread( self, 'TaskItem.SuspendedMail', force=1, subtransaction=None, info=self.getId() )
    #
    #   Followup response functions ==============================================================================
    #
    security.declareProtected( CMFCorePermissions.View, 'listFollowupTasks' )
    def listFollowupTasks( self ):
        """
            Returns the followup tasks list.

            Result:

                List of followup tasks id strings, if it's sequential request.
        """
        return self.followup_tasks

    security.declarePrivate( 'enableFollowupTasks' )
    def enableFollowupTasks( self, task_in_turn_id=None ):
        """
            Starts followup tasks assigned to the current task.
            The list of followup tasks is defined with the 'setFollowipTasks' method.
        """
        tasks = self.listFollowupTasks()

        for task_id in tasks:
            task = self.getTask(task_id)
            if task is None:
                continue
            if not task.isEnabled():
                task.Enable()
                return task.isEnabled()
            elif task_in_turn_id and task_in_turn_id != task_id and not task.checkDemandRevisionSuccess( check_root=None ):
                return 0

        return None

    security.declarePublic( 'checkIfShouldFinalize' )
    def checkIfShouldFinalize( self ):
        """
            Checks whether followup can be finalized success
        """
        tasks = self.listFollowupTasks()
        IsSuccess = 1

        for task_id in tasks:
            task = self.getTask(task_id)
            if task is None or not task.isEnabled():
                IsSuccess = 0
                break
            if task.isFinalized():
                if task.ResultCode() == TaskResultCodes.TASK_RESULT_FAILED:
                    IsSuccess = 0
                    break
            elif not task.get_brains().check_if_shouldFinalize():
                IsSuccess = 0
                break

        return IsSuccess

    def findRootTask( self, check_root=None, parent_only=None ):
        """
            Finds the topmost task in a thread.
            Returns self if no parent tasks were found.

            Result:

                Reference to the Task item instance.
        """
        parents = self.parentsInThread()
        if len(parents) >= 2:
            if not parent_only:
                # The first parent is content object and the second
                # is a top level task item of the thread
                return parents[1]
            else:
                return parents[-1]
        elif check_root:
            return None
        return self

    security.declareProtected( CMFCorePermissions.View, 'listAllowedResponseTypes' )
    def listAllowedResponseTypes( self, uname=None, force=None, check_demand_revision=None, check_only=None ):
        """
            Returns a list of response types allowed to the user.

            Arguments:

                'uname' -- user id, String.

                'force' -- ignore response condition property, Boolean.

                'check_demand_revision' -- check demand revision code if is 'in turn', Boolean.

            Result:

                 List of task response type information mappings.
        """
        if self.isFinalized():
            return []

        if not uname:
            uname = _getAuthenticatedUser(self).getUserName()

        results = []
        if not check_only:
            if self.temporal_expr and uname != self.Creator() or not ( self.isEnabled() or self.isSuperuser( uname ) ):
                return results

        if check_demand_revision and self.isInTurn( check_root=1, parent_only=1 ):
            demand_revision_code = self.getDemandRevisionCode( uname ) or None
        else:
            demand_revision_code = None

        tti = self.get_brains().task_type_information
        responses = tti['responses']

        for rti in responses:
            available = 1
            layer = rti['layer']
            if layer != 'superusers':
                if not demand_revision_code or demand_revision_code == TaskResultCodes.TASK_RESULT_SUCCESS:
                    if self.UserSatysfiedRequest( layer=layer, member=uname, isclosed=1 ):
                        continue
            if rti.has_key('condition'):
                condition = Expression(rti['condition'])
                if not condition( getEngine().getContext( {'here': self, 'member': uname } ) ) and not force:
                    available = 0
            if available:
                results.append( rti )

        return results

    security.declareProtected( CMFCorePermissions.View, 'listNotifiedUsersInTurn' )
    def listNotifiedUsersInTurn( self ):
        """
            Returns 'in turn' followup users list which should be notified
        """
        if not self.isInTurn():
            return None

        res = []
        tasks = self.listFollowupTasks()
        for task_id in tasks:
            task = self.getTask(task_id)
            if not task is None and task.canBePublished():
                involvedUsers = task.InvolvedUsers( no_recursive=1 )
                for user_id in involvedUsers:
                    if user_id and not user_id in res:
                        res.append( user_id )
        return res

    security.declareProtected( CMFCorePermissions.View, 'parseSelectedUsers' )
    def parseSelectedUsers( self, selected_users ):
        return filter( None, uniqueValues( selected_users ) )

    security.declareProtected( CMFCorePermissions.View, 'parseSelectedResponses' )
    def parseSelectedResponses( self, selected_responses, in_turn=None, attr=None ):
        """
            Returns selected 'in turn' followup responses list.

            Arguments:

                'selected_responses' -- responses alarm list by string template: <task_id>|<response_id>.

            Result:

                List of responses dict.
        """
        if in_turn and not self.isInTurn() or not selected_responses:
            return None

        res = []
        for item in selected_responses:
            x = item.split('|')
            task_id = x[0]
            response_id = int(x[1])

            try:
                task = self.getTask( task_id )
                response = task.searchResponses()[ response_id ]
            except: continue

            x = getBTreesItem( response )
            if not x: continue

            if attr and x.has_key(attr):
                res.append( x[attr] )
            else:
                res.append( x )

        return res

    security.declarePublic( 'isInTurn' )
    def isInTurn( self, check_root=None, turn_type=None, parent_only=None ):
        """
            Checks whether this task is in turn: confirm_by_turn/cycle_by_turn.

            Arguments:

                'check_root' -- check followup root task, Boolean.

                'turn_type' -- the turn type name, such as: 'confirm_by_turn/cycle_by_turn', String.

                'parent_only' -- check parent task only.

            Result:

                Boolean.
        """
        root = check_root and self.findRootTask( check_root=1, parent_only=parent_only ) or self
        if root is None:
            return 0
        elif not turn_type:
            return root.isConfirmByTurn() or root.isCycleByTurn()
        elif turn_type == 'confirm_by_turn':
            return root.isConfirmByTurn()
        elif turn_type == 'cycle_by_turn':
            return root.isCycleByTurn()

    security.declarePublic( 'isConfirmByTurn' )
    def isConfirmByTurn( self ):
        return getattr(self, 'confirm_by_turn', None) and 1 or 0

    security.declarePublic( 'isCycleByTurn' )
    def isCycleByTurn( self ):
        return getattr(self, 'cycle_by_turn', None) and 1 or 0

    security.declareProtected( CMFCorePermissions.View, 'searchResponses' )
    def searchResponses( self, view=None, **kw):
        """
            Returns user responses list according to the given query
        """
        return self.get_responses().searchResponses( view=view, **kw )

    security.declareProtected( CMFCorePermissions.View, 'searchResponsesInTurn' )
    def searchResponsesInTurn( self, failed_only=None, current_task_only=None, member=None ):
        """
            Returns user responses list for task followup in turn.

            Arguments:

                'failed_only' -- failed response revision code only, such as 'revise/reject/failure'.

                'current_task_only' -- returns responses list for given task only.

                'member' -- show responses of given member only.
        """
        res = []
        if not current_task_only:
            tasks = self.listFollowupTasks()
        else:
            tasks = [ self.getId() ]

        for task_id in tasks:
            task = self.getTask(task_id)
            if task is None:
                continue
            brains_type = task.BrainsType()
            status_in_turn = brains_type == 'request' and ('satisfy','revise',) or \
                brains_type == 'signature_request' and ('sign','reject',) or \
                brains_type == 'inspection' and ('inspected','reject','review',) or \
                brains_type in ('directive','information',) and ('commit','failure','reject','review',) or \
                []
            if failed_only:
                involved_users = task.InvolvedUsers( no_recursive=1 )
                for user_id in involved_users:
                    if member and user_id != member:
                        continue
                    responses = [ x for x in task.searchResponses( view=1, member=user_id ) ]
                    responses.sort( lambda x, y: cmp(x['date'], y['date']) )
                    responses.reverse()
                    for response in responses:
                        if response['status'] == status_in_turn[0]:
                            break
                        response['task_id'] = task_id
                        res.append( response )
            else:
                for status in status_in_turn:
                    for response in task.searchResponses( view=1, status=status):
                        response['task_id'] = task_id
                        res.append( response )

            if res and failed_only:
                res.sort( lambda x, y: cmp(x['date'], y['date']) )
                res.reverse()

        return tuple(res)

    security.declareProtected( CMFCorePermissions.View, 'setDemandRevisionCode' )
    def setDemandRevisionCode( self, code=None, check_root=None ):
        """
            Sets 'in turn' brains demand revision code.

            Arguments:

                'code' -- current task revision code, such as 'success/failed'.

                'check_root' -- apply for root item only.
        """
        if check_root:
            root = self.findRootTask( check_root=1 )
        else:
            root = self
        if root is None or not root.isInTurn():
            return

        if code:
            user_id = _getAuthenticatedUser(self).getUserName()
            demand_revision_code = getattr(self, 'demand_revision_code', {})
            demand_revision_code[user_id] = code
            setattr(self, 'demand_revision_code', demand_revision_code)
        else:
            for task_id in root.listFollowupTasks():
                task = self.getTask(task_id)
                if not task is None and task.isEnabled():
                    setattr(task, 'demand_revision_code', {})

    security.declarePublic( 'getDemandRevisionCode' )
    def getDemandRevisionCode( self, user_id=None, code_only=None ):
        """
            Returns brains demand revision code for current task and authenticated member.

            Arguments:

                'user_id' -- return result code for user id, otherwise for current user.

                'code_only' -- return code or title of code.
        """
        if not user_id:
            if not self.isInTurn( check_root=1, parent_only=1 ):
                return None
            user_id = _getAuthenticatedUser(self).getUserName()
        if not hasattr(self, 'demand_revision_code'):
            if not code_only:
                if self.canBePublished() and self.InvolvedUsers( no_recursive=1 ):
                    return DemandRevisionCodes.DEMAND_REVISION_CURRENT
                else:
                    return None

        demand_revision_code = getattr(self, 'demand_revision_code', {})
        default = not code_only and DemandRevisionCodes.DEMAND_REVISION_DEFAULT or None

        if self.isCreator():
            if not code_only:
                if not demand_revision_code:
                    return default
                else:
                    for code in demand_revision_code.values():
                        if code == DemandRevisionCodes.DEMAND_REVISION_FAILED:
                            return code
                return None
        elif user_id not in self.InvolvedUsers( no_recursive=1 ):
            return None

        return demand_revision_code.get(user_id, default)

    security.declarePublic( 'checkDemandRevisionSuccess' )
    def checkDemandRevisionSuccess( self, check_root=1 ):
        """
            Checks followup 'in turn' success revision result.

            Arguments:

                'check_root' -- apply for all task collection (than self is root), or for current item only.
        """
        if check_root:
            if not self.isInTurn():
                return None
            tasks = check_root and self.listFollowupTasks()
        else:
            tasks = [ self.getId() ]

        IsSuccess = 1

        for task_id in tasks:
            task = self.getTask(task_id)
            if task is None or not task.isEnabled():
                IsSuccess = 0
                break
            if not check_root and not getattr(task, 'demand_revision_code', {}):
                IsSuccess = 0
                break
            involvedUsers = task.InvolvedUsers( no_recursive=1 )
            for user_id in involvedUsers:
                if task.getDemandRevisionCode( user_id, code_only=1 ) == DemandRevisionCodes.DEMAND_REVISION_FAILED:
                    IsSuccess = 0
                    break
            if not task.get_brains().check_if_shouldFinalize():
                IsSuccess = 0
                break

        return IsSuccess

    security.declareProtected( CMFCorePermissions.View, 'getHistory' )
    def getHistoryInTurn( self ):
        """
            Returns not reviewed notifications history 'in turn' for current user
        """
        root = self.findRootTask( check_root=1 )
        if root is None or not root.isInTurn() or self.isCreator():
            return None

        uname = _getAuthenticatedUser(self).getUserName()
        if uname not in self.InvolvedUsers( no_recursive=1 ):
            return None

        notification_history = [ x for x in getattr( root, 'notification_history' ) ]
        if not notification_history:
            return None

        notification_history.sort( lambda x, y: cmp(x['date'], y['date']) )
        notification_history.reverse()
        responses = self.searchResponses( member=uname )
        last_response_date = responses and max([ x['date'] for x in responses ]) or self.getEnableDate() or None

        objects = []
        a = objects.append

        for x in notification_history:
            if uname in x['rcpt'] and not last_response_date or x['date'] > last_response_date:
                a( x )

        return objects

InitializeClass( TaskItem )


class TaskItemContainer( InstanceBase ):
    """
        Task items container
    """
    _class_version = 1.02

    meta_type = 'Task Item Container'
    id = 'followup'

    isTaskContainer = 1

    security = ClassSecurityInfo()
    security.declareProtected( CMFCorePermissions.View, 'getId' )

    def __init__( self ):
        """
            Construct instance
        """
        InstanceBase.__init__( self )
        self._container = {}

    def _p_resolveConflict( self, oldState, savedState, newState ):
        """
            Try to resolve conflict between container's objects
        """
        oldState = ResolveConflict('TaskItemContainer', oldState, savedState, newState, '_container', \
                                    mode=2 \
                                    )
        return oldState

    def _initstate( self, mode ):
        """
            Initialize attributes
        """
        if not Persistent._initstate( self, mode ):
            return 0

        if getattr( self, '_container', None ) is None:
            self._container = {}
        elif type(self._container) != type({}):
            container = {}
            for key, value in self._container.items():
                container[key] = value
            self._container = container
            self._p_changed = 1

            portal_info( 'TaskItemContainer initstate', 'keys: %s' % len(self._container.keys()) )
        return 1

    security.declareProtected( CMFCorePermissions.View, '__bobo_traverse__' )
    def __bobo_traverse__( self, REQUEST, name ):
        """
            This will make this container traversable
        """
        target = getattr(self, name, None)
        if target is not None:
            return target
        else:
            try:
                return self.getTask( name )
            except KeyError:
                portal_error( 'TaskItemContainer.__bobo_traverse__', "KeyError [name: %s. self: %s]" % ( name, `self`) )
                parent = aq_parent( aq_inner( self ) )
                if parent.getId() == name:
                    return parent
                try: REQUEST.RESPONSE.notFoundError("%s\n%s" % (name, ''))
                except: return None

    def changeOwnership( self, user, recursive=0, aq_get=None ): #, None=None,
        pass

    security.declareProtected( CMFCorePermissions.View, 'getBase' )
    def getBase( self ):
        """
            Returns the contaner object
        """
        return self.parent()

    security.declareProtected( CMFCorePermissions.View, 'getTask' )
    def getTask( self, task_id ):
        """
            Returns a task item, given its ID;  raise KeyError if not found.
        """
        task = self._container.get( task_id )
        if task is not None:
            return task.__of__(self)
        raise KeyError, task_id

    security.declarePrivate( 'manage_afterAdd' )
    def manage_afterAdd( self, item, container ):
        """
            Add event handler
        """
        if aq_base(container) is not aq_base(self):
            for obj in self.objectValues():
                obj.__of__( self ).manage_afterAdd( item, container )
        return

    security.declarePrivate( 'manage_afterClone' )
    def manage_afterClone( self, item ):
        """
            Copy/paste event handler
        """
        # Remove tasks from the document copy
        for task_id in self.objectIds():
            self.deleteTask( task_id )
        return

    security.declarePrivate( 'manage_beforeDelete' )
    def manage_beforeDelete( self, item, container ):
        """
            Delete event handler
        """
        if hasattr(container, 'followup_tasks'):
            id = self.getId()
            if id in container.followup_tasks:
                container.followup_tasks.remove(id)

        if aq_base(container) is not aq_base(self):
            for obj in self.objectValues():
                obj.__of__(self).manage_beforeDelete( item, container )
    #
    #   OFS.ObjectManager query interface ========================================================================
    #
    security.declareProtected( CMFCorePermissions.AccessContentsInformation, 'objectIds' )
    def objectIds( self, spec=None ):
        """
            Returns a list of the Task Items ids.
        """
        # It's allowed to pass sequence type 'spec' list, such as: ( 'Image Attachment', 'File Attachment', )
        if not spec:
            ids = self._container.keys() #ObjectManager.objectIds(self)
        else:
            if type(spec) == type(''):
                spec = [spec]
            ids = []
            for x in spec:
                ids.extend( ObjectManager.objectIds(self, x) )
        #if spec and spec is not TaskItem.meta_type:
        #    return []
        return ids

    security.declareProtected( CMFCorePermissions.AccessContentsInformation, 'objectItems' )
    def objectItems( self, spec=None ):
        """
            Return a list of (id, subobject) tuples for our TaskItems.
        """
        r = []
        a = r.append
        g = self._container.get
        for id in self.objectIds(spec):
            a(( id, g(id) ))
        return r

    security.declareProtected( CMFCorePermissions.AccessContentsInformation, 'objectValues' )
    def objectValues( self ):
        """
            Returns the tasks list stored within the current container
        """
        return [ x.__of__(self) for x in self._container.values() ]

    def cookId( self ):
        t_id = int(DateTime().timeTime())
        id = "task_%s" % str( t_id )
        while self._container.get( id, None ) is not None:
            t_id = t_id + 1
            id = "task_%s" % str( t_id )
        return id

    security.declareProtected( CMFCorePermissions.View, 'createTask' )
    def createTask( self
                , title
                , involved_users
                , description=''
                , creator=None
                , supervisors=None
                , effective_date=None
                , expiration_date=None
                , plan_time=None
                , alarm_settings=None
                , finalize_settings=None
                , enabled=1
                , temporal_expr=None
                , duration=0
                , frequency=None
                , brains_type='directive'
                , resolution=None
                , bind_to=None
                , REQUEST=None
                , task_template_id=None
                , hand_roles=None
                , no_mail=None
                , notify_mode=None
                , confirm_by_turn=None
                , cycle_by_turn=None
                , suspended_timeout=None
                , no_commit=None
                , redirect=1
                , **kw
                ):
        if temporal_expr and not duration:
            raise ValueError, 'Duration time is required for reccurent tasks.'

        if temporal_expr is None and frequency:
            temporal_expr = UniformIntervalTE( seconds=frequency )

        if not creator:
            creator = _getAuthenticatedUser(self).getUserName()

        id = self.cookId()
        brains = getTaskBrains( brains_type )
        involved = []
        membership = getToolByName( self, 'portal_membership', None )

        if involved_users is not None:
            # verify involved list to valid portal members
            for user in involved_users:
                if type(user) is StringType:
                    x = user
                elif isinstance( user, MemberData ):
                    x = user.getMemberName()
                else:
                    continue
                if not x in involved and membership.getMemberById( x, check_only=1 ):
                    involved.append( x )

            # check so that creator must not add itself into involved list, except self signature request
            if len(involved) > 1:
                involved = [ x for x in involved if x != creator or brains_type in ['signature_request'] ]
            if not involved and not ( confirm_by_turn or cycle_by_turn ):
                raise SimpleError, 'Involved users are not defined.'

        base = self.getBase()
        hand_roles = IsPrivateObject( base ) and [ OwnerRole ] or hand_roles or [ ReaderRole ]

        task = TaskItem( id=id
                    , title=title
                    , description=description
                    , creator=creator
                    , involved_users=involved
                    , finalize_settings=finalize_settings
                    , brains=brains
                    , resolution=resolution
                    , enabled=0
                    , notify_mode=notify_mode
                    , task_template_id=task_template_id
                    , version_id=base.implements('isVersionable') and base.getVersion().id or None
                    , hand_roles=hand_roles
                    )

        message = ''
        creator = creator or _getAuthenticatedUser(self).getUserName()

        self._container[ id ] = task
        self._p_changed = 1

        try:
            task = self._container[ id ].__of__(self)
            task.manage_afterAdd( task, self )

            task.setSupervisors( supervisors )
            task.setWorkflowState( base )

            if plan_time is not None: task.setPlanTime( plan_time )
            if effective_date is None: effective_date = DateTime()

            task.setEffectiveDate( effective_date )

            if bind_to and self.getTask(bind_to):
                parent = self.getTask(bind_to)
            else:
                parent = self._getTask()

            task.BindTo( parent )
            task.setPeriodicalScheduleEvents( temporal_expr, duration )

            if not expiration_date and duration and effective_date:
                expiration_date = DateTime(float(task.effective().timeTime() + duration))

            if not expiration_date:
                raise ValueError, 'Expiration date required. Infinite tasks are not allowed.'

            if confirm_by_turn:
                setattr( task, 'confirm_by_turn', 1 )
            if cycle_by_turn:
                setattr( task, 'cycle_by_turn', 1 )

            task.setExpirationDate( expiration_date )
            task.setAlarm( alarm_settings )

            if involved:
                suspended_users, involved = task.checkInvolvedUsersThreshold( suspended_timeout=suspended_timeout )

            task.manage_setLocalRoles( creator, ['Owner'] )

            if enabled:
                if not task.effective().isFuture():
                    task.Enable( no_mail=1 )
            else:
                task.Disable()
                task.stopSchedule()

            task.updateIndexes()

            if not no_commit:
                CommitThread( self, 'TaskItemContainer.createTask', force=1, subtransaction=None )

            IsError = 0

        except ( ConflictError, ReadConflictError ):
            raise

        except Exception, msg_error:
            message = str(msg_error)
            portal_error( 'TaskItemContainer.createTask: %s' % message, ( \
                creator, id, task.getUid(), task.physical_path(), no_commit ), \
                exc_info=True )
            IsError = 1

        if not IsError:
            portal_info( 'TaskItemContainer.createTask: new object created by %s' % creator, ( \
                task.getUid(), task.physical_path(), involved, no_commit ) )
            if not no_mail and task.isEnabled():
                task.send_notifications( involved, [] )

        if IsError:
            raise SimpleError, message
        elif REQUEST is not None:
            if redirect:
                try:
                    REQUEST['RESPONSE'].redirect( task.__of__(self).absolute_url() )
                except:
                    raise SimpleError, 'Bad absolute url!'
            else:
                return task
        else:
            return ( id, '', )

    security.declareProtected( CMFCorePermissions.ManagePortal, 'deleteTask' )
    def deleteTask( self, task_id ):
        """
            Remove a task item from this container
        """
        if self._container.has_key( task_id ):
            uname = _getAuthenticatedUser(self).getUserName()
            container = self._container
            task = container.get( task_id ).__of__( self )
            task.manage_beforeDelete( task, self )

            task.ShouldBeSeenByFor()

            followup = getToolByName( self, 'portal_followup', None )
            followup.uncatalog_object( task.physical_path() )

            sub_tasks = task.followup.getBoundTasks()
            for x in sub_tasks:
                x.deleteTask( x.getId() )

            portal_info( 'TaskItemContainer.deleteTask: object was deleted by %s' % uname, ( \
                task.getUid(), task.physical_path() ) )

            del container[task_id]

            self._container = container
            self._p_changed = 1

    security.declareProtected( CMFCorePermissions.View, 'getBoundTasks' )
    def getBoundTasks( self, version_id=None, recursive=None, sort=None, REQUEST=None, **kw ):
        """
            Returns the list of the bound tasks and filters out tasks from another document versions.
            Adds acquisition wrapper to the task items.
        """
        objects = []
        a = objects.append

        if REQUEST is not None:
            batch_start = int(REQUEST.get('batch_start', 1))
            batch_size = int(REQUEST.get('batch_size', 10))
            batch_length = int(REQUEST.get('batch_length', 0)) or batch_size
            sort_on = REQUEST.get('sort_on')
            sort_order = REQUEST.get('sort_order')
        else:
            batch_length = 0
            sort_on = sort_order = None

        n = 0
        tasks = self._getBoundTasks( recursive )
        total_objects = 0
        added = 0

        if kw and kw.get('count_only'):
            objects = [ task.getId() for task in tasks if task.__of__( self ).validate() ]
            return ( len(objects), None, )

        if sort_on:
            tasks.sort( lambda x, y, sort_on=sort_on: cmp(x[sort_on], y[sort_on]) )
            if sort_order == 'reverse':
                tasks.reverse()

        for task in tasks:
            n += 1
            if version_id:
                # if document's version dosnt match task's version,
                # dont append task to bound list
                if task.version_id != version_id:
                    continue
            if kw and kw.has_key('brains_type'):
                if task.BrainsType() != kw['brains_type']:
                    continue
            total_objects += 1
            if batch_length and ( n < batch_start or added == batch_length ):
                continue
            a( task.__of__( self ) )
            added += 1

        if sort and not sort_on:
            objects.sort( lambda x, y: cmp(x['id'], y['id']) )
            objects.reverse()

        if kw and kw.has_key('with_limit'):
            return ( total_objects, objects, )

        return objects

    security.declareProtected(CMFCorePermissions.View, 'getBoundTaskIds')
    def getBoundTaskIds( self, version_id=None, recursive=None ):
        """
            Returns the list of the bound tasks ids
        """
        return [ task.getId() for task in self.getBoundTasks( version_id, recursive ) ]

    security.declareProtected(CMFCorePermissions.View, 'activateDisabledTasks')
    def activateDisabledTasks( self, recursive=None, state=None, version_id=None, **kw ):
        """
            Activate disabled tasks which were created on given state
        """
        if kw and kw.has_key('brains_type') and not kw['brains_type']:
            del kw['brains_type']

        tasks = self.getBoundTasks( version_id=version_id, recursive=recursive, **kw )
        if not tasks:
            return

        for task in tasks:
            if not state or task is None or task.isFinalized():
                continue
            if task.CreatedOnWorkflowState() != state:
                continue
            if not task.isEnabled():
                task.Enable()

    security.declareProtected(CMFCorePermissions.View, 'getFollowupDescriptions')
    def getFollowupDescriptions( self, recursive=None, check_delegation=None, version_id=None, state=None, **kw ):
        """
            Returns followup descriptions list
        """
        if kw and kw.has_key('brains_type') and not kw['brains_type']:
            del kw['brains_type']

        tasks = self.getBoundTasks( version_id=version_id, recursive=recursive, **kw )
        if not tasks:
            return None

        membership = getToolByName( self, 'portal_membership', None )
        if membership is None:
            return None

        res = []
        a = res.append
        #tasks.sort( lambda x, y: cmp(x['id'], y['id']) )

        for task in tasks:
            if task is None or not task.validate():
                continue
            if state and task.CreatedOnWorkflowState() != state:
                continue
            task_description = task.Description( clean=2 )
            a( task_description )

        return res

    security.declareProtected(CMFCorePermissions.View, 'getResponseCollection')
    def getResponseCollection( self, recursive=None, with_notifications=None, check_delegation=None, status=None,
            version_id=None, no_sort=None, **kw ):
        """
            Returns collection of followup responses for selected tasks
        """
        if kw and kw.has_key('brains_type') and not kw['brains_type']:
            del kw['brains_type']

        tasks = self.getBoundTasks( version_id=version_id, recursive=recursive, **kw )
        if not tasks:
            return None

        membership = getToolByName( self, 'portal_membership', None )
        if membership is None:
            return None

        objects = []
        a = objects.append

        for task in tasks:
            if task is None:
                continue

            task_id = task.getId()
            task_title = task.Title()
            task_has_deletation = task.hasDelegationOfAuthority()
            task_template_id = task.TaskTemplateId()

            responses = task.searchResponsesInTurn( current_task_only=1 )
            userids = task.listInvolvedUsers()

            if responses:
                for x in responses:
                    #if status and x['status'] not in status:
                    #    continue
                    if x.has_key('date'):
                        if check_delegation and task_has_deletation:
                            if task_template_id and task_title:
                                x['delegate'] = task_title
                            else:
                                member = x['member']
                                member_name = ''
                                for responded_name in userids:
                                    if responded_name == member:
                                        member_name = membership.getMemberName( responded_name )
                                        break
                                    elif responded_name.startswith('group'):
                                        group_id = responded_name[6:]
                                        if member in membership.getGroupMembers( group_id ):
                                            member_name = membership.getGroupTitle( group_id )
                                            break
                                x['delegate'] = member_name
                        a( x )

            if with_notifications:
                notification_history = [ x for x in getattr( task, 'notification_history' ) ]

                for x in notification_history:
                    if x.has_key('date'):
                        a( x )

        if objects and not no_sort:
            objects.sort( lambda x, y: cmp(x['date'], y['date']) )

        return objects

    security.declareProtected(CMFCorePermissions.View, 'quotedContents')
    def quotedContents( self ):
        """
            Returns this object's contents in a form suitable for inclusion as a quote in a response
        """
        return ""
    #
    #   Utility methods ==========================================================================================
    #
    security.declarePrivate( '_getTaskParent' )
    def _getTaskParent( self, bind_to=None ):
        """
            Returns the object indicated by the 'bind_to', where 'None' represents the "outer" content object
        """
        outer = self._getTask( outer=1 )
        if bind_to is None:
            return outer
        parent = self._container[ bind_to ].__of__( aq_inner( self ) )
        return parent.__of__( outer )

    security.declarePrivate( '_getTask' )
    def _getTask( self, outer=0 ):
        tb = outer and aq_inner( self ) or self
        parent = getattr( tb, 'aq_parent', None )
        while parent is not None and parent.implements('isVersion'):
            parent = getattr( parent, 'aq_parent', None )
        return parent

    security.declarePrivate( '_getBoundTasks' )
    def _getBoundTasks( self, recursive=None ):
        """
            Returns a list of task ids which are replies to our task.
            Does not add acquisition wrapper to the returned tasks.
        """
        task = self._getTask()
        outer = self._getTask( outer=1 )

        if task == outer:
            bind_to = None
        else:
            bind_to = task.getId()

        result = []
        a = result.append
        values = self._container.values()
        values.sort( lambda x, y: cmp(x['id'], y['id']) )

        for value in values:
            if hasattr(value, 'bind_to') and value.bind_to == bind_to:
                a( value )
                if recursive:
                    result.extend( self.__of__(value)._getBoundTasks( recursive=1 ) )

        return result

InitializeClass( TaskItemContainer )
