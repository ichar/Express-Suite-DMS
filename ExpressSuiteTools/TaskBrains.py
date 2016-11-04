"""
Task brains definition class
$Id: TaskBrains.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 07/06/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

from Globals import DTMLFile
from types import ListType

from AccessControl import ClassSecurityInfo
from Acquisition import Implicit, aq_inner, aq_base, aq_parent
from DateTime import DateTime

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.utils import _checkPermission, _getAuthenticatedUser, getToolByName

from SimpleObjects import Persistent
from Config import Roles, TaskResultCodes, DemandRevisionCodes
from PortalLogger import portal_log, portal_error

from Utils import InitializeClass, getPlainText

MAX_INVOLVED = 3

registered_task_brains = {}

# TODO
task_validate_userids = ['']

def registerTaskBrains( brains ):
    tti = brains.task_type_information
    name = tti['id']
    registered_task_brains[name] = brains

def getTaskBrains( name ):
    return registered_task_brains[name]

def listTaskBrains( visible=None ):
    return [ registered_task_brains[id] for id in registered_task_brains.keys() if not visible or \
             registered_task_brains[id].task_type_information['visible'] \
             ]


class TaskBrains( Persistent, Implicit ):

    mail_alarm = DTMLFile( 'skins/mail_templates/task.alarm', globals() )
    mail_supervisor_notify = DTMLFile( 'skins/mail_templates/task.supervisor_notify', globals() )
    mail_supervisor_canceled = DTMLFile( 'skins/mail_templates/task.supervisor_cancelled', globals() )
    mail_expiration_alarm = DTMLFile( 'skins/mail_templates/task.expiration_alarm', globals() )
    mail_changes = DTMLFile( 'skins/mail_templates/task.inform_changes', globals() )
    mail_finalized = DTMLFile( 'skins/mail_templates/task.finalized', globals() )

    mail_user_reviewed = DTMLFile( 'skins/mail_templates/task.reviewed', globals() )
    mail_user_not_reviewed = DTMLFile( 'skins/mail_templates/task.not_reviewed', globals() )
    mail_user_included = DTMLFile( 'skins/mail_templates/task.directive_user_included', globals() )
    mail_user_excluded = DTMLFile( 'skins/mail_templates/task.directive_user_excluded', globals() )

    def onFinalize( self, REQUEST=None, result_code=None, notify_list=None ):
        """
            Common task finalization method for any brains type
        """
        # we should re-finalize the task if it's activated by worflow especially for signature requests
        if result_code != TaskResultCodes.TASK_RESULT_CANCELLED:
            if not self.canBePublished():
                return

        try: user_who_finalize = _getAuthenticatedUser(self).getUserName()
        except: user_who_finalize = 'System Processes'

        if REQUEST is not None:
            if not result_code:
                result_code = REQUEST.get('result_code', None)
            report_text = getPlainText(REQUEST.get('text', ''))
        else:
            report_text = ''
        if not result_code:
            result_code = TaskResultCodes.TASK_RESULT_SUCCESS

        self.Finalize( result_code, REQUEST )
        if not self.isFinalized() or not notify_list:
            return

        if type(notify_list) is ListType and user_who_finalize in notify_list:
            notify_list.remove( user_who_finalize )
        if not notify_list:
            return

        self.send_mail( notify_list, 'mail_finalized', user_who_finalize=user_who_finalize, report_text=report_text )

    def ExpirationAlarm( self, exclude_list=[], SendToCreator=1 ):
        """
            Notifies users that task is going to expire soon.
            The method is called automatically by the portal scheduling
            service.
        """
        template = getattr( self, 'mail_expiration_alarm' )
        if not template:
            return

        if self.canBePublished():
            exclude_list.extend( self.listUsersWithClosedReports() )
            notify_list = [ user for user in self.InvolvedUsers( no_recursive=1 ) if user not in exclude_list ]

            if SendToCreator: 
                notify_list.append( self.Creator() )
            for supervisor in self.Supervisors():
                if supervisor not in notify_list:
                    notify_list.append( supervisor )

            kw = {}
            kw['task_url'] = self.absolute_url(canonical=1, no_version=1) + '/view'
            kw['time_left'] = int((self.expires() - DateTime()) * 86400)

            self.send( template, notify_list, **kw )

    def check_if_shouldFinalize( self ):
        """
            Checks finalize settings if task should be finalized before all involved users respond
        """
        finalize_settings = self.FinalizeSettings()
        if not ( finalize_settings and finalize_settings.has_key('type') ):
            finalize_settings = { 'type' : 'all' }

        membership = getToolByName( self, 'portal_membership' )
        uname = _getAuthenticatedUser(self).getUserName()
        involved_users = self.InvolvedUsers( no_recursive=1 )
        finalized_users = self.listUsersWithClosedReports()
        pending_users = self.PendingUsers()
        supervisors = self.Supervisors()

        if not ( pending_users or supervisors ):
            return True

        IsFinalize = 0

        # Check delegation of authority at first
        if self.hasDelegationOfAuthority():
            queue = finalize_settings.get('queue', None)
            if queue:
                IsFinalize = self.isFinalizedByDAGroup( queue=queue, finalized_users=finalized_users )
            elif len(finalized_users) > 0 or \
                self.UserSatysfiedRequest( layer='involved_users', member=uname, isclosed=1 ):
                IsFinalize = 1

        # Check all response
        elif finalize_settings['type'] == 'all' and pending_users:
            pass

        # Check any response
        elif finalize_settings['type'] == 'any' and len(finalized_users) > 0:
            IsFinalize = 1

        # Check VIP response
        elif finalize_settings['type'] == 'vip':
            members = membership.expandUserList( user_groups=('VIP',) )
            if uname in members:
                IsFinalize = 1

        # Check somebody or reviewer's response
        elif finalize_settings['type'] in ( 'somebody', 'reviewer' ):
            involved_departments = []

            for user_id in involved_users:
                member = membership.getMemberById( user_id )
                if member is None:
                    continue
                department = member.getProperty( 'department', None )
                if department not in involved_departments:
                    involved_departments.append( department )

            # Check department only
            if finalize_settings['type'] == 'somebody':
                for user_id in finalized_users:
                    member = membership.getMemberById( user_id )
                    if member is None:
                        continue
                    department = member.getProperty( 'department', None )
                    if department in involved_departments:
                        involved_departments.remove( department )

            # Check department reviewers (workflow chief)
            elif finalize_settings['type'] == 'reviewer':
                for user_id in finalized_users:
                    member = membership.getMemberById( user_id )
                    if member is None:
                        continue
                    department = member.getProperty( 'department', None )
                    if membership.MemberHasRoleInContext( self, user_id, Roles.WorkflowChief ) and \
                            department in involved_departments:
                        involved_departments.remove( department )

            if len(involved_departments) == 0:
                IsFinalize = 1

        # Check department chiefs
        elif finalize_settings['type'] == 'chief':
            groups = [ group['group_id'] for group in membership.getListGroups( attr='CH', sys=1 ) ]
            members = membership.expandUserList( user_groups=groups )
            if members: 
                chiefs = [ x for x in involved_users if x in members ]
                for user_id in finalized_users:
                    if user_id in chiefs:
                        chiefs.remove( user_id )
                if len(chiefs) == 0:
                    IsFinalize = 1

        if IsFinalize and not supervisors:
            return True

        # Validate supervisor's reviewing
        if supervisors:
            supervisor_mode = self.isManagedBySupervisor()
            if self.isSupervisor( uname ):
                if supervisor_mode != 'default':
                    return True
                elif not pending_users:
                    return True
            elif supervisor_mode == 'info':
                return True
            else:
                if not pending_users and supervisor_mode != 'request':
                    if self.searchResponses( status='review' ):
                        return True

        return False

    def inform_notified_users( self, template, report_text='' ):
        notify_list = self.getCreatorAndSupervisors()
        if self.getNotifyMode():
            notify_list.extend( self.getNotifyList( isclosed=1 ) )
        if notify_list:
            self.send_mail( notify_list, template, report_text=report_text )
 
    def inform_involved_users( self, template, report_text='' ):
        notify_list = self.InvolvedUsers( no_recursive=1 )
        if notify_list:
            self.send_mail( notify_list, template, report_text=report_text )


class TaskBrains_Directive( TaskBrains ):
    """
        Directive task type definition

        Directive is an imperative task given by the leader to it's subordinates.
    """

    # Mail templates declaration
    mail_user_committed = DTMLFile( 'skins/mail_templates/task.directive_committed', globals() )
    mail_user_rejected = DTMLFile( 'skins/mail_templates/task.directive_rejected', globals() )
    mail_user_failed = DTMLFile( 'skins/mail_templates/task.directive_failed', globals() )
    mail_user_accepted = DTMLFile( 'skins/mail_templates/task.directive_accepted', globals() )
    mail_task_enabled = DTMLFile( 'skins/mail_templates/task.request_user_included', globals() )

    task_type_information = \
                        { 
                              'id'           : 'directive'
                            , 'title'        : 'Directive'
                            , 'sortkey'      : 1
                            , 'visible'      : True
                            , 'description'  : ''
                            , 'url'          : 'task_add_form'
                            , 'acquire_finalization_status': 1
                            , 'permissions'  : CMFCorePermissions.View
                            , 'success_status' : 'commit'
                            , 'responses'    : 
                            (
                                { 'id'          : 'commit'
                                , 'title'       : 'Commit task'
                                , 'description' : 'Commit task'
                                , 'progresslist_title': 'User(s) committed to a task'
                                , 'message'     : 'You have committed to this task'
                                , 'url'         : 'task_response_form'
                                , 'handler'     : 'onCommit'
                                , 'icon'        : 'task_user_committed.gif'
                                , 'layer'       : 'involved_users'
                                , 'manual_report_close': 0
                                , 'condition'   : "python: here.isInvolved(member) and not here.searchResponses(member=member, status='reject')"
                                }
                              , { 'id'          : 'failure'
                                , 'title'       : 'Report task failure'
                                , 'description' : 'Report task failure'
                                , 'progresslist_title': 'User(s) failed to commit task'
                                , 'message'     : 'You have failed to commit this task'
                                , 'url'         : 'task_response_form'
                                , 'handler'     : 'onFailure'
                                , 'icon'        : 'task_user_rejected.gif'
                                , 'layer'       : 'involved_users'
                                , 'manual_report_close': 0
                                , 'condition'   : "python: here.isInvolved(member) and here.searchResponses(member=member) and not here.searchResponses(member=member, status='reject')"
                                }
                              , { 'id'          : 'task_start'
                                , 'title'       : 'Accept task'
                                , 'description' : 'Accept task'
                                , 'progresslist_title': 'User(s) accepted the task'
                                , 'message'     : 'You have accepted this task'
                                , 'url'         : 'task_response_form'
                                , 'handler'     : 'onAccept'
                                , 'icon'        : 'task_user_accepted.gif'
                                , 'layer'       : 'startpad'
                                , 'condition'   : "python: here.isInvolved(member) and not (here.searchResponses(member=member, layer='startpad') or here.searchResponses(member=member, layer='involved_users'))"
                                }
                              , { 'id'          : 'reject'
                                , 'title'       : 'Reject task'
                                , 'description' : 'Reject task'
                                , 'progresslist_title': 'User(s) rejected a task'
                                , 'message'     : 'You have rejected this task'
                                , 'url'         : 'task_response_form'
                                , 'handler'     : 'onReject'
                                , 'icon'        : 'task_user_rejected.gif'
                                , 'layer'       : 'startpad'
                                , 'condition'   : "python: here.isInvolved(member) and not (here.searchResponses(member=member, layer='startpad') or here.searchResponses(member=member, layer='involved_users'))"
                                }
                              , { 'id'          : 'review'
                                , 'title'       : 'Review'
                                , 'description' : 'Review task'
                                , 'progresslist_title': 'User(s) reviewed a task'
                                , 'message'     : 'You have reviewed this task'
                                , 'url'         : 'task_response_form'
                                , 'handler'     : 'onReview'
                                , 'layer'       : 'reviewers'
                                , 'condition'   : "python: here.isSupervisor(member) and (here.isManagedBySupervisor()=='default' or here.isManagedBySupervisor()=='request' and here.checkKickedUser(member) or not here.InvolvedUsers(no_recursive=1) and here.hasResponses(recursive=1))"
                                }
                              , { 'id'          : 'enable'
                                , 'title'       : 'Enable task'
                                , 'description' : 'Enable request'
                                , 'progresslist_title': 'User(s) enabled the request'
                                , 'message'     : 'You have enabled this request'
                                , 'url'         : 'task_enable_form'
                                , 'handler'     : 'onEnable'
                                , 'layer'       : 'superusers'
                                , 'condition'   : "python: here.isSuperuser(member) and not here.isEnabled()"
                                }
                              , { 'id'          : 'finalize'
                                , 'title'       : 'Finalize'
                                , 'description' : 'Finalize task'
                                , 'progresslist_title': 'User(s) finalized a task'
                                , 'message'     : 'You have finalized this task'
                                , 'url'         : 'task_finalize_form'
                                , 'handler'     : 'onFinalize'
                                , 'layer'       : 'superusers'
                                , 'condition'   : "python: here.isCreator(member)"
                                }
                              , { 'id'          : 'send_to_review'
                                , 'title'       : 'To review'
                                , 'description' : 'Send alarm to supervisors'
                                , 'progresslist_title': 'User(s) sent the task to supervisors'
                                , 'message'     : 'You have sent this task to review'
                                , 'url'         : 'task_response_form'
                                , 'handler'     : 'onActivateReview'
                                , 'layer'       : 'superusers'
                                , 'condition'   : "python: here.isCreator(member) and here.isManagedBySupervisor()=='request' and not (here.searchResponses(status='review') or here.searchResponses(status='send_to_review'))"
                                }
                            )
                            , 'results'      :
                            ( { 'id' : TaskResultCodes.TASK_RESULT_SUCCESS,   'title'   : 'success'   }
                            , { 'id' : TaskResultCodes.TASK_RESULT_CANCELLED, 'title'   : 'cancelled' }
                            , { 'id' : TaskResultCodes.TASK_RESULT_FAILED,    'title'   : 'failed'    }
                            )
                        }


    def validate( self ):
        user_roles = _getAuthenticatedUser(self).getRolesInContext(self)
        user_id = _getAuthenticatedUser(self).getUserName()

        if self.isViewer() or \
            _checkPermission(CMFCorePermissions.ModifyPortalContent, self) or \
            _checkPermission(CMFCorePermissions.ManagePortal, self) or \
            Roles.Editor in user_roles or Roles.Writer in user_roles or \
            user_id in task_validate_userids:
            return 1

        parents = self.parentsInThread()
        for parent in parents:
            if hasattr(parent, 'isViewer') and parent.isViewer():
               return 1

        return

    ## Event handlers

    def onAccept( self, REQUEST=None ):
        report_text = REQUEST and getPlainText(REQUEST.get('text', '')) or None
        self.send_mail( self.getCreatorAndSupervisors(), 'mail_user_accepted', report_text=report_text )

    def onCommit( self, REQUEST=None ):
        self.process_request()
        report_text = REQUEST and getPlainText(REQUEST.get('text', '')) or None
        self.send_mail( self.getCreatorAndSupervisors(), 'mail_user_committed', report_text=report_text )

    def onReject( self, REQUEST=None ):
        self.process_request( status='reject' )
        report_text = REQUEST and getPlainText(REQUEST.get('text', '')) or None
        self.send_mail( self.getCreatorAndSupervisors(), 'mail_user_rejected', report_text=report_text )

    def onEnable( self, REQUEST=None ):
        report_text = getPlainText(REQUEST.get('text', ''))
        if report_text:
            self.Enable( no_mail=1 )
            self.inform_involved_users( 'mail_task_enabled', report_text=report_text )
        else:
            self.Enable()

    def onActivateReview( self, REQUEST=None ):
        supervisors = self.Supervisors()
        if not supervisors:
            return
        report_text = REQUEST and getPlainText(REQUEST.get('text', '')) or None
        self.setKickedUsers( supervisors )
        self.send_mail( supervisors, 'mail_supervisor_notify', report_text=report_text )

    def onFailure( self, REQUEST=None ):
        self.process_request( status='failure' )
        report_text = REQUEST and getPlainText(REQUEST.get('text', '')) or None
        self.send_mail( self.getCreatorAndSupervisors(), 'mail_user_failed', report_text=report_text )

    def onReview( self, REQUEST=None ):
        self.process_request()
        report_text = REQUEST and getPlainText(REQUEST.get('text', '')) or None
        self.send_mail( [ self.Creator() ], 'mail_user_reviewed', report_text=report_text )

    def onFinalize( self, REQUEST=None, result_code=None ):
        if REQUEST is not None:
            notify_list = self.PendingUsers()
            for supervisor in self.Supervisors():
                if supervisor not in notify_list:
                    notify_list.append( supervisor )
        else:
            notify_list = self.getCreatorAndSupervisors()
        TaskBrains.onFinalize( self, REQUEST, result_code, notify_list )

    def process_request( self, status=None ):
        if self.canBePublished() and self.check_if_shouldFinalize():
            root = self.findRootTask()
            if root is None:
                return
            root_id = root.getId()
            IsRootExists = root_id and root_id != self.getId() and 1 or 0

            if status == 'reject' or self.searchResponses( status='reject' ):
                code = TaskResultCodes.TASK_RESULT_CANCELLED
            elif status == 'failure' or self.searchResponses( status='failure' ):
                code = TaskResultCodes.TASK_RESULT_FAILED
            else:
                code = TaskResultCodes.TASK_RESULT_SUCCESS

            self.Finalize( code )

            if not self.isFinalized() or not IsRootExists:
                return
            if root.BrainsType() != self.BrainsType():
                return

            try: should_be_finalized = root.get_brains().check_if_shouldFinalize()
            except: should_be_finalized = None

            portal_log( self, 'TaskBrains_Request', 'process_request', 'Finalize-root', ( root.getId(), code, should_be_finalized ) )
            if not should_be_finalized:
                return

            root.Finalize( code )

            if root.isFinalized():
                return
            portal_error( 'TaskBrains_Request.process_request', "root not finalized: %s, code: [%s]" % ( self.getId(), code ) )

InitializeClass( TaskBrains_Directive, __version__ )


class TaskBrains_Request( TaskBrains ):
    """
        Request task type definition

        Directive is an imperative task given by the leader to it's subordinates.
    """

    # Mail templates declaration
    mail_user_signed = DTMLFile( 'skins/mail_templates/task.request_signed', globals() )
    mail_user_satisfied = DTMLFile( 'skins/mail_templates/task.request_satisfied', globals() )
    mail_user_rejected = DTMLFile( 'skins/mail_templates/task.request_rejected', globals() )
    mail_demand_revision = DTMLFile( 'skins/mail_templates/task.request_demand_revision', globals() )
    mail_deliver_execution = DTMLFile( 'skins/mail_templates/task.request_deliver_execution', globals() )
    mail_task_enabled = DTMLFile( 'skins/mail_templates/task.request_user_included', globals() )

    task_type_information = \
                        { 
                              'id'           : 'request'
                            , 'title'        : 'Request'
                            , 'sortkey'      : 2
                            , 'visible'      : True
                            , 'description'  : ''
                            , 'url'          : 'document_confirmation_form'
                            , 'acquire_finalization_status': 1
                            , 'condition'    : 'python: here.implements(\'isDocument\')'
                            , 'permissions'  : CMFCorePermissions.View
                            , 'success_status' : 'satisfy'
                            , 'responses'    :
                            ( 
                                { 'id'          : 'satisfy'
                                , 'title'       : 'Satisfy request'
                                , 'description' : 'Satisfy request'
                                , 'progresslist_title': 'User(s) satisfied the request'
                                , 'message'     : 'You have satisfied this request'
                                , 'url'         : 'task_response_form'
                                , 'handler'     : 'onSatisfy'
                                , 'icon'        : 'task_user_committed.gif'
                                , 'layer'       : 'involved_users'
                                , 'condition'   : "python: here.isInvolved(member)"
                                }
                              , { 'id'          : 'revise'
                                , 'title'       : 'Demand revision'
                                , 'description' : 'Demand revision'
                                , 'progresslist_title': 'User(s) demanded request revision'
                                , 'message'     : 'You have demanded request revision'
                                , 'url'         : 'task_response_form'
                                , 'handler'     : 'onDemandRevision'
                                , 'icon'        : 'task_user_rejected.gif'
                                , 'layer'       : 'involved_users'
                                , 'manual_report_close': 0
                                , 'condition'   : "python: here.isInvolved(member)"
                                }
                              , { 'id'          : 'deliver'
                                , 'title'       : 'Deliver execution'
                                , 'description' : 'Deliver execution'
                                , 'progresslist_title': 'User(s) delivered the task execution'
                                , 'message'     : 'You have delivered the task execution'
                                , 'url'         : 'task_deliver_form'
                                , 'handler'     : 'onDeliverExecution'
                                , 'icon'        : 'task_user_delivered.gif'
                                , 'layer'       : 'involved_users'
                                , 'manual_report_close': 0
                                , 'condition'   : "python: here.isInvolved(member) and not here.isDelivered() and here.isInTurn(check_root=1, parent_only=1)"
                                }
                              , { 'id'          : 'enable'
                                , 'title'       : 'Enable task'
                                , 'description' : 'Enable request'
                                , 'progresslist_title': 'User(s) enabled the request'
                                , 'message'     : 'You have enabled this request'
                                , 'url'         : 'task_enable_form'
                                , 'handler'     : 'onEnable'
                                , 'layer'       : 'superusers'
                                , 'condition'   : "python: here.isCreator(member) and not here.isEnabled() and here.isInTurn(check_root=1, parent_only=1)"
                                }
                              , { 'id'          : 'finalize'
                                , 'title'       : 'Finalize'
                                , 'description' : 'Finalize request'
                                , 'progresslist_title': 'User(s) finalized the request'
                                , 'message'     : 'You have finalized this request'
                                , 'url'         : 'task_finalize_form'
                                , 'handler'     : 'onFinalize'
                                , 'layer'       : 'superusers'
                                , 'condition'   : "python: here.isCreator(member) and here.canBePublished()"
                                }
                            )
                            , 'results'      :
                            ( { 'id' : TaskResultCodes.TASK_RESULT_SUCCESS,   'title'   : 'success' }
                            , { 'id' : TaskResultCodes.TASK_RESULT_FAILED,    'title'   : 'failed' }
                            , { 'id' : TaskResultCodes.TASK_RESULT_CANCELLED, 'title'   : 'cancelled' }
                            )
                        }

    def validate( self ):
        user_roles = _getAuthenticatedUser(self).getRolesInContext(self)
        user_id = _getAuthenticatedUser(self).getUserName()

        if self.isViewer() or \
           _checkPermission(CMFCorePermissions.ModifyPortalContent, self) or \
           _checkPermission(CMFCorePermissions.ManagePortal, self) or \
           Roles.Editor in user_roles or Roles.Writer in user_roles:
               return 1

        parents = self.parentsInThread()
        for parent in parents:
             if hasattr(parent, 'isViewer') and parent.isViewer():
                return 1

        return

    ## Event handlers

    def onSign( self, REQUEST=None ):
        self.setDemandRevisionCode( code=DemandRevisionCodes.DEMAND_REVISION_SUCCESS, check_root=1 )
        self.process_request()
        report_text = REQUEST and getPlainText(REQUEST.get('text', '')) or None
        self.inform_notified_users( 'mail_user_signed', report_text=report_text )

    def onSatisfy( self, REQUEST=None ):
        self.setDemandRevisionCode( code=DemandRevisionCodes.DEMAND_REVISION_SUCCESS, check_root=1 )
        self.process_request()
        report_text = REQUEST and getPlainText(REQUEST.get('text', '')) or None
        self.inform_notified_users( 'mail_user_satisfied', report_text=report_text )

    def onReject( self, REQUEST=None ):
        self.setDemandRevisionCode( code=DemandRevisionCodes.DEMAND_REVISION_FAILED, check_root=1 )
        self.process_request()
        report_text = REQUEST and getPlainText(REQUEST.get('text', '')) or None
        self.inform_notified_users( 'mail_user_rejected', report_text=report_text )

    def onDemandRevision( self, REQUEST=None ):
        self.setDemandRevisionCode( code=DemandRevisionCodes.DEMAND_REVISION_FAILED, check_root=1 )
        report_text = REQUEST and getPlainText(REQUEST.get('text', '')) or None
        self.inform_notified_users( 'mail_demand_revision', report_text=report_text )

    def onDeliverExecution( self, REQUEST=None ):
        if not self.DeliverExecution( REQUEST ):
            return
        report_text = REQUEST and getPlainText(REQUEST.get('text', '')) or None
        self.inform_notified_users( 'mail_deliver_execution', report_text=report_text )

    def onEnable( self, REQUEST=None ):
        report_text = getPlainText(REQUEST.get('text', ''))
        if report_text:
            self.Enable( no_mail=1 )
            self.inform_involved_users( 'mail_task_enabled', report_text=report_text )
        else:
            self.Enable()

    def onFinalize( self, REQUEST=None, result_code=None ):
        notify_list = self.getCreatorAndSupervisors()
        if self.getNotifyMode():
            notify_list.extend( self.getNotifyList(isclosed=1) )
        if not result_code and REQUEST is not None:
            result_code = REQUEST.get('result_code', None)
        TaskBrains.onFinalize( self, REQUEST, result_code, notify_list )
        if self.isFinalized() and result_code == TaskResultCodes.TASK_RESULT_SUCCESS:
            self.enableFollowupTasks()

    def process_request( self ):
        if self.canBePublished() and self.check_if_shouldFinalize():
            root = self.findRootTask()
            if root is None:
                return
            root_id = root.getId()
            IsRootExists = root_id and root_id != self.getId() and 1 or 0

            if self.searchResponses( status='reject' ):
                code = TaskResultCodes.TASK_RESULT_CANCELLED
            else:
                code = TaskResultCodes.TASK_RESULT_SUCCESS

            if self.isInTurn( check_root=1, turn_type='cycle_by_turn', parent_only=1 ):
                if root.enableFollowupTasks( task_in_turn_id=self.getId() ) in [0,1]:
                    return
            else:
                portal_log( self, 'TaskBrains_Request', 'process_request', 'Finalize-self', ( self.getId(), code ) )
                self.Finalize( code )
                if self.isFinalized():
                    if self.enableFollowupTasks():
                        return
                else:
                    portal_error( 'TaskBrains_Request.process_request', "task not finalized: %s, code: [%s]" % ( self.getId(), code ) )

            if root.isCycleByTurn():
                if not root.checkDemandRevisionSuccess():
                    return
            else:
                bound_tasks = root.followup.getBoundTasks( recursive=1 )
                for task in bound_tasks:
                    if task.getId() != root_id and not task.isFinalized():
                        return

            if not IsRootExists:
                return
            if root.BrainsType() != self.BrainsType():
                return

            try: should_be_finalized = root.get_brains().check_if_shouldFinalize()
            except: should_be_finalized = None

            portal_log( self, 'TaskBrains_Request', 'process_request', 'Finalize-root', ( root.getId(), code, should_be_finalized ) )
            if not should_be_finalized:
                return

            root.Finalize( code )

            if root.isFinalized():
                return
            portal_error( 'TaskBrains_Request.process_request', "root not finalized: %s, code: [%s]" % ( self.getId(), code ) )

InitializeClass( TaskBrains_Request, __version__ )


class TaskBrains_SignatureRequest( TaskBrains_Request ):

    task_type_information = \
                        { 
                              'id'           : 'signature_request'
                            , 'title'        : 'Signature request'
                            , 'sortkey'      : 3
                            , 'visible'      : True
                            , 'description'  : ''
                            , 'url'          : 'document_confirmation_form'
                            , 'acquire_finalization_status': 0
                            , 'condition'    : 'python: here.implements(\'isDocument\')'
                            , 'permissions'  : CMFCorePermissions.View
                            , 'success_status' : 'sign'
                            , 'responses'    :
                            (
                                { 'id'          : 'sign'
                                , 'title'       : 'Sign'
                                , 'description' : 'Sign the document'
                                , 'progresslist_title': 'User(s) signed the document'
                                , 'message'     : 'You have signed the document'
                                , 'url'         : 'task_response_form'
                                , 'handler'     : 'onSign'
                                , 'icon'        : 'task_user_committed.gif'
                                , 'layer'       : 'involved_users'
                                , 'condition'   : "python: here.isInvolved(member)"
                                }
                              , { 'id'          : 'reject'
                                , 'title'       : 'Reject signature request'
                                , 'description' : 'Reject signature request'
                                , 'progresslist_title': 'User(s) rejected to sign'
                                , 'message'     : 'You have rejected to sign'
                                , 'url'         : 'task_response_form'
                                , 'handler'     : 'onReject'
                                , 'icon'        : 'task_user_rejected.gif'
                                , 'layer'       : 'involved_users'
                                , 'condition'   : "python: here.isInvolved(member)"
                                }
                              , { 'id'          : 'finalize'
                                , 'title'       : 'Finalize'
                                , 'description' : 'Finalize request'
                                , 'progresslist_title': 'User(s) finalized the request'
                                , 'message'     : 'You have finalized this request'
                                , 'url'         : 'task_finalize_form'
                                , 'handler'     : 'onFinalize'
                                , 'layer'       : 'superusers'
                                , 'condition'   : "python: here.isCreator(member)"
                                }
                            )
                            , 'results'      :
                            ( { 'id' : TaskResultCodes.TASK_RESULT_SUCCESS,   'title'   : 'document signed'         }
                            , { 'id' : TaskResultCodes.TASK_RESULT_FAILED,    'title'   : 'document was not signed' }
                            , { 'id' : TaskResultCodes.TASK_RESULT_CANCELLED, 'title'   : 'cancelled'               }
                            )
                        }

    # the rest of the brain stuff is inherited from the TaskBrains_Request

    def validate( self ):
        return 1

InitializeClass( TaskBrains_SignatureRequest, __version__ )


class TaskBrains_Inform( TaskBrains ):

    # Mail templates declaration

    mail_user_informed = DTMLFile( 'skins/mail_templates/task.info_user_informed', globals() )

    task_type_information = \
                        { 
                              'id'           : 'information'
                            , 'title'        : 'Information'
                            , 'sortkey'      : 4
                            , 'visible'      : True
                            , 'url'          : 'task_add_form'
                            , 'acquire_finalization_status': 1
                            , 'description'  : ''
                            , 'permissions'  : CMFCorePermissions.View
                            , 'success_status' : 'informed'
                            , 'responses'    :
                            ( 
                                { 'id'          : 'informed'
                                , 'title'       : 'Informed'
                                , 'description' : 'Confirm that you have been informed about the document contents'
                                , 'progresslist_title': 'User(s) familiarized with the document'
                                , 'message'     : 'You have familiarized with the document'
                                , 'url'         : 'task_response_form'
                                , 'handler'     : 'onInform'
                                , 'icon'        : 'task_user_committed.gif'
                                , 'layer'       : 'involved_users'
                                , 'condition'   : "python: here.isInvolved(member)"
                                }
                              , { 'id'          : 'review'
                                , 'title'       : 'Review'
                                , 'description' : 'Review task'
                                , 'progresslist_title': 'User(s) reviewed a task'
                                , 'message'     : 'You have reviewed this task'
                                , 'url'         : 'task_response_form'
                                , 'handler'     : 'onReview'
                                , 'layer'       : 'reviewers'
                                , 'condition'   : "python: here.isSupervisor(member)"
                                }
                              , { 'id'          : 'finalize'
                                , 'title'       : 'Finalize'
                                , 'description' : 'Finalize request'
                                , 'progresslist_title': 'User(s) finalized the request'
                                , 'message'     : 'You have finalized this request'
                                , 'url'         : 'task_finalize_form'
                                , 'handler'     : 'onFinalize'
                                , 'layer'       : 'superusers'
                                , 'condition'   : "python: here.isCreator(member)"
                                }
                            )
                            , 'results'      :
                            ( { 'id' : TaskResultCodes.TASK_RESULT_SUCCESS,   'title'   : 'success'   }
                            , { 'id' : TaskResultCodes.TASK_RESULT_CANCELLED, 'title'   : 'cancelled' }
                            )
                        }

    def validate( self ):
        user_roles = _getAuthenticatedUser(self).getRolesInContext(self)
        user_id = _getAuthenticatedUser(self).getUserName()

        if self.isViewer() or \
            _checkPermission(CMFCorePermissions.ModifyPortalContent, self) or \
            _checkPermission(CMFCorePermissions.ManagePortal, self) or \
            Roles.Editor in user_roles or Roles.Writer in user_roles or \
            user_id in task_validate_userids:
            return 1

        parents = self.parentsInThread()
        for parent in parents:
             if hasattr(parent, 'isViewer') and parent.isViewer():
                return 1

        return

    def onInform( self, REQUEST=None ):
        report_text = REQUEST and getPlainText(REQUEST.get('text', '')) or None
        if self.isEnabled() and not self.isFinalized() and self.check_if_shouldFinalize():
            self.Finalize(TaskResultCodes.TASK_RESULT_SUCCESS)
        self.send_mail( self.getCreatorAndSupervisors(), 'mail_user_informed', report_text=report_text )

    def onReview( self, REQUEST=None ):
        report_text = REQUEST and getPlainText(REQUEST.get('text', '')) or None
        self.send_mail( [ self.Creator() ], 'mail_user_reviewed', report_text=report_text )

    def onFinalize( self, REQUEST=None, result_code=None ):
        notify_list = self.PendingUsers()
        for supervisor in self.Supervisors():
            if supervisor not in notify_list:
                notify_list.append( supervisor )
        TaskBrains.onFinalize( self, REQUEST, result_code, notify_list )

InitializeClass( TaskBrains_Inform, __version__ )


class TaskBrains_Registration( TaskBrains_Directive ):

    task_type_information = \
                        { 
                              'id'           : 'registration'
                            , 'title'        : 'Registration'
                            , 'sortkey'      : 5
                            , 'visible'      : False
                            , 'url'          : 'task_add_form'
                            , 'acquire_finalization_status': 1
                            , 'description'  : ''
                            , 'permissions'  : CMFCorePermissions.View
                            , 'success_status' : 'task_register'
                            , 'responses'    :
                            ( 
                                { 'id'          : 'task_register'
                                , 'title'       : 'To register'
                                , 'description' : 'Make the document registration'
                                , 'progresslist_title': 'User(s) accepted the task to register'
                                , 'message'     : 'You have registered this document'
                                , 'url'         : 'document_registration_form'
                                , 'handler'     : 'onAccept'
                                , 'icon'        : 'task_user_accepted.gif'
                                , 'layer'       : 'startpad'
                                , 'condition'   : "python: here.isInvolved(member) and not here.searchResponses(member=member, layer='startpad')"
                                }
                              , { 'id'          : 'failure'
                                , 'title'       : 'Report task failure'
                                , 'description' : 'Report task failure'
                                , 'progresslist_title': 'User(s) failed to register task'
                                , 'message'     : 'You have failed to register this task'
                                , 'url'         : ''
                                , 'handler'     : 'onFailure'
                                , 'icon'        : 'task_user_rejected.gif'
                                , 'layer'       : 'involved_users'
                                , 'manual_report_close': 1
                                , 'condition'   : "python: 1==0"
                                }
                              , { 'id'          : 'reject'
                                , 'title'       : 'Reject task'
                                , 'description' : 'Reject task'
                                , 'progresslist_title': 'User(s) rejected a task'
                                , 'message'     : 'You have rejected this task'
                                , 'url'         : 'task_response_form'
                                , 'handler'     : 'onReject'
                                , 'icon'        : 'task_user_rejected.gif'
                                , 'layer'       : 'startpad'
                                , 'condition'   : "python: here.isInvolved(member) and not here.searchResponses(member=member, layer='startpad')"
                                }
                              , { 'id'          : 'review'
                                , 'title'       : 'Review'
                                , 'description' : 'Review task'
                                , 'progresslist_title': 'User(s) reviewed a task'
                                , 'message'     : 'You have reviewed this task'
                                , 'url'         : 'task_response_form'
                                , 'handler'     : 'onReview'
                                , 'layer'       : 'reviewers'
                                , 'condition'   : "python: here.isSupervisor(member)"
                                }
                              , { 'id'          : 'finalize'
                                , 'title'       : 'Finalize'
                                , 'description' : 'Finalize task'
                                , 'progresslist_title': 'User(s) finalized a task'
                                , 'message'     : 'You have finalized this task'
                                , 'url'         : 'task_finalize_form'
                                , 'handler'     : 'onFinalize'
                                , 'layer'       : 'superusers'
                                , 'condition'   : "python: here.isCreator(member)"
                                }
                            )
                            , 'results'      :
                            ( { 'id' : TaskResultCodes.TASK_RESULT_SUCCESS,   'title'   : 'success'   }
                            , { 'id' : TaskResultCodes.TASK_RESULT_FAILED,    'title'   : 'document was not registered' }
                            , { 'id' : TaskResultCodes.TASK_RESULT_CANCELLED, 'title'   : 'cancelled' }
                            )
                        }

    # the rest of the brain stuff is inherited from the TaskBrains_Directive

    def validate( self ):
        return 1

    ## Event handlers

    def onAccept( self, REQUEST=None ):
        if self.Supervisors() and self.searchResponses( status='review' ):
            self.process_request()

    def onCommit( self, REQUEST=None ):
        return

    def onFailure( self, REQUEST=None ):
        return

    def onReview( self, REQUEST=None ):
        if self.searchResponses( status='task_register' ):
            self.process_request()

    def onReject( self, REQUEST=None ):
        self.process_request( status='cancelled' )
        report_text = REQUEST and getPlainText(REQUEST.get('text', '')) or None
        self.send_mail( self.getCreatorAndSupervisors(), 'mail_user_rejected', report_text=report_text )

    def onFinalize( self, REQUEST=None, result_code=None ):
        supervisors = self.Supervisors()
        if supervisors:
            if not self.searchResponses( status='review' ):
                msg = getToolByName(self, 'msg')
                report_text = msg('The document was not reviewed by supervisors')
                self.send_mail( supervisors, 'mail_user_not_reviewed', report_text=report_text )
                return
        TaskBrains.onFinalize( self, REQUEST, result_code )
        portal_log( self, 'TaskBrains_Registration', 'onFinalize', 'debug', ( result_code, `self` ) )

    def process_request( self, status=None ):
        if self.canBePublished():
            root = self.findRootTask()
            root_id = root.getId()
            IsRootExists = root_id and root_id != self.getId() and 1 or 0

            code = status or TaskResultCodes.TASK_RESULT_SUCCESS
            self.Finalize(code)

InitializeClass( TaskBrains_Registration, __version__ )


class TaskBrains_Inspect( TaskBrains_Inform ):

    task_type_information = \
                        { 
                              'id'           : 'inspection'
                            , 'title'        : 'Inspection'
                            , 'sortkey'      : 6
                            , 'visible'      : False
                            , 'url'          : 'task_add_form'
                            , 'acquire_finalization_status': 1
                            , 'description'  : ''
                            , 'permissions'  : CMFCorePermissions.View
                            , 'success_status' : 'inspected'
                            , 'responses'    :
                            ( 
                                { 'id'          : '*change_state*'
                                , 'title'       : ''
                                , 'description' : ''
                                , 'progresslist_title': 'User(s) inspected the document'
                                , 'message'     : 'You have inspected the document'
                                , 'url'         : 'change_state'
                                , 'handler'     : 'onInform'
                                , 'icon'        : 'task_user_committed.gif'
                                , 'layer'       : 'involved_users'
                                , 'condition'   : "python: here.isInvolved(member)"
                                }
                              , { 'id'          : 'inspected'
                                , 'title'       : 'Inspected'
                                , 'description' : 'Confirm that you have inspected with the document contents'
                                , 'progresslist_title': 'User(s) inspected the document'
                                , 'message'     : 'You have inspected the document'
                                , 'url'         : 'task_inspect_form'
                                , 'handler'     : 'onInform'
                                , 'icon'        : 'task_user_committed.gif'
                                , 'layer'       : 'involved_users'
                                , 'condition'   : "python: here.isInvolved(member)"
                                }
                              , { 'id'          : 'review'
                                , 'title'       : 'Review'
                                , 'description' : 'Review task'
                                , 'progresslist_title': 'User(s) reviewed a task'
                                , 'message'     : 'You have reviewed this task'
                                , 'url'         : 'task_response_form'
                                , 'handler'     : 'onReview'
                                , 'layer'       : 'reviewers'
                                , 'condition'   : "python: here.isSupervisor(member)"
                                }
                              , { 'id'          : 'finalize'
                                , 'title'       : 'Finalize'
                                , 'description' : 'Finalize request'
                                , 'progresslist_title': 'User(s) finalized the request'
                                , 'message'     : 'You have finalized this request'
                                , 'url'         : 'task_finalize_form'
                                , 'handler'     : 'onFinalize'
                                , 'layer'       : 'superusers'
                                , 'condition'   : "python: here.isCreator(member)"
                                }
                            )
                            , 'results'      :
                            ( { 'id' : TaskResultCodes.TASK_RESULT_SUCCESS,   'title'   : 'success'   }
                            , { 'id' : TaskResultCodes.TASK_RESULT_CANCELLED, 'title'   : 'cancelled' }
                            )
                        }

InitializeClass( TaskBrains_Inspect, __version__ )


class TaskBrains_PublicationRequest( TaskBrains_Request ):

    task_type_information = \
                        { 
                              'id'           : 'publication_request'
                            , 'title'        : 'Publication request'
                            , 'sortkey'      : 5
                            , 'visible'      : False
                            , 'description'  : ''
                            , 'url'          : 'document_confirmation_form'
                            , 'condition'    : 'python: here.implements(\'isDocument\') and here.isInCategory(\'Publication\')'
                            , 'permissions'  : CMFCorePermissions.View
                            , 'success_status' : 'publish'
                            , 'responses'    :
                            ( 
                                { 'id'          : 'publish'
                                , 'title'       : 'Publish'
                                , 'description' : 'Publish the document'
                                , 'progresslist_title': 'User(s) published the document'
                                , 'message'     : 'You have published the document'
                                , 'url'         : 'task_response_form'
                                , 'handler'     : 'onSatisfy'
                                , 'icon'        : 'task_user_committed.gif'
                                , 'layer'       : 'involved_users'
                                , 'condition'   : "python: here.isInvolved(member)"
                                }
                              , { 'id'          : 'reject'
                                , 'title'       : 'Reject publication request'
                                , 'description' : 'Reject publication request'
                                , 'progresslist_title': 'User(s) rejected the publication'
                                , 'message'     : 'You have rejected the publication'
                                , 'url'         : 'task_response_form'
                                , 'handler'     : 'onReject'
                                , 'icon'        : 'task_user_rejected.gif'
                                , 'layer'       : 'involved_users'
                                , 'condition'   : "python: here.isInvolved(member)"
                                }
                              , { 'id'          : 'finalize'
                                , 'title'       : 'Finalize'
                                , 'description' : 'Finalize request'
                                , 'progresslist_title': 'User(s) finalized the request'
                                , 'message'     : 'You have finalized this request'
                                , 'url'         : 'task_finalize_form'
                                , 'handler'     : 'onFinalize'
                                , 'layer'       : 'superusers'
                                , 'condition'  : "python: here.isCreator(member)"
                                }
                            )
                            , 'results'     :
                            ( { 'id' : TaskResultCodes.TASK_RESULT_SUCCESS,   'title'   : 'document published'   }
                            , { 'id' : TaskResultCodes.TASK_RESULT_FAILED,    'title'   : 'publication rejected' }
                            , { 'id' : TaskResultCodes.TASK_RESULT_CANCELLED, 'title'   : 'cancelled'            }
                            )
                        }

    # the rest of the brain stuff is inherited from the TaskBrains_Request

    ## Event handlers

    def onSatisfy( self, REQUEST=None ):
        self.send_mail( self.getCreatorAndSupervisors(), 'mail_user_satisfied' )
        self.process_request()

    def onReject( self, REQUEST=None ):
        self.send_mail( self.getCreatorAndSupervisors(), 'mail_user_rejected' )
        self.process_request()
        # Finalize task immediately
        self.Finalize( TaskResultCodes.TASK_RESULT_FAILED )

    def onFinalize( self, REQUEST=None, result_code=None ):
        # Rollback to the evolutive state since request is finalized manually
        self.doWorkflowAction('evolve', REQUEST.get('text'))
        TaskBrains.onFinalize( self, REQUEST, result_code )

    def process_request( self ):
        if self.canBePublished() and not self.PendingUsers():
            root = self.findRootTask()
            root_id = root.getId()
            IsRootExists = root_id and root_id != self.getId() and 1 or 0

            text = self.REQUEST.get('text')
            if self.searchResponses( status='reject' ):
                code = TaskResultCodes.TASK_RESULT_FAILED
                action = 'evolve'
            else:
                code = TaskResultCodes.TASK_RESULT_SUCCESS
                action = 'publish'

            self.Finalize( code )
            self.doWorkflowAction( action, text )

            if self.isFinalized():
                self.enableFollowupTasks()

    def doWorkflowAction( self, action, comment ):
        workflow = getToolByName( self, 'portal_workflow' )
        IsError = 0
        try:
            workflow.doActionFor( self.getBase(), action, comment=comment )
        except:
            IsError = 1

InitializeClass( TaskBrains_PublicationRequest, __version__ )


registerTaskBrains(TaskBrains_Directive)
registerTaskBrains(TaskBrains_Request)
registerTaskBrains(TaskBrains_SignatureRequest)
registerTaskBrains(TaskBrains_Inform)
registerTaskBrains(TaskBrains_Registration)
registerTaskBrains(TaskBrains_Inspect)
registerTaskBrains(TaskBrains_PublicationRequest)
