## Script (Python) "image_edit"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=id, precondition='', file=''
##title=Edit an image
##
old_id = context.getId()
if old_id != id:
    context.aq_parent.manage_renameObjects([old_id,], [id,])

context.edit(
     precondition=precondition,
     file=file)

if context.REQUEST.get('Status') and context.portal_workflow.getInfoFor(context, 'state', '')=='private':
    context.portal_workflow.doActionFor( context, 'publish', comment='Published by CMF' )

qst='?portal_status_message=State+changed'

context.REQUEST.RESPONSE.redirect( context.absolute_url() + '/image_edit_form' + qst )
