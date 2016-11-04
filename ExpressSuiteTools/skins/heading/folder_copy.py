## Script (Python) "folder_copy"
##title=Copy object from a folder to the clipboard
from Products.ExpressSuiteTools.SecureImports import DateTime, Unauthorized, UpdateRequestRuntime, CustomDefs

REQUEST=context.REQUEST

start_time = DateTime()
member = context.portal_membership.getAuthenticatedMember()
username = member.getUserName()
message = ''

source_ids = []
IsBadCopies = 0
IsRun = 0

if REQUEST.has_key('ids'):
    ids = REQUEST['ids']
    if member.IsAdmin():
        source_ids = ids
    elif len(ids) > 3: # or CustomDefs('context_disabled', context=context):
        message = 'Not allowed $ $ error'
    else:
        source_ids = ids

if source_ids:
    try:
        context.manage_copyObjects( source_ids, REQUEST, REQUEST.RESPONSE )
        message = 'Item(s) Copied'
        if len(source_ids) > 1:
            message = '%s $ (%s)' % ( message, len(source_ids) )
        IsRun = 1
    except:
        message = 'Not allowed $ $ error'

elif IsBadCopies:
    message = 'Exist too many copies of the objects $ $ error'

elif not message:
    message = 'Please select one or more items to copy first $ $ error'

end_time = DateTime()
if IsRun: UpdateRequestRuntime( context, username, start_time, end_time, 'folder_copy %s' % str(ids) )

return context.redirect( action='folder', message=message )