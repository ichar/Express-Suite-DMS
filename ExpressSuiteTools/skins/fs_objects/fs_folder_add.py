## Script (Python) "fs_folder_add"
##title=Add FS Folder 
##parameters=id, title, description, folder_path
# $Id: fs_folder_add.py,v 1.1.2.2 2003/11/10 13:16:32 Exp $
from Products.ExpressSuiteTools.SecureImports import cookId, refreshClientFrame

id = cookId(context, id)

try:
    context.manage_addProduct['ExpressSuiteTools'].addFSFolder( id=id
                        , title=title
                        , description=description
                        , path=folder_path
                        )
except 'MyOSError', err_msg:
    return context.redirect( message=err_msg )

ob = context[id]

refreshClientFrame( [ 'workspace','navTree' ] )

info = context.portal_types.getTypeInfo( ob )

return ob.redirect( action=info.immediate_view )
