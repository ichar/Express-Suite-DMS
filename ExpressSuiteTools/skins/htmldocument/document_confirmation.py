## Script (Python) "document_confirmation"
##bind container=container
##bind context=context
##parameters=alarm_type, title='', description='', requested=[], in_turn=0, brains_type, auto_finalize=None, notify_mode=None
##title=Add a task item
##
from Products.ExpressSuiteTools.SecureImports import DateTime, parseDate, parseDateTime, parseMemberIDList, \
     BeginThread, CommitThread, UpdateRequestRuntime, refreshClientFrame, \
     SimpleError

REQUEST = context.REQUEST

membership = context.portal_membership
properties = context.portal_properties

start_time = DateTime()
member = membership.getAuthenticatedMember()
username = member.getUserName()
message = ''

def go_back( message, info=None ):
    message = '%s $ %s $ error' % ( message, info or '' )
    url = context.absolute_url( action='document_confirmation_form', frame='document_frame', message=message )
    x = url.replace( '/followup', '' )
    return REQUEST['RESPONSE'].redirect( x )
    #return context.document_confirmation_form( context, REQUEST,
    #    **script.values( portal_status_message=message, portal_status_info=info, portal_status_style='error' ) )

confirm_by_turn = cycle_by_turn = 0

if in_turn in ['1', 'confirm_by_turn']:
    confirm_by_turn = 1
elif in_turn in ['2', 'cycle_by_turn']:
    cycle_by_turn = 1

expiration_date = parseDate('expiration', REQUEST)

if brains_type=='signature_request':
   cfm_msg = 'Signature request for the document'
   chain_msg = 'Chain signature request for the document'
elif confirm_by_turn:
   cfm_msg = 'Confirmation request of the document'
   chain_msg = 'Chain confirmation of the document'
elif cycle_by_turn:
   cfm_msg = 'Cycled request of the document'
   chain_msg = 'Chain cyclability of the document'
else:
   cfm_msg = 'Confirmation request of the document'
   chain_msg = 'Chain confirmation of the document'

suspended_mail = properties.getProperty('suspended_mail', 1)
max_involved_users = properties.getProperty( 'max_involved_users', 0 )
mail_threshold = properties.getProperty('mail_threshold', 50)

# Do not allow stupid users to crash everything here
if not requested:
    message = 'Please specify involved users'
    return go_back( message )

involved_users = parseMemberIDList( context, requested, check_access=1 )

if requested and not involved_users:
    message = 'Selected users have not default access. Please repeat!'
    return go_back( message, str(requested) )
elif not involved_users:
    message = 'Involved users are defined incorrect:'
    return go_back( message )

if len(involved_users) > max_involved_users and max_involved_users > 0 and not suspended_mail:
    message = 'Too many involved users. Allowed:'
    return go_back( message, str(max_involved_users) )
elif len(involved_users) > mail_threshold:
    message = 'Too many involved users. Allowed:' % str(mail_threshold)
    return go_back( message, str(mail_threshold) )

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

finalize_type = REQUEST.get('finalize_type', 'all') 
fs = finalize_type and { 'type' : finalize_type } or {}
delegation_of_authority_allowed = not not REQUEST.get('delegation_of_authority_allowed', None)

if auto_finalize and not ( confirm_by_turn or cycle_by_turn ):
    fs['auto'] = 1

if REQUEST.get( 'resolution_or_commission', None ):
    author = REQUEST.get( 'resolution_author', 'personal' )
    if author == 'personal':
        author = username
    resolution = { 'author' : author, 'date' : parseDateTime( DateTime() ) }
else:
    resolution = {}

notify_mode = not not REQUEST.get('notify_mode')

# Start committed transaction ================================================================

BeginThread( context, 'document_confirmation', force=1 )

base = context
while base.implements('isVersion') or base.implements('isTaskItem'):
    base = base.getVersionable() # base = base.aq_parent !!!

if not base.implements('isHTMLDocument'):
    base = context

task = None

try:
    if confirm_by_turn or cycle_by_turn:
        # Create head nonactive task just for informational/presentation purposes
        task_id, message = context.followup.createTask( \
                                            title="%s" % ( title or context.msg(chain_msg, add=0) )
                                          , description=description
                                          , involved_users=[]
                                          , expiration_date=expiration_date
                                          , brains_type=brains_type
                                          , alarm_settings=alarm_settings
                                          , notify_mode=notify_mode
                                          , confirm_by_turn=confirm_by_turn
                                          , cycle_by_turn=cycle_by_turn
                                          , no_commit=1
                                          )

        for u_id in requested:
            # Enable the first task in the chain
            enabled = task is None and 1 or 0
            if task is None or confirm_by_turn:
                task = context.followup.getTask( task_id )
                followup_tasks = []
            finalize_settings = fs.copy()
            if u_id[0:5] == 'group':
                group_id = u_id[6:]
                u_name = membership.getGroupTitle( group_id )
                involved_users = parseMemberIDList( context, [ u_id ], check_access=1 )
                IsDAGroup = membership.getGroupAttribute( group_id, attr_name='DA' )
                if delegation_of_authority_allowed and IsDAGroup:
                    delegation_of_authority = REQUEST.get('delegation_of_authority', None) and 1 or 0
                    finalize_settings['delegate'] = delegation_of_authority
                    if finalize_settings.has_key('type'):
                        del finalize_settings['type']
            else:
                u_name = membership.getMemberBriefName( u_id )
                involved_users = [ u_id ]
                finalize_settings['type'] = finalize_type or 'all'

            task_id, message = task.followup.createTask( \
                                            title="%s" % u_name
                                          , description=context.msg(cfm_msg, add=0)
                                          , involved_users=involved_users
                                          , expiration_date=expiration_date
                                          , brains_type=brains_type
                                          , enabled=enabled
                                          , alarm_settings=alarm_settings
                                          , finalize_settings=finalize_settings
                                          , notify_mode=notify_mode
                                          , no_commit=1
                                          )

            followup_tasks.append( task_id )
            task.setFollowupTasks( followup_tasks )
    else:
        if involved_users:
            finalize_settings = fs.copy()
            delegation_of_authority = REQUEST.get('delegation_of_authority', None) and 1 or 0
            finalize_settings['delegate'] = delegation_of_authority_allowed and delegation_of_authority and 1 or 0
            queue = parseMemberIDList( context, requested, check_delegate=1, check_access=1 )
            if queue:
                finalize_settings['queue'] = queue

            task = context.followup.createTask( \
                                            title="%s" % ( title or context.msg(cfm_msg, add=0) )
                                          , description=description
                                          , involved_users=involved_users
                                          , expiration_date=expiration_date
                                          , brains_type=brains_type
                                          , alarm_settings=alarm_settings
                                          , finalize_settings=finalize_settings
                                          , notify_mode=notify_mode
                                          , resolution=resolution
                                          , REQUEST=REQUEST
                                          , no_commit=1
                                          , redirect=0
                                          )

except SimpleError, msg_error:
    message = str(msg_error)
    IsError = 1

except:
    raise

else:
    message = 'Request was directed for confirmation'
    IsError = 0

IsDone = CommitThread( context, 'document_confirmation', IsError, force=1, subtransaction=None )

if IsDone == -1:
    message = '%s $ $ error' % 'Members weren\'t notified because of error'

end_time = DateTime()
UpdateRequestRuntime( context, username, start_time, end_time, brains_type )

if IsError:
    return go_back( message )

refreshClientFrame( ['workspace', 'followup_menu'] )

if task is not None:
    return task.redirect( action='view', message=message )

return base.redirect( action='document_follow_up_form', message=message )
