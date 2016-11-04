## Script (Python) "changeDocumentOrder"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=REQUEST, RESPONSE, id, order
##title=Changing viewing order
##
REQUEST = context.REQUEST

context.shiftDocument(id, order)

qst='?portal_status_message=Folder+changed'

REQUEST.RESPONSE.redirect( context.absolute_url() + '/viewing_order' + qst )

