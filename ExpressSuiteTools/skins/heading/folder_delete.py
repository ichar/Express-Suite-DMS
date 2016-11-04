## Script (Python) "folder_delete"
##bind container=container
##bind context=context
##bind namespace=_
##bind script=script
##bind subpath=traverse_subpath
##parameters=ids=None
##title=Delete objects from a folder
from Products.ExpressSuiteTools.SecureImports import DateTime, refreshClientFrame, SimpleError, \
     BeginThread, CommitThread, UpdateRequestRuntime, CustomDefs

REQUEST=context.REQUEST

start_time = DateTime()
member = context.portal_membership.getAuthenticatedMember()
username = member.getUserName()
message = ''

IsRun = 0

context_url = context.absolute_url()
params = {}

if not ids:
    message = 'Please select one or more items first.'
    return context.redirect( action='folder', message=message )
elif len(ids) > 100 or CustomDefs('context_disabled', context=context):
    message = 'Not allowed'
    return context.redirect( action='folder', message=message )

BeginThread( context, 'folder_delete', force=1 )

if not same_type( ids, [] ):
    ids = [ids]
try:
    # First of all remove related shortcuts (such as favorites)
    res = context.portal_catalog.searchResults( meta_type='Shortcut' )

    for r in res:
        ob = r.getObject()
        if ob is None:
            continue
        source = ob.getObject()
        if source is None:
            continue
        parent = ob.aq_parent
        if parent is None:
            continue

        try:
            source_id = source.getId()
            source_url = source.aq_parent.absolute_url()
        except:
            continue

        if source_id in ids and source_url == context_url:
            parent.manage_delObjects( ids=r['id'] )

    # and only after remove objects
    nDeleted = context.deleteObjects( ids )
    IsError = 0
    IsRun = 1

except SimpleError, msg:
    message = '%s $ $ error' % str(msg)
    nDeleted = 0
    IsError = 1
except:
    raise

CommitThread( context, 'folder_delete', IsError, force=1, subtransaction=None )

if nDeleted:
    refreshClientFrame( [ 'workspace', 'navTree', 'followup_menu' ] )

if not nDeleted:
    if not message:
        message = 'Object(s) were not deleted. Either you have no permission to delete them or they are locked. $ $ error'
elif nDeleted < len(ids):
    message = '%(count)d object(s) were not deleted. Either you have no permission to delete them or they are locked. $ $ error'
    params['count:int'] = len(ids) - nDeleted
else:
    message = 'Deleted.'

end_time = DateTime()
if IsRun:
    UpdateRequestRuntime( context, username, start_time, end_time, 'folder_delete %s' % str(ids) )

return context.redirect( action='folder', message=message, params=params )
