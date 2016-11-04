## Script (Python) "logout"
##title=Logout handler
##parameters=

REQUEST = context.REQUEST
RESPONSE = REQUEST.RESPONSE

if REQUEST.has_key( '__ac' ):
    RESPONSE.expireCookie( '__ac', path='/' )
    return RESPONSE.redirect( context.portal_url() + '/logged_out' )

elif hasattr(context, 'manage_logout'):
    return RESPONSE.redirect( context.portal_url() + '/manage_logout?auth=' + str(REQUEST['AUTHENTICATED_USER']) )

else:
    return context.manage_zmi_logout( REQUEST, RESPONSE )
