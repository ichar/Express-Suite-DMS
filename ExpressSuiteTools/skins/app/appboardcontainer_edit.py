## Script (Python) "appboardcontainer_edit"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=REQUEST, RESPONSE, title=''
##title=Edit a board item
##
context.edit(title=title)
context.reindexObject()

context.REQUEST.RESPONSE.redirect( context.absolute_url() + '/appboardcontainer_view' )