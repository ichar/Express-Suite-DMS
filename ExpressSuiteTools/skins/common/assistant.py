## Script (Python) "assistant"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=
##title=
##
# $Id: invoke_factory.py,v 1.40.10.1.6.2 2004/11/25 09:43:54 mbernatski Exp $
# $Revision: 1.40.10.1.6.2 $
from Products.ExpressSuiteTools.SecureImports import DateTime, refreshClientFrame, parseDate

REQUEST = context.REQUEST

return context.assistant_form(context,
    REQUEST=REQUEST
)
