## Script (Python) "reply_to_document"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=category, uid
##title=
##
from Products.ExpressSuiteTools.SecureImports import DateTime, refreshClientFrame, parseDate, CustomReplyToAction

REQUEST = context.REQUEST
REQUEST.set('expand', 1)

message = ''

if uid:
    ob = context.portal_catalog.getObjectByUid( uid )
else:
    ob = None

type_name, default_category, relation, by_matter, default_values = CustomReplyToAction( ob, category )

if ob is not None:
    #REQUEST.set('title', ob.Title())
    description = ob.Description()
    if description:
        REQUEST.set('description', '%s: %s' % ( context.msg(by_matter), description ) )
    if default_values:
        REQUEST.set('default_values', default_values)

    ob.aq_parent.manage_copyObjects( [ ob.getId() ], REQUEST )

return context.invoke_factory_form( context,
    type_name=type_name or 'HTMLDocument', default_category=default_category, relation=relation,
    REQUEST=REQUEST
)
