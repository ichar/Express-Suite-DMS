## Script (Python) "task_inspect"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=text_format=None, text=None, file='', SafetyBelt='', IsEditFieldsOnly=0, log_message='', status='', response=None, close_report=1
##title=Inspect the document
##
from Products.ExpressSuiteTools.SecureImports import DateTime, SimpleError, ResourceLockedError, \
     BeginThread, CommitThread, UpdateRequestRuntime, ObjectHasCustomCategory

REQUEST = context.REQUEST

start_time = DateTime()
member = context.portal_membership.getAuthenticatedMember()
username = member.getUserName()
message = ''
action = ''

BeginThread( context, 'task_inspect', force=1 )

base = context.getBase()

if base is None or not base.isCurrentVersionEditable():
    message = ( "Current version is not editable. "
                "Be sure you are editing the last (editable) version. "
                "(You may be able to recover your changes using the browser 'back' button.)")
    return REQUEST.RESPONSE.redirect(
            context.absolute_url( redirect=1, action='view', message=message ),
            status=303 )

version = base.getEditableVersion()
document = version.aq_parent
category = document.Category()

try:
    if text is not None:
        document.edit( text_format, text, file, safety_belt=SafetyBelt )
        message = "Document saved."
        action = 'text'

    # Update the document 'modification' date
    # todo: document.setEffectiveDate(DateTime())

    if log_message:
        ts = str(int(DateTime()))
        context.changes_log.append( { 'date' : ts, 'member' : username, 'comment': log_message } )

    no_clean_html = not context.portal_membership.getInterfacePreferences('cleanup')
    context.cleanup( no_clean_html=no_clean_html )

    # Update additional fields
    sheet = context.propertysheets.get('ext_metadata', None)
    if sheet:
       for prop in sheet.propertyIds():
            sheet.manage_changeProperties({ prop: REQUEST.get(prop,'') })

    # Make task respose
    x = context.Respond( status, response, close_report=close_report, redirect=0, no_commit=1, no_update_runtime=1, REQUEST=REQUEST )

    IsError = not ( x and x[0] ) and 1 or 0

except 'EditingConflict', text:
    return context.document_conflict_form( context, REQUEST=REQUEST )
except ResourceLockedError:
    message = "Since document is locked, it was not saved."
    ObjectIsLocked = 1
    IsError = 0
except SimpleError, msg:
    message = str(msg)
    IsError = 1
except Exception, error:
    IsError = 1
    raise

CommitThread( context, 'task_inspect: %s' % action, IsError, force=1, subtransaction=None )

end_time = DateTime()
UpdateRequestRuntime( context, username, start_time, end_time, 'task_inspect %s' % ( action and '[%s]' % action or '' ) )

action = 'view'

return REQUEST.RESPONSE.redirect(
    context.absolute_url( action=action, message=message ),
    status=303 )
