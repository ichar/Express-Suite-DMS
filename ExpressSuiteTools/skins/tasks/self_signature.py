## Script (Python) "self_signature"
##bind container=container
##bind context=context
##parameters=workflow_action, brains_type='signature_request', text='', close_report=1, status='satisfy'
##title=Make self signature request
from Products.ExpressSuiteTools.SecureImports import DateTime, parseDate, parseTime, parseDateTime, refreshClientFrame, \
     SimpleError, BeginThread, CommitThread, UpdateRequestRuntime

REQUEST = context.REQUEST

start_time = DateTime()
member = context.portal_membership.getAuthenticatedMember()
username = member.getUserName()
message = ''

BeginThread( context, 'self_signature', force=1 )
#
# Create task for user self signature
#
task_title = 'Self signature request'
tesk_description = 'Self signature request for the document'
task_template_id = 'SelfSignature'

brains_type = REQUEST['brains_type']

requested_users = [username]
alarm_settings = {}
task = None

try:
    task = context.followup.createTask( title="%s" % ( context.msg(task_title)  )
                     , description="%s" % ( context.msg(tesk_description) )
                     , involved_users=requested_users
                     , creator=username
                     , supervisors=None
                     , effective_date=None
                     , expiration_date=None
                     , alarm_settings=alarm_settings
                     , duration=86400
                     , brains_type=brains_type
                     , REQUEST=REQUEST
                     , task_template_id=task_template_id
                     , no_mail=1
                     , redirect=0
                     , no_commit=1
                     )
    #task = task_id and context.followup.getTask(task_id) or None
    IsError = 0

except SimpleError, msg:
    message = '%s $ $ error' % str(msg) or 'Bad task'
    IsError = 1
except:
    raise

# Check if not and return error
if IsError or task is None:
    action = 'view'
    return REQUEST.RESPONSE.redirect( \
           context.absolute_url( redirect=1, action=action, message=message, frame='document_frame' ),
           status=303 )
#
# Make satisfaction response for this task
#
status = REQUEST['status']
close_report = 1 #REQUEST['close_report']
text = REQUEST['text']
response_id = None

try:
    if task is not None:
        response_id, message = task.Respond( status=status
                     , text=text
                     , document=None
                     , close_report=close_report
                     , redirect=0
                     , no_commit=1
                     , no_update_runtime=1
                     , REQUEST=REQUEST
                     )
    IsError = 0

except SimpleError, msg:
    message = '%s $ $ error' % msg or 'Bad response'
    IsError = 1
except:
    raise

if response_id is None or IsError or task is None:
    action = 'view'
    return REQUEST.RESPONSE.redirect( \
            context.absolute_url( redirect=1, action=action, message=message, frame='document_frame' ),
            status=303 )
#
# Run invoke workflow action
#
workflow_action = REQUEST['workflow_action']
comment = None

base = task.getBase()
while base.implements('isVersion'):
    base = base.aq_parent

uid = base.getUid()
IsMoved = 0
ob = base

try:
    if workflow_action:
        res = context.portal_workflow.doActionFor( base, workflow_action, comment=comment )
    else:
        res = {}
    message = 'You have successfully signed the document'
    IsError = 0

except SimpleError, msg:
    message = '%s, uid:%s $ $ error' % ( str(msg), uid )
    IsError = 1
except:
    raise

CommitThread( context, 'self_signature', IsError, force=1, subtransaction=None )

try:
    IsMoved = res and res['ObjectMoved'] and 1 or 0
    if IsMoved and res['ob'].getUid() == uid:
        ob = res['ob']
except:
    pass

end_time = DateTime()
UpdateRequestRuntime( context, username, start_time, end_time, 'self_signature' )

refreshClientFrame( 'workspace' )

return ob.redirect( action='view', message=message )
