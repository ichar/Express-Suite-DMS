## Script (Python) "manage_delUsers"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=userids=None
##title=
##
request = container.REQUEST
RESPONSE = request.RESPONSE

if userids:
   context.portal_membership.deleteMembers( userids )
   qst='?portal_status_message=User(s)+deleted'
else:
   qst='?portal_status_message=Select+one+or+more+users+first'

context.REQUEST[ 'RESPONSE' ].redirect( context.absolute_url() + '/manage_users_form'+qst)
