# Example code:

# Import a standard function, and get the HTML request and response objects.
from Products.PythonScripts.standard import html_quote
request = container.REQUEST
RESPONSE = request.RESPONSE

url = context.absolute_url(redirect=1, action='home', frame='inFrame', params={'_UpdateSections':['main']})

if auth == str(request['AUTHENTICATED_USER']):
    realm=RESPONSE.realm
    RESPONSE.setStatus(401)
    RESPONSE.setHeader('WWW-Authenticate', 'basic realm="%s"' % realm, 1)
    RESPONSE.setBody("<html><head><title>Logout</title></head><body><p>You have been logged out.</p></body></html>")
    return
else:
    return RESPONSE.redirect(url)
