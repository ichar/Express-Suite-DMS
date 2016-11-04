## Script (Python) "reconfig"
##title=Reconfigure Portal
##parameters=
from Products.ExpressSuiteTools.SecureImports import portal_log

REQUEST = context.REQUEST
member = context.portal_membership.getAuthenticatedMember()
uname = member.getUserName()

if member.IsAdmin():
    context.portal_properties.editProperties( REQUEST )
    portal_log( context, 'reconfig', 'py', 'changed by', ( uname ), force=1 )

return REQUEST.RESPONSE.redirect(context.portal_url() + '/reconfig_form?portal_status_message=CMF+Settings+changed.')
