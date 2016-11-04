## Script (Python) "fs_folder_edit"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=
# $Id: fs_folder_edit.py,v 1.1.2.1 2003/10/17 09:49:02 Exp $
##title=Edit a filefolder
##
from Products.ExpressSuiteTools.SecureImports import refreshClientFrame

REQUEST = context.REQUEST
context.edit(REQUEST.folder_path,REQUEST.title, REQUEST.description)

refreshClientFrame( [ 'workspace', 'navTree' ] )

#context.REQUEST.RESPONSE.redirect( context.absolute_url() + '/filefolder_edit_form' )
info = context.portal_types.getTypeInfo( context )

return context.redirect( action=info.immediate_view )
