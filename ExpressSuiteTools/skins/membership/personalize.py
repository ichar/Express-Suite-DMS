## Script (Python) "personalize"
##bind container=container
##bind context=context
##bind namespace=_
##bind script=script
##bind subpath=traverse_subpath
##parameters=userid=None, refresh=None
##title=Personalization Handler
##
from Products.ExpressSuiteTools.SecureImports import portal_log

REQUEST = context.REQUEST

if REQUEST.get('refresh', None) or refresh:
    REQUEST.set('user_email', REQUEST.get('email', ''))
    return context.personalize_form( context, REQUEST=REQUEST )

user = context.portal_membership.getAuthenticatedMember()
uname = user.getUserName()

if user is None:
    return context.personalize_form( context, REQUEST=REQUEST )

if userid is None:
    user.setProperties( REQUEST )
else:
    member = context.portal_membership.getMemberById( userid )
    member.setMemberProperties( REQUEST )
    roles = list( member.getRoles() )

    if 'Manager' in roles:
        roles.remove('Manager')
    if REQUEST.get('manager'):
        roles.append('Manager')

    member.setSecurityProfile( roles=roles )

if REQUEST.has_key('portal_skin'):
    context.portal_skins.updateSkinCookie()

portal_log( context, 'personalize', 'py', 'changed by %s for member' % uname, userid, 1 )

qs = '/personalize_form?portal_status_message=Member+changed.'

abc = REQUEST.get('abc', None)
company = REQUEST.get('com', None)
department = REQUEST.get('dep', None)

if userid:
    qs += '&userid=%s' % userid
if abc:
    qs += '&abc=%s' % abc
if company:
    qs += '&com=%s' % company
if department:
    qs += '&dep=%s' % department

context.REQUEST.RESPONSE.redirect(context.portal_url() + qs)
