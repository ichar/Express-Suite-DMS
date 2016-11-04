## Script (Python) "file_edit"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=precondition='', file=''
##title=Edit a file
##
context.edit(
     precondition=precondition,
     file=file)

if context.REQUEST.get('Status') and context.portal_workflow.getInfoFor(context, 'state', '')=='private':
    context.portal_workflow.doActionFor( context, 'publish', comment='Published by CMF' )


qst='?portal_status_message=File+saved'

context.REQUEST.RESPONSE.redirect( context.absolute_url() + '/file_edit_form' + qst )
