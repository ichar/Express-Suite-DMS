## Script (Python) "content_status_modify"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=workflow_action=None, comment='', with_respond=None
##title=Modify the status of a content object
##
from Products.ExpressSuiteTools.SecureImports import DateTime, refreshClientFrame, SimpleError, \
     BeginThread, CommitThread, UpdateRequestRuntime, SetCustomBaseRoles, \
     portal_log, portal_info, portal_error, \
     getObjectByUid

start_time = DateTime()
member = context.portal_membership.getAuthenticatedMember()
username = member.getUserName()
message = ''

if not workflow_action:
    msg_error = 'Invalid request, workflow_action is not defined'
    portal_info( 'content_status_modify', ( \
        msg_error, context.physical_path(), workflow_action, username ), exc_info=True )
    return context.redirect( action='view', message='%s $ $ error' % msg_error )

BeginThread( context, 'content_status_modify', force=1 )

# Invoke workflow action
# if we are in context of version get first not version object
base = context
while base.implements('isVersion') or base.implements('isTaskItem'):
    base = base.getVersionable() # base = base.aq_parent !!!

if not base.implements('isHTMLDocument'):
    base = context

uid = base.getUid()
IsMoved = 0
ob = base
res = None

try:
    res = context.portal_workflow.doActionFor( base, workflow_action, comment=comment )

except SimpleError, msg_error:
    msg_error = str(msg_error)
    message = '%s $ $ error' % msg_error
    portal_error( 'content_status_modify', ( \
        msg_error, uid, context.physical_path(), workflow_action, username, res ), exc_info=False )
    IsError = 1

else:
    message = 'State changed'
    IsError = 0

if with_respond and not IsError and hasattr(context, 'Respond'):
    context.Respond( '*change_state*', close_report=1, no_commit=1 ) # , REQUEST=context.REQUEST

IsDone = CommitThread( context, 'content_status_modify', IsError, force=1, subtransaction=None )

if IsDone == -1:
    message = '%s $ $ error' % 'Members weren\'t notified because of error'

try:
    IsMoved = res and res['ObjectMoved'] and 1 or 0
    if IsMoved and res['ob'].getUid() == uid:
        ob = res['ob']
        SetCustomBaseRoles( ob )
except:
    pass

end_time = DateTime()
UpdateRequestRuntime( context, username, start_time, end_time, workflow_action )

if IsError:
    return ob.redirect( action='view', message=message )

refreshClientFrame( ['workspace', 'followup_menu'] )

return ob.redirect( action='view', message=message )
