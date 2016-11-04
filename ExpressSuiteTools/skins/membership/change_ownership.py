## Script (Python) "change_ownership"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=userid
##title=Action to change ownership
##
# $Id: change_ownership.py,v 1.3 2003/06/06 10:24:15 Exp $

# do not change permission on version
object = context
while object.implements('isVersion'):
    object = object.aq_parent

object.changeOwnership( userid, explicit=1 )
message = 'Owner changed.'

try:
    url = context.absolute_url( redirect=1, action='view', message=message, frame='document_frame' )
    ob = context.unrestrictedTraverse( object.relative_url() )
except:
    url = object.aq_parent.absolute_url( redirect=1, message=message )

context.REQUEST['RESPONSE'].redirect( url )
