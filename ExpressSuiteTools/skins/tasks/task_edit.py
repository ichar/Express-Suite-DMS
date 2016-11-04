## Script (Python) "task_edit"
##bind container=container
##bind context=context
##parameters=title, description=None, periodical=None, task_id=None, brains_type='directive', alarm_type=None, auto_finalize=None, notify_mode=None, managed_by_supervisor=None
##title=Add a task item
##
from Products.ExpressSuiteTools.SecureImports import DateTime, parseDate, parseTime, parseDateTime, parseMemberIDList, \
     BeginThread, CommitThread, UpdateRequestRuntime, refreshClientFrame, \
     UniformIntervalTE, SimpleError

REQUEST = context.REQUEST

membership = context.portal_membership
properties = context.portal_properties

start_time = DateTime()
member = membership.getAuthenticatedMember()
username = member.getUserName()
message = ''

# Get base object if we are in context of version get first not version object

redirect_to = None
base = context
task = None

if context is not None and context.parent().implements('isPortalRoot'):
    IsPortalRoot = 1
else:
    while base.implements('isVersion') or base.implements('isTaskItem'):
        base = base.getVersionable()
    IsPortalRoot = 0

if not base.implements('isHTMLDocument'):
    base = context

def go_back( message, info=None ):
    # Check valid URI to redirect
    message = '%s $ %s $ error' % ( message, info or '' )
    if IsPortalRoot:
        action = 'followup_tasks_form'
        if context.aq_parent is not None:
            url = context.aq_parent.absolute_url( action=action, frame=None, message=message )
        else:
            url = context.absolute_url( action=action, frame=None, message=message )
    elif base is not None:
        url = base.absolute_url( action='document_follow_up_form', frame='document_frame', message=message )
    else:
        url = context.absolute_url( action='view', message=message )
    return REQUEST['RESPONSE'].redirect( url )

if not title:
    message = 'Please specify task title'
    return go_back( message )

duration = None
temporal_expr = None

if periodical:
    temporal_expr = UniformIntervalTE( seconds=parseTime('frequency_time', REQUEST) )
    duration = parseTime('duration_time', REQUEST)

effective_date = parseDate('effective_date', REQUEST, None)
expiration_date = parseDate('expiration_date', REQUEST, None)
plan_time = parseTime('plan_time', REQUEST)

alarm_settings = {}

if alarm_type == 'percents':
    alarm_settings['value'] = REQUEST['alarm_percents']
elif alarm_type == 'periodical':
    alarm_settings['value'] = REQUEST['alarm_period']
    alarm_settings['period_type'] = REQUEST['alarm_period_type']
elif alarm_type == 'custom':
    alarm_settings['value'] = map( parseDateTime, REQUEST.get('alarm_dates', ()))

if alarm_settings:
    alarm_settings['type'] = alarm_type
    alarm_settings['note'] = REQUEST['alarm_note']
    alarm_settings['include_descr'] = not not REQUEST.get('alarm_includes_descr')
else:
    alarm_settings = None

if REQUEST.get('disable', None):
    enabled = 0
else:
    enabled = 1

finalize_type = REQUEST.get('finalize_type', None) 
finalize_settings = finalize_type and { 'type' : finalize_type } or {}
delegation_of_authority_allowed = not not REQUEST.get('delegation_of_authority_allowed', None)

if auto_finalize and not periodical:
    finalize_settings['auto'] = 1

notify_mode = not not REQUEST.get('notify_mode', None)
requested = REQUEST.get('involved', None) or []

if REQUEST.get('involved_users_disabled', None):
    involved_users_disabled = 1
    involved_users = None
else:
    involved_users_disabled = 0
    involved_users = parseMemberIDList( context, requested, check_access=1 )

    suspended_mail = properties.getProperty('suspended_mail', 1)
    max_involved_users = properties.getProperty( 'max_involved_users', 0 )
    mail_threshold = properties.getProperty('mail_threshold', 50)

    if len(involved_users) > max_involved_users and max_involved_users > 0 and not suspended_mail:
        message = 'Too many involved users. Allowed: $ %s $ error' % str(max_involved_users)
        return go_back( message )
    elif len(involved_users) > mail_threshold:
        message = 'Too many involved users. Allowed: $ %s $ error' % str(mail_threshold)
        return go_back( message )

if not ( involved_users_disabled or involved_users ):
    if requested:
        message = 'Selected users have not default access. Please repeat!'
        return go_back( message ) #, str(requested)
    else:
        message = 'Please specify involved users'
        return go_back( message )

if not filter(lambda x, u=username: x!=u, involved_users):
    message = 'Involved users was typed incorrectly. You cannot select yourself'
    return go_back( message )

# Start committed transaction ================================================================

BeginThread( context, 'task_edit', force=1 )

delegation_of_authority = REQUEST.get('delegation_of_authority', None) and 1 or 0

if delegation_of_authority_allowed:
    finalize_settings['delegate'] = delegation_of_authority
    if involved_users is not None:
        if not task_id:
            requested = involved_users
        queue = parseMemberIDList( context, requested, check_delegate=1 )
        if queue:
            finalize_settings['queue'] = queue

if REQUEST.get('supervisors_disabled', None):
    supervisors = ( None, managed_by_supervisor, )
else:
    x = REQUEST.get('supervisors', None) or []
    if not x:
        supervisors = None
    else:
        supervisors = []
        for x in parseMemberIDList( context, x, check_delegate=1, check_access=1 ):
            id = x['id']
            typ = x['type']
            members = x['members']
            if id != 'users':
                IsDAGroup = typ == 'any' and 1 or 0
                supervisors.append( ( id, IsDAGroup, members ) )
            else:
                supervisors.extend( members )
        supervisors = ( supervisors, managed_by_supervisor, )

try:
    if task_id is None:
        task = context.createTask( title=title
                    , description=description
                    , involved_users=involved_users
                    , supervisors=supervisors
                    , effective_date=effective_date
                    , expiration_date=expiration_date
                    , plan_time=plan_time
                    , alarm_settings=alarm_settings
                    , finalize_settings=finalize_settings
                    , enabled=enabled
                    , brains_type=brains_type
                    , duration=duration
                    , notify_mode=notify_mode
                    , temporal_expr=temporal_expr
                    , REQUEST=REQUEST
                    , no_commit=1
                    , redirect=0
                    )
        redirect_to = None
        message = 'Task was successfully added'
    else:
        task = context.getTask(task_id)
        task.edit( title=title
                    , description=description
                    , involved_users=involved_users
                    , supervisors=supervisors
                    , duration=duration
                    , effective_date=effective_date
                    , expiration_date=expiration_date
                    , plan_time=plan_time
                    , alarm_settings=alarm_settings
                    , finalize_settings=finalize_settings
                    , notify_mode=notify_mode
                    , temporal_expr=temporal_expr
                    , no_commit=1
                    )
        redirect_to = task.absolute_url()
        message = 'Changes were successfully accepted'

except SimpleError, msg:
    message = str(msg)
    IsError = 1

except:
    raise

else:
    IsError = 0

IsDone = CommitThread( context, 'task_edit', IsError, force=1, subtransaction=None )

end_time = DateTime()
UpdateRequestRuntime( context, username, start_time, end_time, 'task_edit' )

if IsDone == -1:
    message = '%s $ $ error' % 'Members weren\'t notified because of error'
    if task is not None:
        return REQUEST['RESPONSE'].redirect( task.absolute_url( action='view', message=message ) )
    IsError = 1

if IsError:
    return go_back( message )
elif not redirect_to:
    if task is None:
        action = IsPortalRoot and 'followup_tasks_form' or ''
        redirect_to = context.absolute_url( action=action, message=message )
    else:
        redirect_to = task.absolute_url( action='view', message=message )

return REQUEST['RESPONSE'].redirect( redirect_to )
