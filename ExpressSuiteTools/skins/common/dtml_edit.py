## Script (Python) "document_edit"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=REQUEST, RESPONSE, id, title='', data=' '
##title=Edit a document
##
message='Document+saved.'

context.edit(title, data)

old_id = context.getId()
if old_id != id:
    context.aq_parent.manage_renameObjects([old_id,], [id,])

qst='?portal_status_message='+message


context.REQUEST.RESPONSE.redirect( context.absolute_url() + '/dtml_edit_form' + qst )
