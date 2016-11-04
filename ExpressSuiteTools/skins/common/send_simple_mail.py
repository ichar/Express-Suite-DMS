## Script (Python) "simple_mail"
##bind context=context
##bind container=container
##bind namespace=_
##bind script=script
##bind subpath=traverse_subpath
##parameters=REQUEST=None,mail_text=None,subj=None,f_addr=None,t_addr=None
##title=Mail a message to user
##
from Products.ExpressSuiteTools.SecureImports import portal_info # portal_error

REQUEST = context.REQUEST
message = None

kwargs = {}
kwargs.setdefault( 'mail_text', mail_text )
kwargs.setdefault( 'mail_subject', subj )

host = context.MailHost

mto = [t_addr]
mfrom = f_addr

if host is not None:
    try:
        count = host.sendTemplate( template='simple_mail', mto=mto, mfrom=mfrom, **kwargs )
    except Exception, msg:
        #message = "Error: %s" % str(msg)
        portal_info('simple_mail error', ( host.address(), mto, mfrom ), exc_info=True)
        count = 0

if not message:
    message = count and "Message is sent" or "Error while sending message"

return context.send_mail_response( context, REQUEST, message=message )
