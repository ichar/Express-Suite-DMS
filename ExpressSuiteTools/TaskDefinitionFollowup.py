"""
TaskDefinitionFollowup class.

It consist of:
    -- model (TaskDefinitionFollowup)
    -- controller (TaskDefinitionControllerFollowup)
    -- view (TaskDefinitionFormFollowup)
    -- register (TaskDefinitionRegistryFollowup)

They are inherited from appropriated TaskDefinitionAbstract classes.
Them provide functions for create action templates for task creation.

$Id: TaskDefinitionFollowup.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 27/06/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import re
from types import StringType, ListType, TupleType, DictType
from DateTime import DateTime

from Acquisition import aq_get
from Products.CMFCore.utils import _getAuthenticatedUser, getToolByName

from Config import ReaderRole
from DFRoleManager import DFRoleManager
from Exceptions import SimpleError
from TaskBrains import getTaskBrains
from TaskDefinitionAbstract import TaskDefinition
from TaskDefinitionAbstract import TaskDefinitionForm
from TaskDefinitionAbstract import TaskDefinitionController
from TaskDefinitionAbstract import TaskDefinitionRegistry
from PortalLogger import portal_log

from Utils import InitializeClass, parseDate, parseDateTime

_comments = [ '<div class=comments>', '</div>', '<p id="(.*?)" title=comments>', '</p>' ]


class TaskDefinitionFollowup( TaskDefinition ):
    """
        Class-model.

        Store fields needed for createTask method:

        -- task_brains - id of task's brains (see TaskBrains.py)
        -- title - task's title
        -- involved_users - involved to task users
        -- supervisors - task's supervisors
        -- interval - interval for create expiration date
        -- description - task's description

        Based on this fields in 'activate' method will be maden task.
    """
    _class_version = 1.01

    def __init__( self, task_brains='' ):
        TaskDefinition.__init__( self )

        # specific fields
        self.task_brains = task_brains
        self.type = 'followup_' + self.task_brains
        self.dest_folder_uid = None
        self.title = ''
        self.involved_users = []
        self.supervisors = []
        self.interval = 0 # interval of seconds
        self.description = ''

    def _initstate( self, mode ):
        if not TaskDefinition._initstate( self, mode ):
            return 0

        if getattr( self, '_allow_edit', None ) is None:
            self._allow_edit = []
        if getattr( self, '_date_format', None ) is None:
            self._date_format = None
        if getattr( self, '_supervisor_mode', None ) is None:
            self._supervisor_mode = None
        if getattr( self, '_resolution_or_commission', None ) is None:
            self._resolution_or_commission = None
        if getattr( self, '_auto_finalize', None ) is None:
            self._auto_finalize = 0
        if getattr( self, '_expiration_alarm', None ) is None:
            self._expiration_alarm = None
        if getattr( self, '_auto_sending_by_default', None ) is None:
            self._auto_sending_by_default = 0
        if getattr( self, '_delegation_of_authority', None ) is None:
            self._delegation_of_authority = 0
        if getattr( self, '_confirmation_type', None ) is None:
            self._confirmation_type = 'any'
        if getattr( self, 'supervisors', None ) is None:
            supervisor = getattr( self, 'supervisor_user', None )
            if supervisor:
                supervisors = [ supervisor ]
                delattr( self, 'supervisor_user' )
            else:
                supervisors = []
            self.supervisors = supervisors
        if getattr( self, '_full_userlist', None ) is None:
            self._full_userlist = 0
        if getattr( self, 'to_whom', None ) is None:
            self.to_whom = None
        if getattr( self, 'hand_roles', None ) is None:
            self.hand_roles = [ ReaderRole ]
        if getattr( self, 'dest_folder_uid', None ) is None:
            self.dest_folder_uid = getattr( self, 'segment_of_company', None )
        if getattr( self, 'use_department', None ) is None:
            self.use_department = None

        return 1

    def toArray( self, arr=None ):
        """
            Converting object's fields to dictionary.

            Result:

                Dictionary as { 'field_name': 'field_value', ... }
        """
        if arr is None or type(arr) is not DictType:
            x = {}
        else:
            x = arr.copy()
        x = TaskDefinition.toArray( self, x )

        # specific fields
        x['task_brains'] = self.task_brains
        x['title'] = self.title
        x['involved_users'] = self.involved_users
        x['supervisors'] = self.supervisors
        x['interval'] = self.interval
        x['description'] = self.description

        if getattr( self, '_allow_edit', None ) is None:
            self._allow_edit = []
        if getattr( self, '_date_format', None ) is None:
            self._date_format = None
        if getattr( self, '_supervisor_mode', None ) is None:
            self._supervisor_mode = None
        if getattr( self, '_resolution_or_commission', None ) is None:
            self._resolution_or_commission = None
        if getattr( self, '_auto_finalize', None ) is None:
            self._auto_finalize = 0
        if getattr( self, '_expiration_alarm', None ) is None:
            self._expiration_alarm = None
        if getattr( self, '_auto_sending_by_default', None ) is None:
            self._auto_sending_by_default = 0
        if getattr( self, '_delegation_of_authority', None ) is None:
            self._delegation_of_authority = 0
        if getattr( self, '_confirmation_type', None ) is None:
            self._confirmation_type = 'any'
        #if getattr( self, 'supervisors', None ) is None:
        #    self.supervisors = []

        x['_allow_edit'] = self._allow_edit
        x['_date_format'] = self._date_format
        x['_supervisor_mode'] = self._supervisor_mode
        x['_resolution_or_commission'] = self._resolution_or_commission
        x['_auto_finalize'] = self._auto_finalize
        x['_expiration_alarm'] = self._expiration_alarm
        x['_auto_sending_by_default'] = self._auto_sending_by_default
        x['_delegation_of_authority'] = self._delegation_of_authority
        x['_confirmation_type'] = self._confirmation_type
        x['_full_userlist'] = self._full_userlist
        x['to_whom'] = self.to_whom
        x['hand_roles'] = self.hand_roles
        x['dest_folder_uid'] = self.dest_folder_uid
        x['use_department'] = self.use_department

        return x

    def changeTo( self, taskDefinition ):
        """
            Changes object's values to news.

            Arguments:

                'taskDefinition' -- object to values of which need to change self
        """
        TaskDefinition.changeTo( self, taskDefinition )
        # specific fields
        self.title = taskDefinition.title
        self.involved_users = taskDefinition.involved_users
        self.supervisors = taskDefinition.supervisors
        self.interval = taskDefinition.interval
        self.description = taskDefinition.description
        self._allow_edit = taskDefinition._allow_edit
        self._date_format = taskDefinition._date_format
        self._supervisor_mode = taskDefinition._supervisor_mode
        self._resolution_or_commission = taskDefinition._resolution_or_commission
        self._auto_finalize = taskDefinition._auto_finalize
        self._expiration_alarm = taskDefinition._expiration_alarm
        self._auto_sending_by_default = taskDefinition._auto_sending_by_default
        self._delegation_of_authority = taskDefinition._delegation_of_authority
        self._confirmation_type = taskDefinition._confirmation_type
        self._full_userlist = taskDefinition._full_userlist
        self.to_whom = taskDefinition.to_whom
        self.hand_roles = taskDefinition.hand_roles
        uid = taskDefinition.dest_folder_uid
        self.dest_folder_uid = uid and len(uid) > 10 and uid or None
        self.use_department = taskDefinition.use_department

    def getResultCodes( self ):
        """
            Returns result codes of task which will be maden based on
            this template.

            Asked information from task's brains

            Result:

            >>>return = (
            >>>    { 'id': 'result_code1', 'title': 'title_result_code1' },
            >>>     ...
            >>> )
        """
        task_type_information = getTaskBrains( self.task_brains ).task_type_information
        return task_type_information.get('results', {})

    def activate( self, object, ret_from_up, transition ):
        """
            Create task to specific object, with fields from template's values.

            Arguments:

                'object' -- object for which task will be maden (generally HTMLDocument)

                'ret_from_up' -- dictionary from previous 'action', if this action template
                             are included, otherwise dictionary have key 'task_template_id'
                             which have id of task_template, this attribut are stored to task

            Result:

                Dictionary, have key 'task_id' - result of execution method
                TaskItemcontainer.createTask(), this needed to included action templates
                (if exists), to 'bind' task to this task.
        """
        self.ret_from_up = ret_from_up    # for access from methods

        # we mark 'automatedTask' only task definition on top of tree
        if self.amIonTop():
            # root element
            task_template_id = ret_from_up['task_template_id']
            bind_to = None
        else:
            # childs
            task_template_id = None
            bind_to = ret_from_up['task_id']

        task_id = None
        involved_users = []
        title = self._getField('title')
        confirmation_type = int(self.REQUEST.get(self._getFormNameByName( 'confirmation_type' )) or '0')
        confirm_by_turn = cycle_by_turn =  0
        if confirmation_type == 1:
            confirm_by_turn = 1
        elif confirmation_type == 2:
            cycle_by_turn = 1

        portal_log( self, 'TaskDefinitionFollowup', 'activate', 'confirmation_type', ( \
            confirmation_type, confirm_by_turn, cycle_by_turn ) )
        users = self._getInvolvedUsers( object, distinct=1 )
        supervisors = self._getSupervisors( object )
        portal_log( self, 'TaskDefinitionFollowup', 'activate', 'users, supervisors', ( \
            users, supervisors ) )
        membership = getToolByName( self, 'portal_membership' )
        msg = getToolByName( self, 'msg' )

        if users:
            if confirm_by_turn or cycle_by_turn:
                task_id = self.CreateTaskInTransition( object, title, [], task_template_id, description='...', \
                        confirm_by_turn=confirm_by_turn, cycle_by_turn=cycle_by_turn, \
                        supervisors=supervisors )
                if task_id:
                    task = object.followup.getTask( task_id )
                    # The child's task desription is root title only
                    task_description = self._getField('description').strip() or task is not None and task.Title() or ''
                    # Use it as a child's task title if needed
                    task_title = '%s' % msg(self.task_brains)

                task = None
                for user in users:
                    if not task_id:
                        break
                    # Enable the first task in the chain
                    enabled = task is None and 1 or 0
                    if task is None or confirm_by_turn:
                        task = object.followup.getTask( task_id )
                        followup_tasks = []
                    bind_to = task.getId()
                    if type(user) is TupleType:
                        group, IsDAGroup, involved_users = user
                        if involved_users:
                            group_id = group[6:]
                            user_name = membership.getGroupTitle( group_id )
                        else:
                            continue
                    else:
                        involved_users = [ user ]
                        user_name = membership.getMemberById( user ).getMemberBriefName()
                        IsDAGroup = 0

                    task_id = self.CreateTaskInTransition( object
                                        , title="%s" % user_name
                                        , involved_users=involved_users
                                        , task_template_id=task_template_id
                                        , bind_to=bind_to
                                        , enabled=enabled
                                        , no_mail=not enabled and 1 or 0
                                        , description=task_description
                                        , IsDAGroup=IsDAGroup
                                        , supervisors=supervisors
                                        )

                    followup_tasks.append( task_id )
                    task.setFollowupTasks( followup_tasks )
            else:
                suspended_timeout = 10
                followup_tasks = []
                task = None
                n = 0

                task_description = self._getField('description')
                resolution = self._getResolution( task_template_id, self.REQUEST )
                matched = None

                if len(users) > 1:
                    description = '...'
                    if task_description and self.task_brains == 'directive':
                        # check and force commission for root item
                        rfrom = re.compile( r'%s(.*)%s' % (_comments[2], _comments[3]), re.I+re.DOTALL )
                        matched = rfrom.search( task_description )
                        if matched:
                            if resolution is not None:
                                description = task_description.strip()
                            else:
                                description = '<div class=comments><P id="execute" title=comments><FONT color="blue">%s.</FONT></P></div>' % msg('To office review')

                    for user in users:
                        if type(user) is TupleType:
                            task_id = self.CreateTaskInTransition( object
                                        , title=title
                                        , involved_users=None
                                        , task_template_id=task_template_id
                                        , description=description
                                        , supervisors=supervisors
                                        , resolution=resolution
                                        )

                            if not task_id:
                                continue
                            task = object.followup.getTask( task_id )
                            if task is None:
                                continue
                            followup_tasks.append( task_id )
                            bind_to = task_id
                            resolution = None
                            if matched:
                                supervisors = None
                            break

                for user in users:
                    n += 1
                    if type(user) is TupleType:
                        group, IsDAGroup, group_users = user
                        if group_users:
                            group_id = group[6:]
                            user_name = membership.getGroupTitle( group_id )
                        else:
                            continue
                        #description = task_description and ("%s.\n%s" % ( title, task_description )).strip() or "%s." % title
                        description = task_description and task_description.strip() or title or ''

                        task_id = self.CreateTaskInTransition( object
                                        , title="%s" % user_name
                                        , involved_users=group_users
                                        , task_template_id=task_template_id
                                        , bind_to=bind_to
                                        , description=description
                                        , IsDAGroup=IsDAGroup
                                        , suspended_timeout=suspended_timeout*n
                                        , supervisors=supervisors
                                        , resolution=resolution
                                        )

                        followup_tasks.append( task_id )
                    else:
                        involved_users.append( user )

                if involved_users:
                    task_id = self.CreateTaskInTransition( object
                                        , title
                                        , involved_users
                                        , task_template_id
                                        , bind_to
                                        , supervisors=supervisors
                                        , resolution=resolution
                                        )

                    followup_tasks.append( task_id )

                if task is not None and len(followup_tasks) > 1:
                    task.setFollowupTasks( followup_tasks )
                    task_id = task.getId()

        return { 'task_id' : task_id }

    def CreateTaskInTransition( self, object, title, involved_users, task_template_id, bind_to=None, enabled=1, \
            no_mail=0, description=None, IsDAGroup=None, confirm_by_turn=None, cycle_by_turn=None, \
            suspended_timeout=None, supervisors=None, resolution=None ):
        """
            Creates a task in transition
        """
        task_id = None
        REQUEST = self.REQUEST
        prefix = task_template_id and task_template_id+'_' or ''

        finalize_settings = {}
        if REQUEST.has_key( prefix+'finalize_type' ):
            finalize_settings['type'] = REQUEST.get( prefix+'finalize_type', 'all' )

        try:
            if REQUEST.get( prefix+'auto_finalize', None ):
                finalize_settings['auto'] = 1
            if getattr( self, '_delegation_of_authority', None ):
                if not REQUEST.has_key( prefix+'delegation_of_authority', 1 ):
                    finalize_settings['delegate'] = 1
                elif IsDAGroup and REQUEST.get( prefix+'delegation_of_authority', 1 ):
                    finalize_settings['delegate'] = 1
        except:
            pass

        duration_time_field = prefix + 'duration_time'
        message = ''

        if getattr( self, '_expiration_alarm', None ):
            alarm_settings = {}
            alarm_settings['type'] = 'percents'
            alarm_settings['value'] = 10
            alarm_settings['note'] = None
            alarm_settings['include_descr'] = 1
        else:
            alarm_settings = None

        if description == '...':
            _d = ''
        elif not description:
            _d = self._getField('description')
        else:
            _d = description

        portal_log( self, 'TaskDefinitionFollowup', 'CreateTaskInTransition', 'settings', ( \
            alarm_settings, finalize_settings, resolution, \
            REQUEST is not None and 1 or 0 ) )

        if object and title:
            task_id, message = object.followup.createTask( title=title
                    , description=_d
                    , involved_users=involved_users
                    , supervisors=supervisors
                    , brains_type=self.task_brains
                    , expiration_date=self._getExpirationDate( duration_time_field )
                    , task_template_id=task_template_id
                    , alarm_settings=alarm_settings
                    , finalize_settings=finalize_settings
                    , resolution=resolution
                    , enabled=enabled
                    , bind_to=bind_to
                    , hand_roles=self._getField('hand_roles')
                    , no_mail=no_mail
                    , confirm_by_turn=confirm_by_turn
                    , cycle_by_turn=cycle_by_turn
                    , suspended_timeout=suspended_timeout
                    , no_commit=1
                )
        else:
            return None

        if not task_id or message:
            raise SimpleError, message

        return task_id

    def _getResolution( self, task_template_id, REQUEST=None ):
        """
            Returns resolution body
        """
        resolution = None
        prefix = task_template_id and task_template_id+'_' or ''

        try:
            if REQUEST.get( prefix+'resolution_or_commission', None ):
                author = REQUEST.get( prefix+'resolution_author', 'personal' )
                if author == 'personal':
                    membership = getToolByName( self, 'portal_membership' )
                    member = membership.getAuthenticatedMember()
                    name = member.getMemberBriefName()
                    position = member.getMemberNotes()
                    author = ('%s %s' % (position, name)).strip()
                resolution = { 'author' : author, 'date' : parseDateTime( DateTime() ) }
                resolution['involved_users'] = self._getField('involved_users')
        except:
            pass

        return resolution

    def _getExpirationDate( self, duration_time_field=None ):
        """
            Returns expiration date by current date and interval.

            Result:

                Instance on DateTime
        """
        interval = self.interval
        if not duration_time_field:
            duration_time_field = 'duration_time'
        
        if 'interval' in self._allow_edit and self.amIonTop():
            if not self._date_format or self._date_format == 'interval':
                if self.REQUEST.has_key( duration_time_field ):
                    value = self.REQUEST[ duration_time_field ]
                    interval = value['days'] * 86400 + value['hours'] * 3600 + value['minutes'] * 60
            elif self.REQUEST.has_key('expiration'):
                return parseDate('expiration', self.REQUEST)

        return DateTime( float( DateTime().timeTime() + interval ) )

    def _getField( self, name, force=None, default=None ):
        """
            Return specific fields.

            Arguments:

                'name' -- name of field

            Purpose of this method, is to handle the case when action teamplate's
            fields are changed during 'change_state' page. In this case we takes field's
            value from REQUEST, but not from 'self'.
        """
        if getattr(self, 'REQUEST', None) is not None:
            REQUEST = self.REQUEST
        else:
            REQUEST = aq_get( self, 'REQUEST', None ) or {}
        if not force:
            if getattr( self, name, None ) is None:
                return None
            if name in self._allow_edit and self.amIonTop() and REQUEST.has_key(self._getFormNameByName( name )):
                return REQUEST.get(self._getFormNameByName( name ))
        else:
            return REQUEST.get(self._getFormNameByName( name ), default) or None

        # otherwise return not changed value
        return getattr( self, name, None )

    def _getFormNameByName( self, name ):
        """
            Return field's name on form, in case changed field during 'change_state' page

            Arguments:

                'name' -- field's name
        """
        # return name of field on form
        return "_new_%s_%s" % ( self.ret_from_up['task_template_id'], name )

    def _getSupervisors( self, object, distinct=1 ):
        supervisors = self._getField('supervisors')
        supervisors = self._convertRolesToUsers( supervisors, object )
        if not supervisors:
            return None
        if distinct:
            supervisors = self._distinctUserId( supervisors )
        managed_by_supervisor = self._getField('managed_by_supervisor', \
            default=getattr( self, '_supervisor_mode', None ), \
            force=1)
        return ( supervisors, managed_by_supervisor, )

    def _getInvolvedUsers( self, object, distinct=1 ):
        involved_users = self._getField('involved_users')
        involved_users = self._convertRolesToUsers( involved_users, object )
        if not involved_users and getattr( self, '_auto_sending_by_default', None ):
            if getattr( self, 'to_whom', None ):
                involved_users = object.getCategoryAttribute( self.to_whom )
        if not involved_users:
            raise ValueError, 'Involved users is not defined'
        if distinct:
            involved_users = self._distinctUserId( involved_users )
        return involved_users

    def _convertRolesToUsers( self, users_and_roles, object ):
        res = []
        if type(users_and_roles) == StringType:
            users = [ users_and_roles ]
        else:
            users = users_and_roles
        for user_id in users:
            if self._isIdRole( user_id ):
                user_ids = self._getUserIdByRoleId( user_id, object )
                if user_ids:
                    res.extend( user_ids )
            elif self._isEditIdRole( user_id ):
                role_id = user_id[12:]
                user_ids = self._getField( role_id, force=1 )
                if user_ids:
                    res.extend( user_ids )
            elif self._isIdGroup( user_id ):
                group_id = user_id
                group, IsDAGroup, user_ids = self._getUserIdByGroupId( group_id )
                if user_ids:
                    res.append( ( group, IsDAGroup, user_ids ) )
            else:
                res.append( user_id )
        return res

    def _isIdRole( self, item_id ):
        return item_id.startswith( '__role_' )

    def _isEditIdRole( self, item_id ):
        return item_id.startswith( '__edit_role_' )

    def _isIdGroup( self, item_id ):
        return item_id.startswith( 'group' )

    def _getUserIdByRoleId( self, role_id, object ):
        dept_title = None
        msg = getToolByName( self, 'msg' )
        if self.use_department:
            dept_title = object.getCategoryAttribute( self.use_department )
            if not dept_title:
                raise ValueError, msg('User secretary department is not defined (%s)' % self.use_department)
        return DFRoleManager().getUserIdByRole( parent=self, role_id=role_id, object=object, segment_uid=self.dest_folder_uid, dept_title=dept_title )

    def _getUserIdByGroupId( self, group_id ):
        membership = getToolByName( self, 'portal_membership', None )
        group = group_id.startswith('group') and group_id[6:] or group_id
        user_ids = None
        IsDAGroup = 0
        if group:
            user_ids = [ x for x in membership.getGroupMembers( group ) if x is not None ]
            IsDAGroup = membership.getGroupAttribute( group, attr_name='DA' ) and 1 or 0
            return ( 'group:%s' % group, IsDAGroup, user_ids )
        return ( group, IsDAGroup, None )

    def _distinctUserId( self, users ):
        res = []
        applied = []
        for x in users:
            id = type(x) is TupleType and x[0] or x
            if not id in applied:
                applied.append( id )
                res.append( x )
        return res

InitializeClass( TaskDefinitionFollowup )


class TaskDefinitionFormFollowup( TaskDefinitionForm ):
    """
        Class-view.
        Showing form for edit action template's fields.
    """
    def __init__( self, task_brains='' ):
        TaskDefinitionForm.__init__( self )

    def getForm( self, task_definition_array ):
        """
            Returns parsed dtml 'task_definition_followup.dtml'.

            Arguments:

                'task_definition_array' -- array with values, to fill form
        """
        form = ''
        form += TaskDefinitionForm.getForm( self, task_definition_array )
        form += self._getDtml( 'task_definition_followup', taskDefinitionArray=task_definition_array )
        return form

    def getTaskDefinitionFormScriptOnSubmit( self ):
        """
            Returns java-script fragment, to check form's fields on submit
        """
        script = TaskDefinitionForm.getTaskDefinitionFormScriptOnSubmit( self )
        script += """
        if( !window.document.getElementsByName('title')[0].value ) {
            alert('Please specify task title');
            return false;
        }
        if( window.document.getElementsByName('involved_users:list')[0].options.length )
            selectAll( form.involved_users_selected_users );
        try {
        if( window.document.getElementsByName('supervisors:list')[0].options.length )
            selectAll( form.supervisors_selected_users );
        } catch (error) {}
        return true;
        """
        return script


class TaskDefinitionControllerFollowup( TaskDefinitionController ):
    """
        Class-controller.
        Takes values from request, and store them to model.
    """
    def __init__( self, task_brains='' ):
        TaskDefinitionController.__init__( self )
        self.task_brains=task_brains

    def getEmptyArray( self, emptyArray=None ):
        """
            Return empty dictionary
        """
        if emptyArray is None or type(emptyArray) is not DictType:
            x = {}
        else:
            x = emptyArray.copy()
        x = TaskDefinitionController.getEmptyArray( self, x )

        x['task_brains'] = ''
        x['title'] = ''
        #x['type'] = None
        x['involved_users'] = []
        x['supervisors'] = []
        x['interval'] = 86400
        x['description'] = ''
        x['_allow_edit'] = []
        x['_date_format'] = []
        x['_supervisor_mode'] = None
        x['_resolution_or_commission'] = None
        x['_auto_finalize'] = 0
        x['_expiration_alarm'] = 0
        x['_auto_sending_by_default'] = 0
        x['_delegation_of_authority'] = 0
        x['_confirmation_type'] = 0
        x['_full_userlist'] = 0
        x['to_whom'] = None
        x['hand_roles'] = [ReaderRole]
        x['dest_folder_uid'] = None
        x['use_department'] = None

        return x

    def getTaskDefinitionByRequest( self, request ):
        """
            Return task definition instance by request.

            Arguments:

                'request' -- REQUEST

            Result:

                Filled by form 'TaskDefinitionFollowup' instance
        """
        taskDefinition = TaskDefinitionFollowup( self.task_brains )
        TaskDefinitionController.getTaskDefinitionByRequest( self, request, taskDefinition )
        # fill specific fields from request
        #
        if request.has_key('title'):
            taskDefinition.title = request['title']
        if request.has_key('description'):
            taskDefinition.description = request['description']
        if request.has_key('involved_users'):
            taskDefinition.involved_users = request['involved_users']
        if request.has_key('supervisors'):
            taskDefinition.supervisors = request['supervisors']
        if request.has_key('duration_time'):
            # parseTime( 'duration_time', request )
            taskDefinition.interval = request['duration_time']['days'] * 86400 + request['duration_time']['hours'] * 3600 + request['duration_time']['minutes'] * 60

        if request.has_key('_allow_edit'):
            taskDefinition._allow_edit = request['_allow_edit']
        else:
            taskDefinition._allow_edit = []

        if request.has_key('_date_format'):
            taskDefinition._date_format = request['_date_format']
        else:
            taskDefinition._date_format = None

        if request.has_key('_supervisor_mode'):
            taskDefinition._supervisor_mode = request['_supervisor_mode']
        else:
            taskDefinition._supervisor_mode = None

        if request.has_key('_resolution_or_commission'):
            taskDefinition._resolution_or_commission = request['_resolution_or_commission']
        else:
            taskDefinition._resolution_or_commission = None

        if request.has_key('_auto_finalize'):
            taskDefinition._auto_finalize = 1
        else:
            taskDefinition._auto_finalize = 0

        if request.has_key('_expiration_alarm'):
            taskDefinition._expiration_alarm = 1
        else:
            taskDefinition._expiration_alarm = 0

        if request.has_key('_auto_sending_by_default'):
            taskDefinition._auto_sending_by_default = 1
        else:
            taskDefinition._auto_sending_by_default = 0

        if request.has_key('_delegation_of_authority'):
            taskDefinition._delegation_of_authority = 1
        else:
            taskDefinition._delegation_of_authority = 0

        if request.has_key('_confirmation_type'):
            taskDefinition._confirmation_type = request['_confirmation_type']
        else:
            taskDefinition._confirmation_type = 0

        if request.has_key('_full_userlist'):
            taskDefinition._full_userlist = 1
        else:
            taskDefinition._full_userlist = 0

        if request.has_key('to_whom'):
            taskDefinition.to_whom = request['to_whom']
        else:
            taskDefinition.to_whom = None

        if request.has_key('hand_roles'):
            taskDefinition.hand_roles = request['hand_roles']
        else:
            taskDefinition.hand_roles = [ReaderRole]

        if request.has_key('dest_folder_uid'):
            taskDefinition.dest_folder_uid = request['dest_folder_uid']
        else:
            taskDefinition.dest_folder_uid = None

        taskDefinition.use_department = request.get('use_department', None)

        return taskDefinition


class TaskDefinitionRegistryFollowup( TaskDefinitionRegistry ):
    """
        Class-registry.
        Register information to factory.
    """
    def __init__( self ):
        TaskDefinitionRegistry.__init__( self )
        self.type_list = [
                      { "id": "followup_request", "title": "Creating task#msg_delim# \"#msg_delim#Request#msg_delim#\"" },
                      { "id": "followup_directive", "title": "Creating task#msg_delim# \"#msg_delim#Directive#msg_delim#\"" },
                      { "id": "followup_information", "title": "Creating task#msg_delim# \"#msg_delim#Information#msg_delim#\"" },
                      { "id": "followup_signature_request", "title": "Creating task#msg_delim# \"#msg_delim#Signature request#msg_delim#\"" },
                      { "id": "followup_inspection", "title": "Creating task#msg_delim# \"#msg_delim#Inspection#msg_delim#\"" },
                      { "id": "followup_registration", "title": "Creating task#msg_delim# \"#msg_delim#Registration#msg_delim#\"" },
        ]

        self.task_definition_type_2_brains = \
          { "followup_request": "request",
            "followup_directive": "directive",
            "followup_information": "information",
            "followup_signature_request": "signature_request",
            "followup_inspection": "inspection",
            "followup_registration": "registration"
          }

    def getDtmlTokenForInfoByType( self, task_definition_type ):
        """
            Return token neede for making dtml file name.
            See TaskDefinitionAbstract.TaskDefinitionRegistry.getDtmlTokenForInfoByType
        """
        return 'followup'

    def getControllerImplementation( self, task_definition_type ):
        """
            Returns class-controller implementation by type.

            Arguments:

                'task_definition_type' -- type

            Result:

                Instance of 'TaskDefinitionControllerFollowup'
        """
        return TaskDefinitionControllerFollowup( self._getTaskDefinitionTaskBrainsByType( task_definition_type ) )

    def getFormImplementation( self, task_definition_type ):
        """
            Returns class-form implementation by type.

            Arguments:

                'task_definition_type' -- type

            Result:

                Instance of 'TaskDefinitionFormFollowup'
        """
        return TaskDefinitionFormFollowup( self._getTaskDefinitionTaskBrainsByType( task_definition_type ) )

    def _getTaskDefinitionTaskBrainsByType( self, task_definition_type ):
        """
            Returns appropriate task's brains by specified task_defintion_type.

            Arguments:

                'task_definition_type' -- type of task definition
        """
        if task_definition_type in self.task_definition_type_2_brains.keys():
            return self.task_definition_type_2_brains[task_definition_type]
        return None
