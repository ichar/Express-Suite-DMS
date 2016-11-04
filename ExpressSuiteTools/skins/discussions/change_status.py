## Script (Python) "change_status"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=REQUEST, RESPONSE, replyID, status=1
##

reply = context.restrictedTraverse( replyID )

#Change the status of top-level comment
reply.manage_changeProperties( {'status': status} )

target = '%s/%s' % (context.absolute_url(), replyID)

context.REQUEST.RESPONSE.redirect(target)