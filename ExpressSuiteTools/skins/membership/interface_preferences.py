## Script (Python) "interface_preferences"
##bind container=container
##bind context=context
##bind namespace=_
##bind script=script
##bind subpath=traverse_subpath
##parameters=
##title=Personalization Handler.
##
from Products.ExpressSuiteTools.SecureImports import refreshClientFrame

REQUEST = context.REQUEST
membership = context.portal_membership

try:
    membership.setInterfacePreferences( REQUEST )
    IsError = 0
except:
    IsError = 1

if not IsError and REQUEST.has_key('portal_skin'):
    context.portal_skins.updateSkinCookie()

if not IsError and REQUEST.has_key('lang'):
    lang = REQUEST.get('lang')
    membership.setMemberLanguage( lang )
    context.msg.changeLanguage( lang, REQUEST, REQUEST.RESPONSE )
    if membership.getLanguage() != lang:
        return context.REQUEST.RESPONSE.redirect( context.portal_url() )

if not IsError and REQUEST.has_key('commissions'):
    IsError = membership.setCommissions( value=REQUEST.get('commissions'), sync=0 )

if IsError:
    qs = 'portal_status_message=error'
else:
    qs = 'portal_status_message=Member+changed.'

redirect_url = '%s%s?%s&%s' % ( context.portal_url(), '/interface_preferences_form', qs, '_UpdateSections:tokens=main' )

context.REQUEST.RESPONSE.redirect( redirect_url )