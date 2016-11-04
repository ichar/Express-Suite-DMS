## Script (Python) "folder_paste"
##title=Paste objects to a folder from the clipboard
from Products.ExpressSuiteTools.SecureImports import DateTime, refreshClientFrame, CopyError, SimpleError, \
     BeginThread, CommitThread, CustomDefs, ObjectHasCustomCategory, TypeOFSAction, \
     CreateObjectCopy, UpdateRequestRuntime, print_traceback

REQUEST=context.REQUEST

start_time = DateTime()
member = context.portal_membership.getAuthenticatedMember()
username = member.getUserName()
message = ''

IsError = 0
IsRun = 0

if CustomDefs('context_disabled', context=context):
    message = 'Not allowed $ $ error'
    return context.redirect( action='folder', message=message )
elif not context.cb_dataValid():
    message = 'Copy or cut one or more items to paste first'
    return context.redirect( action='folder', message=message )

BeginThread( context, 'folder_paste', force=None ) #!!! don't apply force

try:
    # check action type (op): 0-copy, 1-move
    op = TypeOFSAction( context, REQUEST=REQUEST )

    if member.IsAdmin() or op == 1:
        context.manage_pasteObjects( REQUEST=context.REQUEST )
        message = 'Item(s) Pasted'
        IsRun = 1
    else:
        items = context.cb_dataItems()
        created = 0
        for item in items:
            if ObjectHasCustomCategory( item ) and CreateObjectCopy( context, item, default=1 ):
                created += 1
                IsRun = 1
        if created == len(items):
            message = 'Item(s) Created'
        elif created > 0:
            message = 'Not all item(s) created $ (%s)' % created
        else:
            message = 'Error until object(s) creation $ $ error'
            IsError = 1

except CopyError, msg:
    message = 'Copy error $ %s $ error' % msg
    IsError = 1
except SimpleError, msg:
    LOG( 'folder_paste', ERROR, "%s: %s\n%s" % ( 'SimpleError', msg, print_traceback() ) )
    message = 'Item(s) copy error $ $ error'
    IsError = 1
#except:
#    message = 'Possible you try to copy an alien object. It is impossible! $ $ error'
#    IsError = 1
except:
    raise

CommitThread( context, 'folder_paste', IsError, force=1, subtransaction=None )

refreshClientFrame( 'navTree' )

end_time = DateTime()
if IsRun: UpdateRequestRuntime( context, username, start_time, end_time, 'folder_paste' )

return context.redirect( action='folder', message=message )
