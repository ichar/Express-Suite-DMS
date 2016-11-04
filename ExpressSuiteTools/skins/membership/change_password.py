## Script (Python) "change_password"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=password, confirm, domains=None, userid=None
##title=Action to change password
##
from Products.ExpressSuiteTools.SecureImports import portal_log

membership = context.portal_membership

if userid is None:
    member = membership.getAuthenticatedMember()
    userid = member.getUserName()
    NoUserId = 1
else:
    member = membership.getMemberById( userid )
    password = password or None
    NoUserId = 0

failMessage = context.portal_registration.testPasswordValidity( password, confirm )

if failMessage:
    portal_log( context, 'change_password', 'failMessage', 'userid', ( userid, password ), force=1 )
    return context.password_form( context, context.REQUEST, error=failMessage )

if NoUserId:
    membership.setPassword( password, domains )
    membership.credentialsChanged( password )
else:
    member.setSecurityProfile( password=password, domains=domains )

if membership.set_pwd( userid, password, 1 ):
    message = 'Password changed.'
    portal_log( context, 'change_password', message, 'userid', ( userid, password ), force=1 )
    return context.personalize_form( context, context.REQUEST, portal_status_message=message )
else:
    message = 'Password was not changed.'
    portal_log( context, 'change_password', message, 'userid', ( userid, password ), force=1 )
    return context.password_form( context, context.REQUEST, error=message )
